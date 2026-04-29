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
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from MeshParser import get_optimal_topics

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from api.utils.pubmed_api_client import PubMedAPIClient
from api.utils.qdrant_vector_client import QdrantVectorClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

# Windows konsolė naudoja cp1252 — lietuviški simboliai netelpa.
# Nustatome UTF-8 stdout/stderr ir logging handler'iams.
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

ARTICLES_PER_TOPIC = int(os.getenv("INDEXER_ARTICLES_PER_TOPIC", "200"))

# Pauzė tarp topic'ų (sekundės)
DELAY_BETWEEN_TOPICS = float(os.getenv("INDEXER_TOPIC_DELAY", "1.0"))

# Lygiagrečių fetch'ų skaičius (be API key: max 3 req/s → 3 workers)
# Su PUBMED_API_KEY: max 10 req/s → 8 workers saugiai
FETCH_WORKERS = int(os.getenv("INDEXER_FETCH_WORKERS", "8"))

PROGRESS_FILE = os.getenv("INDEXER_PROGRESS_FILE", "indexer_progress.json")

TOPICS = []


# ── Text cleaning ─────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Valo tekstą prieš embed'inimą."""
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
    # Saugojame tik completed_topics ir stats — ne indexed_pmc_ids
    # (Qdrant yra authoritative šaltinis; set'as laikomas atmintyje)
    slim = {
        "completed_topics": progress.get("completed_topics", []),
        "stats": progress.get("stats", {}),
    }
    with open(PROGRESS_FILE, "w") as f:
        json.dump(slim, f, indent=2)


# ── Qdrant helpers ────────────────────────────────────────────────────────────

