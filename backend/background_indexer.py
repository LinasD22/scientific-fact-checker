"""
Background indexer for bulk PubMed article indexing.

Paleidimas:
    python background_indexer.py                         # vienkartinis run
    python background_indexer.py --loop --interval 3600  # kas valandą

Veikimo principas:
    1. Kiekvienam topic'ui iš TOPICS sąrašo ieško PubMed straipsnių
    2. Kiekvienas straipsnis tikrinamas ar jau indeksuotas (pagal pmc_id)
    3. Nauji straipsniai: chunk → embed → store į Qdrant
    4. Progresas saugomas progress.json — galima sustabdyti ir tęsti

Optimizacijos (v2):
    - Gilesnė pipeline: PREFETCH_DEPTH topic'ų fetch'inami lygiagrečiai
      kol vyksta embed+upsert
    - DELAY_BETWEEN_TOPICS = 0 — dirbtinis lėtinimas pašalintas
    - store_bulk_batch: visas topic'as embed'inamas ir upsert'inamas vienu kvietimu
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from datetime import datetime
from pathlib import Path

from MeshParser import get_optimal_topics

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from api.utils.pubmed_api_client import PubMedAPIClient
from api.utils.qdrant_vector_client import QdrantVectorClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("background_indexer.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── Konfigūracija ─────────────────────────────────────────────────────────────

ARTICLES_PER_TOPIC = int(os.getenv("INDEXER_ARTICLES_PER_TOPIC", "20"))

# Sumažinta iki 0 — fetch/embed/upsert pasiskirsto lygiagrečiai,
# dirbtinis lėtinimas nebereikalingas.
DELAY_BETWEEN_TOPICS = float(os.getenv("INDEXER_TOPIC_DELAY", "0.0"))

FETCH_WORKERS = int(os.getenv("INDEXER_FETCH_WORKERS", "10"))

# Kiek topic'ų iš anksto fetch'inti (pipeline gylis).
# 2 = kol embed'inamas N, fetch'inami N+1 ir N+2 lygiagrečiai.
PREFETCH_DEPTH = int(os.getenv("INDEXER_PREFETCH_DEPTH", "2"))

PROGRESS_FILE     = os.getenv("INDEXER_PROGRESS_FILE", "indexer_progress.json")
INDEXED_IDS_CACHE = os.getenv("INDEXER_IDS_CACHE", "indexed_pmc_ids.json")

TOPICS = []


# ── Text cleaning ─────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\x0c', '\n', text)
    text = re.sub(r'\s+\.\s+', '. ', text)
    return text.strip()


# ── Progress tracking ─────────────────────────────────────────────────────────

def load_progress() -> dict:
    if Path(PROGRESS_FILE).exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed_topics": [], "stats": {}}


def save_progress(progress: dict) -> None:
    slim = {
        "completed_topics": progress.get("completed_topics", []),
        "stats": progress.get("stats", {}),
    }
    with open(PROGRESS_FILE, "w") as f:
        json.dump(slim, f, indent=2)


# ── Qdrant helpers ────────────────────────────────────────────────────────────

def load_indexed_ids_from_qdrant(qdrant: QdrantVectorClient) -> set[str]:
    """
    Nuskaito visus source_id (pmc_id) iš Qdrant.
    Pirma tikrina lokalų cache failą — jei egzistuoja, naudoja jį.
    """
    cache_path = Path(INDEXED_IDS_CACHE)
    if cache_path.exists():
        cache_age_h = (time.time() - cache_path.stat().st_mtime) / 3600
        log.info(f"Rastas lokalus ID cache ({cache_path}, amžius: {cache_age_h:.1f}h)")
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            indexed = set(data.get("ids", []))
            log.info(f"  Įkelti {len(indexed)} ID iš cache (greitas paleidimas)")
            return indexed
        except Exception as e:
            log.warning(f"  Cache nuskaitymas nepavyko ({e}), skanuojamas Qdrant...")

    log.info("Kraunami jau indeksuoti PMC ID iš Qdrant (gali užtrukti)...")
    indexed: set[str] = set()
    offset = None
    batch_num = 0
    BATCH_SIZE = 10_000

    while True:
        try:
            results, next_offset = qdrant.client.scroll(
                collection_name="fact_checker_cache",
                scroll_filter=Filter(must=[
                    FieldCondition(key="source_db", match=MatchValue(value="pubmed_bulk"))
                ]),
                limit=BATCH_SIZE,
                offset=offset,
                with_payload=["source_id"],
                with_vectors=False,
            )
        except Exception as e:
            log.warning(f"Klaida skaitant Qdrant: {e}")
            break

        for point in results:
            sid = (point.payload or {}).get("source_id", "")
            if sid:
                indexed.add(sid)

        batch_num += 1
        if batch_num % 10 == 0:
            log.info(f"  ... nuskaityta {len(indexed)} ID ({batch_num} batchų)")

        if next_offset is None:
            break
        offset = next_offset

    log.info(f"Rasta {len(indexed)} jau indeksuotų straipsnių Qdrant")

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"ids": list(indexed), "saved_at": datetime.now().isoformat()}, f)
        log.info(f"ID cache išsaugotas → {cache_path}")
    except Exception as e:
        log.warning(f"Cache išsaugoti nepavyko: {e}")

    return indexed


def _prepare_article(article: dict, pmc_id: str) -> dict | None:
    title     = article.get("title") or "Unknown"
    full_text = article.get("full_text") or ""
    abstract  = article.get("abstract") or ""
    text      = clean_text(full_text) if full_text else clean_text(abstract)

    if not text:
        return None

    return {
        "pmc_id":         pmc_id,
        "title":          title,
        "text":           text,
        "source_db":      "pubmed_bulk",
        "source_id":      pmc_id,
        "authors":        article.get("authors"),
        "published_date": article.get("published_date"),
        "url":            article.get("url"),
    }


# ── Lygiagretus fetch ─────────────────────────────────────────────────────────

def fetch_batch(
    pubmed: PubMedAPIClient,
    pmc_ids: list[str],
    max_workers: int = FETCH_WORKERS,
) -> dict[str, dict]:
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_id = {
            pool.submit(pubmed.fetch_article_content, pmc_id): pmc_id
            for pmc_id in pmc_ids
        }
        for future in as_completed(future_to_id):
            pmc_id = future_to_id[future]
            try:
                content = future.result()
                if content:
                    results[pmc_id] = content
            except Exception as e:
                log.warning(f"  Fetch klaida [{pmc_id}]: {e}")
    return results


def fetch_and_prepare(
    topic: str,
    pubmed: PubMedAPIClient,
    indexed_ids: set[str],
    limit: int = ARTICLES_PER_TOPIC,
) -> tuple[str, list[dict], dict]:
    """
    Vieno topic'o fetch + prepare fazė (be embedding).
    Kviečiama background thread'e kol embed'inamas ankstesnis topic'as.
    """
    stats = {"new": 0, "skipped_cached": 0, "skipped_no_text": 0, "errors": 0}

    log.info(f"\n{'─' * 60}")
    log.info(f"Fetch: '{topic}' (limit={limit})")

    try:
        article_ids = pubmed.search_article_ids(topic, limit=limit, use_mesh=True)
    except Exception as e:
        log.error(f"esearch nepavyko '{topic}': {e}")
        stats["errors"] += 1
        return topic, [], stats

    log.info(f"  Rasta {len(article_ids)} IDs")

    new_ids = [pid for pid in article_ids if pid not in indexed_ids]
    skipped = len(article_ids) - len(new_ids)
    stats["skipped_cached"] += skipped
    log.info(f"  Praleista: {skipped}, fetch'inama: {len(new_ids)}")

    if not new_ids:
        return topic, [], stats

    fetched = fetch_batch(pubmed, new_ids, max_workers=FETCH_WORKERS)
    log.info(f"  Gauta: {len(fetched)}/{len(new_ids)}")
    stats["errors"] += len(new_ids) - len(fetched)

    prepared = []
    for pmc_id, content in fetched.items():
        art = _prepare_article(content, pmc_id)
        if art:
            prepared.append(art)
        else:
            stats["skipped_no_text"] += 1

    return topic, prepared, stats


# ── Pagrindinis run ───────────────────────────────────────────────────────────

def run_indexer(once: bool = True, interval: int = 3600) -> None:
    """
    Paleidžia background indexer'į su giliu pipeline (PREFETCH_DEPTH topic'ų).

    Pipeline:
        - Kol embed'inamas topic N, lygiagrečiai fetch'inami N+1 .. N+PREFETCH_DEPTH
        - Visas topic'as embed'inamas ir upsert'inamas vienu store_bulk_batch kvietimu

    Args:
        once:     True = vienkartinis run, False = kartojasi kas `interval` sekundžių
        interval: Pauzė tarp run'ų sekundėmis (naudojama tik jei once=False)
    """
    pubmed = PubMedAPIClient()
    qdrant = QdrantVectorClient()
    TOPICS = get_optimal_topics()

    log.info("Background indexer paleistas (v2 — gilaus pipeline)")
    log.info(f"  Topics: {len(TOPICS)}")
    log.info(f"  Straipsnių per topic: {ARTICLES_PER_TOPIC}")
    log.info(f"  Fetch workers: {FETCH_WORKERS}")
    log.info(f"  Prefetch gylis: {PREFETCH_DEPTH}")
    log.info(f"  Režimas: {'vienkartinis' if once else f'kas {interval}s'}")

    indexed_ids = load_indexed_ids_from_qdrant(qdrant)

    # PREFETCH_DEPTH thread'ų — kiekvienas fetch'ina vieną topic'ą
    pipeline_pool = ThreadPoolExecutor(
        max_workers=PREFETCH_DEPTH,
        thread_name_prefix="pipeline",
    )

    while True:
        progress   = load_progress()
        run_stats  = {"new": 0, "skipped": 0, "errors": 0}
        start_time = datetime.now()
        completed  = set(progress.get("completed_topics", []))

        pending = [t for t in TOPICS if t not in completed]
        log.info(f"Liko {len(pending)} topic'ų")

        if not pending:
            log.info("Visi topic'ai atlikti — run baigtas.")
        else:
            # ── Gilaus pipeline inicializacija ───────────────────────────────
            # Iš anksto paleisti pirmuosius PREFETCH_DEPTH topic'ų fetch'us.
            prefetch_queue: list[tuple[int, Future]] = []
            for pi in range(min(PREFETCH_DEPTH, len(pending))):
                fut = pipeline_pool.submit(
                    fetch_and_prepare, pending[pi], pubmed, indexed_ids
                )
                prefetch_queue.append((pi, fut))

            for i, topic in enumerate(pending):
                # 1. Gauti šio topic'o paruoštus straipsnius
                _, cur_future = prefetch_queue.pop(0)
                cur_topic, prepared, fetch_stats = cur_future.result()

                # 2. Paleisti kito prefetch'o topic'o fetch'ą
                next_pi = i + PREFETCH_DEPTH
                if next_pi < len(pending):
                    fut = pipeline_pool.submit(
                        fetch_and_prepare, pending[next_pi], pubmed, indexed_ids
                    )
                    prefetch_queue.append((next_pi, fut))

                # 3. Embed + upsert — visas topic'as vienu store_bulk_batch kvietimu
                embed_stats = {"new": 0, "skipped_no_text": 0, "errors": 0}

                if prepared:
                    log.info(f"Embed+upsert: '{cur_topic}' ({len(prepared)} straipsnių)")
                    t0 = time.monotonic()
                    chunk_counts = qdrant.store_bulk_batch(prepared)
                    elapsed = time.monotonic() - t0

                    for pmc_id, n_chunks in chunk_counts.items():
                        log.info(f"  ✓ [{pmc_id}] → {n_chunks} chunks")
                        indexed_ids.add(pmc_id)

                    embed_stats["new"] += len(chunk_counts)
                    embed_stats["skipped_no_text"] += len(prepared) - len(chunk_counts)
                    log.info(f"  Embed+upsert baigtas [{elapsed:.1f}s]")
                else:
                    log.info(f"  Nėra naujų straipsnių: '{cur_topic}'")

                # 4. Statistika
                topic_stats = {
                    "new":             embed_stats["new"],
                    "skipped_cached":  fetch_stats["skipped_cached"],
                    "skipped_no_text": fetch_stats["skipped_no_text"] + embed_stats["skipped_no_text"],
                    "errors":          fetch_stats["errors"] + embed_stats["errors"],
                }
                run_stats["new"]     += topic_stats["new"]
                run_stats["skipped"] += topic_stats["skipped_cached"] + topic_stats["skipped_no_text"]
                run_stats["errors"]  += topic_stats["errors"]

                progress.setdefault("completed_topics", []).append(cur_topic)
                progress.setdefault("stats", {})[cur_topic] = {
                    **topic_stats,
                    "timestamp": datetime.now().isoformat(),
                }
                save_progress(progress)

                if DELAY_BETWEEN_TOPICS > 0:
                    time.sleep(DELAY_BETWEEN_TOPICS)

        # Run baigtas
        progress["completed_topics"] = []
        elapsed    = (datetime.now() - start_time).total_seconds()
        cache_info = qdrant.cache_stats()

        log.info(f"\n{'=' * 60}")
        log.info(f"Run baigtas [{elapsed:.0f}s]")
        log.info(f"  Nauji straipsniai: {run_stats['new']}")
        log.info(f"  Praleista:         {run_stats['skipped']}")
        log.info(f"  Klaidos:           {run_stats['errors']}")
        log.info(f"  Viso Qdrant:       {cache_info['total_chunks']} chunks")
        log.info(f"  Unikalūs PMC ID:   {len(indexed_ids)}")
        save_progress(progress)

        try:
            with open(INDEXED_IDS_CACHE, "w", encoding="utf-8") as f:
                json.dump({"ids": list(indexed_ids), "saved_at": datetime.now().isoformat()}, f)
            log.info(f"ID cache atnaujintas → {INDEXED_IDS_CACHE}")
        except Exception as e:
            log.warning(f"ID cache atnaujinti nepavyko: {e}")

        if once:
            pipeline_pool.shutdown(wait=False)
            break

        log.info(f"Kitas run po {interval}s...")
        time.sleep(interval)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PubMed background indexer")
    parser.add_argument("--loop", action="store_true",
                        help="Kartoti kas --interval sekundžių")
    parser.add_argument("--interval", type=int, default=3600,
                        help="Pauzė tarp run'ų sekundėmis (default: 3600)")
    parser.add_argument("--topics", type=int, default=None,
                        help="Kiek topic'ų paleisti (debug: --topics 2)")
    parser.add_argument("--reset-progress", action="store_true",
                        help="Išvalo progress.json ir pradeda iš naujo")
    parser.add_argument("--mini-batch", type=int, default=None,
                        help="Mini-batch dydis embed+upsert fazei (default: 5)")
    parser.add_argument("--prefetch", type=int, default=None,
                        help=f"Pipeline prefetch gylis (default: {PREFETCH_DEPTH})")
    args = parser.parse_args()

    if args.reset_progress and Path(PROGRESS_FILE).exists():
        Path(PROGRESS_FILE).unlink()
        log.info("Progress failas išvalytas.")
    if args.reset_progress and Path(INDEXED_IDS_CACHE).exists():
        Path(INDEXED_IDS_CACHE).unlink()
        log.info("ID cache failas išvalytas.")

    if args.mini_batch:
        os.environ["INDEXER_MINI_BATCH"] = str(args.mini_batch)
    if args.prefetch:
        PREFETCH_DEPTH = args.prefetch
    if args.topics:
        TOPICS[:] = TOPICS[:args.topics]
        log.info(f"Debug režimas: {len(TOPICS)} topic(s)")

    run_indexer(once=not args.loop, interval=args.interval)