def load_indexed_ids_from_qdrant(qdrant: QdrantVectorClient) -> set[str]:
    """
    Nuskaito visus source_id (pmc_id) iš Qdrant vienu praėjimu.
    Kviečiama tik kartą paleidus — rezultatas laikomas atmintyje kaip set.
    """
    log.info("Kraunami jau indeksuoti PMC ID iš Qdrant...")
    indexed: set[str] = set()
    offset = None

    while True:
        try:
            results, next_offset = qdrant.client.scroll(
                collection_name="fact_checker_cache",
                scroll_filter=Filter(must=[
                    FieldCondition(
                        key="source_db",
                        match=MatchValue(value="pubmed_bulk"),
                    )
                ]),
                limit=1000,
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

        if next_offset is None:
            break
        offset = next_offset

    log.info(f"Rasta {len(indexed)} jau indeksuotų straipsnių Qdrant")
    return indexed


def _prepare_article(article: dict, pmc_id: str) -> dict | None:
    """
    Parengia straipsnio dict'ą store_bulk_batch kvietimui.
    Grąžina None jei nėra teksto.
    """
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
    """
    Fetch'ina kelis straipsnius lygiagrečiai.

    Args:
        pubmed:      PubMedAPIClient instance.
        pmc_ids:     Sąrašas PMC ID, kuriuos reikia fetch'inti.
        max_workers: Lygiagrečių thread'ų kiekis.

    Returns:
        Dict {pmc_id: article_content} — tik sėkmingai gauti straipsniai.
    """
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
    Grąžina (topic, prepared_articles, partial_stats).
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


def run_indexer(once: bool = True, interval: int = 3600) -> None:
    """
    Paleidžia background indexer'į su pipeline optimizacija:
    kol embed'inamas topic N, background thread'e fetch'inamas topic N+1.

    Args:
        once:     True = vienkartinis run, False = kartojasi kas `interval` sekundžių
        interval: Pauzė tarp run'ų sekundėmis (naudojama tik jei once=False)
    """
    pubmed = PubMedAPIClient()
    qdrant = QdrantVectorClient()
    TOPICS = get_optimal_topics()

    log.info("Background indexer paleistas")
    log.info(f"  Topics: {len(TOPICS)}")
    log.info(f"  Straipsnių per topic: {ARTICLES_PER_TOPIC}")
    log.info(f"  Fetch workers: {FETCH_WORKERS}")
    log.info(f"  Režimas: {'vienkartinis' if once else f'kas {interval}s'}")

    indexed_ids = load_indexed_ids_from_qdrant(qdrant)

    # Atskiras thread pool tik pipeline fetch'ui (1 thread pakanka —
    # fetch_and_prepare viduje jau naudoja FETCH_WORKERS per fetch_batch)
    pipeline_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")

    while True:
        progress  = load_progress()
        run_stats = {"new": 0, "skipped": 0, "errors": 0}
        start_time = datetime.now()
        completed  = set(progress.get("completed_topics", []))

        # Sudaryti sąrašą topic'ų, kurie dar neatlikti šiame run'e
        pending = [t for t in TOPICS if t not in completed]
        log.info(f"Liko {len(pending)} topic'ų")

        if not pending:
            log.info("Visi topic'ai atlikti — run baigtas.")
        else:
            # ── Pipeline: iš anksto paleisti pirmojo topic'o fetch'ą ────────
            next_future = pipeline_pool.submit(
                fetch_and_prepare, pending[0], pubmed, indexed_ids
            )

            for i, topic in enumerate(pending):
                # 1. Gauti šio topic'o paruoštus straipsnius
                cur_topic, prepared, fetch_stats = next_future.result()

                # 2. Iš karto paleisti kito topic'o fetch'ą background'e
                #    (vyksta lygiagrečiai su embed+upsert žemiau)
                if i + 1 < len(pending):
                    next_future = pipeline_pool.submit(
                        fetch_and_prepare, pending[i + 1], pubmed, indexed_ids
                    )

                # 3. Embed + upsert (čia CPU intensyvus darbas)
                embed_stats = {"new": 0, "skipped_no_text": 0, "errors": 0}
                if prepared:
                    log.info(f"Embed+upsert: '{cur_topic}' ({len(prepared)} straipsnių)")
                    chunk_counts = qdrant.store_bulk_batch(prepared)

                    for pmc_id, n_chunks in chunk_counts.items():
                        log.info(f"  ✓ [{pmc_id}] → {n_chunks} chunks")
                        embed_stats["new"] += 1
                        indexed_ids.add(pmc_id)

                    skipped_fp = len(prepared) - len(chunk_counts)
                    embed_stats["skipped_no_text"] += skipped_fp
                else:
                    log.info(f"  Nėra naujų straipsnių: '{cur_topic}'")

                # 4. Susumuoti statistiką
                topic_stats = {
                    "new":              embed_stats["new"],
                    "skipped_cached":   fetch_stats["skipped_cached"],
                    "skipped_no_text":  fetch_stats["skipped_no_text"] + embed_stats["skipped_no_text"],
                    "errors":           fetch_stats["errors"] + embed_stats["errors"],
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

        if once:
            pipeline_pool.shutdown(wait=False)
            break

        log.info(f"Kitas run po {interval}s...")
        time.sleep(interval)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PubMed background indexer")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Kartoti kas --interval sekundžių (default: vienkartinis run)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="Pauzė tarp run'ų sekundėmis (default: 3600 = 1h)",
    )
    parser.add_argument(
        "--topics",
        type=int,
        default=None,
        help="Kiek topic'ų paleisti (debug: --topics 2)",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="Išvalo progress.json ir pradeda iš naujo",
    )
    args = parser.parse_args()

    if args.reset_progress and Path(PROGRESS_FILE).exists():
        Path(PROGRESS_FILE).unlink()
        log.info("Progress failas išvalytas.")

    if args.topics:
        original = TOPICS.copy()
        TOPICS[:] = TOPICS[:args.topics]
        log.info(f"Debug režimas: {len(TOPICS)} topic(s)")

    run_indexer(once=not args.loop, interval=args.interval)