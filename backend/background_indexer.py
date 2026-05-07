"""Background indexer for bulk PubMed article indexing.

Optimizacija (v5):
    - UPSERT vyksta fone (atskirame thread'e)
    - Pagrindinis thread'as iškart pradeda kito topic'o EMBEDDING'ą
    - CPU niekada nėra idle - embedding vyksta KOL upsertina
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from datetime import datetime
from pathlib import Path
from threading import Thread
from typing import Any, Optional

from qdrant_client.models import HnswConfigDiff

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from api.utils.pubmed_api_client import PubMedAPIClient
from api.utils.qdrant_vector_client import QdrantVectorClient, COLLECTION
from MeshParser import get_optimal_topics

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
DELAY_BETWEEN_TOPICS = float(os.getenv("INDEXER_TOPIC_DELAY", "0.1"))
FETCH_WORKERS = int(os.getenv("INDEXER_FETCH_WORKERS", "8"))
PREFETCH_DEPTH = int(os.getenv("INDEXER_PREFETCH_DEPTH", "1"))
EMBED_WORKERS = int(os.getenv("INDEXER_EMBED_WORKERS", "1"))
UPSERT_WORKERS = int(os.getenv("INDEXER_UPSERT_WORKERS", "1"))  # Naujas parametras

PROGRESS_FILE = os.getenv("INDEXER_PROGRESS_FILE", "indexer_progress.json")
INDEXED_IDS_CACHE = os.getenv("INDEXER_IDS_CACHE", "indexed_pmc_ids.json")

TOPICS = []


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
    """Nuskaito visus source_id (pmc_id) iš Qdrant."""
    cache_path = Path(INDEXED_IDS_CACHE)
    if cache_path.exists():
        log.info(f"Rastas lokalus ID cache ({cache_path})")
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            indexed = set(data.get("ids", []))
            log.info(f"  Įkelti {len(indexed)} ID iš cache")
            return indexed
        except Exception as e:
            log.warning(f"  Cache nuskaitymas nepavyko ({e})")

    log.info("Kraunami jau indeksuoti PMC ID iš Qdrant...")
    indexed = qdrant.get_all_pmc_ids()
    log.info(f"Rasta {len(indexed)} jau indeksuotų straipsnių Qdrant")

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"ids": list(indexed), "saved_at": datetime.now().isoformat()}, f)
        log.info(f"ID cache išsaugotas → {cache_path}")
    except Exception as e:
        log.warning(f"Cache išsaugoti nepavyko: {e}")

    return indexed


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
    """Vieno topic'o fetch + prepare fazė (be embedding)."""
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
        art = prepare_article(content, pmc_id)
        if art:
            prepared.append(art)
        else:
            stats["skipped_no_text"] += 1

    stats["new"] = len(prepared)
    return topic, prepared, stats


def prepare_article(article: dict, pmc_id: str) -> dict | None:
    """Paruošia straipsnį indeksavimui (be chunk'inimo)."""
    import re

    def clean_text(text: str) -> str:
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = re.sub(r'\x0c', '\n', text)
        text = re.sub(r'\s+\.\s+', '. ', text)
        return text.strip()

    title = article.get("title") or "Unknown"
    full_text = article.get("full_text") or ""
    abstract = article.get("abstract") or ""
    text = clean_text(full_text) if full_text else clean_text(abstract)

    if not text:
        return None

    return {
        "pmc_id": pmc_id,
        "title": title,
        "text": text,
        "source_db": "pubmed_bulk",
        "source_id": pmc_id,
        "authors": article.get("authors"),
        "published_date": article.get("published_date"),
        "url": article.get("url"),
    }


# ── Pagrindinis run su TRUE lygiagrečiu pipeline ─────────────────────────────

class UpsertTask:
    """Upsert užduotis, kuri vykdoma fone."""
    def __init__(self, topic: str, embed_future: Future, fetch_stats: dict):
        self.topic = topic
        self.embed_future = embed_future
        self.fetch_stats = fetch_stats
        self.upsert_future: Optional[Future] = None


def run_indexer(once: bool = True, interval: int = 3600) -> None:
    """
    Paleidžia background indexer'į su TRUE lygiagrečiu pipeline v5:

      STEP 1: Fetch topic N (lygiagrečiai per pipeline_pool)
      STEP 2: Kai fetch baigtas, iškart paleidžiamas embedding (embedding_pool)
      STEP 3: Kol N embed'inasi, pradedamas fetch N+1
      STEP 4: Kai embedding baigtas, UPSERT paleidžiamas atskirame thread'e
      STEP 5: Pagrindinis thread'as iškart pradeda kito topic'o embed'inimą

    Tai užtikrina, kad CPU niekada nėra idle:
      - Kol upsert (disko I/O) vyksta fone, kitas embed'as (CPU) jau dirba
    """
    pubmed = PubMedAPIClient()
    qdrant = QdrantVectorClient()
    topics_list = get_optimal_topics()

    log.info("before=")
    config_dict = qdrant.client.get_collection(COLLECTION).config.dict() # Konvertuojame i žodyna
    print(json.dumps(config_dict, indent=2))


    qdrant.client.update_collection(
        collection_name=COLLECTION,
        hnsw_config=HnswConfigDiff(m=0)
    )

    log.info("=" * 60)
    log.info("Background indexer v5 — TRUE parallel pipeline (async upsert)")
    log.info("=" * 60)
    log.info(f"  Topics: {len(topics_list)}")
    log.info(f"  Straipsnių per topic: {ARTICLES_PER_TOPIC}")
    log.info(f"  Fetch workers: {FETCH_WORKERS}")
    log.info(f"  Embed workers: {EMBED_WORKERS}")
    log.info(f"  Upsert workers: {UPSERT_WORKERS}")
    log.info(f"  Prefetch gylis: {PREFETCH_DEPTH}")
    log.info(f"  Režimas: {'vienkartinis' if once else f'kas {interval}s'}")

    log.info("after=")
    config_dict = qdrant.client.get_collection(COLLECTION).config.dict() # Konvertuojame i žodyna
    print(json.dumps(config_dict, indent=2))


    indexed_ids = load_indexed_ids_from_qdrant(qdrant)

    # Thread pool'ai
    pipeline_pool = ThreadPoolExecutor(
        max_workers=PREFETCH_DEPTH,
        thread_name_prefix="pipeline",
    )
    embedding_pool = ThreadPoolExecutor(
        max_workers=EMBED_WORKERS,
        thread_name_prefix="embedder",
    )
    upsert_pool = ThreadPoolExecutor(
        max_workers=UPSERT_WORKERS,
        thread_name_prefix="upserter",
    )

    while True:
        progress = load_progress()
        run_stats = {"new": 0, "skipped": 0, "errors": 0}
        start_time = datetime.now()
        completed = set(progress.get("completed_topics", []))

        pending = [t for t in topics_list if t not in completed]
        log.info(f"Liko {len(pending)} topic'ų")

        if not pending:
            log.info("Visi topic'ai atlikti — run baigtas.")
        else:
            # ──────────────────────────────────────────────────────────────
            # PIPELINE: fetch + embedding + upsert su TRUE overlap
            # ──────────────────────────────────────────────────────────────

            # Queue: (topic, fetch_future, fetch_stats, articles)
            fetch_queue: deque = deque()
            # Queue: UpsertTask objektai (su embed_future)
            upsert_queue: deque = deque()
            # Aktyvūs upsert'ai fone
            active_upserts: list[Future] = []

            # 1. Iš pradžių paleidžiame PREFETCH_DEPTH fetch'ų
            for i in range(min(PREFETCH_DEPTH, len(pending))):
                fut = pipeline_pool.submit(
                    fetch_and_prepare, pending[i], pubmed, indexed_ids
                )
                fetch_queue.append((pending[i], fut, None, None))

            # 2. Pagrindinis ciklas
            for idx, topic in enumerate(pending):
                # ── A. GAUTI ŠIO TOPIC'O FETCH REZULTATĄ ─────────────────
                if fetch_queue and fetch_queue[0][0] == topic:
                    t, fetch_future, _, _ = fetch_queue.popleft()
                    cur_topic, articles, fetch_stats = fetch_future.result()
                elif any(queue_topic == topic for queue_topic, _, _, _ in fetch_queue):
                    # Jei topic yra kažkur kitur eilėje (ne pirmas)
                    # Surandame ir paimame
                    for i, (qt, qf, _, _) in enumerate(fetch_queue):
                        if qt == topic:
                            fetch_queue_list = list(fetch_queue)
                            fetch_queue_list.pop(i)
                            fetch_queue = deque(fetch_queue_list)
                            cur_topic, articles, fetch_stats = qf.result()
                            break
                else:
                    cur_topic, articles, fetch_stats = topic, [], {"skipped_cached": 0, "skipped_no_text": 0,
                                                                   "errors": 0}

                # ── B. PATIKRINTI AR NĖRA UŽBAIGTŲ UPSERT'Ų ───────────────
                # Pirmiausia pažiūrime ar kuris nors upsert jau baigtas
                done_upserts = []
                remaining_upserts = []
                for fut in active_upserts:
                    if fut.done():
                        done_upserts.append(fut)
                    else:
                        remaining_upserts.append(fut)
                active_upserts = remaining_upserts

                # Apdorojame baigtus upsert'us
                for fut in done_upserts:
                    try:
                        result = fut.result()
                        if result:
                            topic_name, topic_stats, new_ids = result
                            run_stats["new"] += topic_stats["new"]
                            run_stats["skipped"] += topic_stats["skipped_cached"] + topic_stats["skipped_no_text"]
                            run_stats["errors"] += topic_stats["errors"]

                            for pmc_id in new_ids:
                                indexed_ids.add(pmc_id)

                            progress.setdefault("completed_topics", []).append(topic_name)
                            progress.setdefault("stats", {})[topic_name] = {
                                **topic_stats,
                                "timestamp": datetime.now().isoformat(),
                            }
                            save_progress(progress)
                            log.info(f"✓ Upsert fone baigtas: '{topic_name}'")
                    except Exception as e:
                        log.error(f"Upsert fone nepavyko: {e}")
                        run_stats["errors"] += 1

                # ── C. PALEISTI KITO TOPIC'O FETCH'Ą (jei yra) ────────────
                next_idx = idx + PREFETCH_DEPTH
                if next_idx < len(pending):
                    next_topic = pending[next_idx]
                    fut = pipeline_pool.submit(
                        fetch_and_prepare, next_topic, pubmed, indexed_ids
                    )
                    fetch_queue.append((next_topic, fut, None, None))

                # ── D. PALEISTI DABARTINIO TOPIC'O EMBEDDING'Ą (iškart!) ──
                if articles:
                    log.info(f"EMBED QUEUED(parallel): '{cur_topic}' ({len(articles)} articles)")
                    embed_future = embedding_pool.submit(
                        qdrant.embed_articles_bulk, articles
                    )
                    upsert_queue.append(UpsertTask(cur_topic, embed_future, fetch_stats))
                else:
                    # Tuščias topic'as – iškart pažymime kaip baigtą
                    log.info(f"  Nėra naujų straipsnių: '{cur_topic}'")
                    topic_stats = {
                        "new": 0,
                        "skipped_cached": fetch_stats.get("skipped_cached", 0),
                        "skipped_no_text": fetch_stats.get("skipped_no_text", 0),
                        "errors": fetch_stats.get("errors", 0),
                    }
                    run_stats["skipped"] += topic_stats["skipped_cached"] + topic_stats["skipped_no_text"]
                    run_stats["errors"] += topic_stats["errors"]

                    progress.setdefault("completed_topics", []).append(cur_topic)
                    progress.setdefault("stats", {})[cur_topic] = {
                        **topic_stats,
                        "timestamp": datetime.now().isoformat(),
                    }
                    save_progress(progress)

                # ── E. PALEISTI UPSERT'Ą FONE (jei embed jau baigtas) ─────
                # Čia yra KEY: kol upsert vyksta fone, mes tęsiame ciklą
                # ir pradedame kito topic'o embed'inimą

                # Patikriname ar yra upsert'ų, kurių embed jau baigtas
                while upsert_queue:
                    task = upsert_queue[0]
                    if task.embed_future.done():
                        upsert_queue.popleft()
                        try:
                            chunks, vectors, payloads, article_chunk_counts = task.embed_future.result()
                            if chunks:
                                log.info(f"UPSERT (fone): '{task.topic}' ({len(chunks)} chunks)")
                                # Paleidžiame upsert atskirame thread'e – NEBLOKUOJA!
                                upsert_future = upsert_pool.submit(
                                    _do_upsert,
                                    qdrant,
                                    task.topic,
                                    chunks,
                                    vectors,
                                    payloads,
                                    article_chunk_counts,
                                    task.fetch_stats,
                                )
                                active_upserts.append(upsert_future)
                            else:
                                # Nėra chunk'ų – pažymime kaip baigtą
                                topic_stats = {
                                    "new": 0,
                                    "skipped_cached": task.fetch_stats.get("skipped_cached", 0),
                                    "skipped_no_text": task.fetch_stats.get("skipped_no_text", 0),
                                    "errors": task.fetch_stats.get("errors", 0),
                                }
                                run_stats["skipped"] += topic_stats["skipped_cached"] + topic_stats["skipped_no_text"]
                                run_stats["errors"] += topic_stats["errors"]
                                progress.setdefault("completed_topics", []).append(task.topic)
                                progress.setdefault("stats", {})[task.topic] = {
                                    **topic_stats,
                                    "timestamp": datetime.now().isoformat(),
                                }
                                save_progress(progress)
                                log.info(f"  Nėra chunk'ų upsert'ui: '{task.topic}'")
                        except Exception as e:
                            log.error(f"Embedding failed for '{task.topic}': {e}")
                            run_stats["errors"] += 1
                    else:
                        # Pirmas upsert'as dar nebaigtas, laukiame kito karto
                        break

                if DELAY_BETWEEN_TOPICS > 0:
                    time.sleep(DELAY_BETWEEN_TOPICS)

            # ── F. FINAL: UŽBAIGTI VISUS LIKUSIUS UPSERT'US ────────────────
            # Pirmiausia paleidžiame upsert'us tiems, kurių embed baigtas
            while upsert_queue:
                task = upsert_queue.popleft()
                if task.embed_future.done():
                    try:
                        chunks, vectors, payloads, article_chunk_counts = task.embed_future.result()
                        if chunks:
                            log.info(f"UPSERT (final fone): '{task.topic}' ({len(chunks)} chunks)")
                            upsert_future = upsert_pool.submit(
                                _do_upsert,
                                qdrant,
                                task.topic,
                                chunks,
                                vectors,
                                payloads,
                                article_chunk_counts,
                                task.fetch_stats,
                            )
                            active_upserts.append(upsert_future)
                    except Exception as e:
                        log.error(f"Final embedding failed for '{task.topic}': {e}")
                        run_stats["errors"] += 1
                else:
                    # Laukiama kol embed baigsis (blokuojantis, bet jau nedaug)
                    log.info(f"  Laukiama embed pabaigos: '{task.topic}'")
                    try:
                        chunks, vectors, payloads, article_chunk_counts = task.embed_future.result()
                        if chunks:
                            log.info(f"UPSERT (final fone): '{task.topic}' ({len(chunks)} chunks)")
                            upsert_future = upsert_pool.submit(
                                _do_upsert,
                                qdrant,
                                task.topic,
                                chunks,
                                vectors,
                                payloads,
                                article_chunk_counts,
                                task.fetch_stats,
                            )
                            active_upserts.append(upsert_future)
                    except Exception as e:
                        log.error(f"Final embedding failed for '{task.topic}': {e}")
                        run_stats["errors"] += 1

            # Laukiame kol visi upsert'ai fone baigsis
            if active_upserts:
                log.info(f"Laukiama {len(active_upserts)} upsert'ų fone...")
                for fut in as_completed(active_upserts):
                    try:
                        result = fut.result()
                        if result:
                            topic_name, topic_stats, new_ids = result
                            run_stats["new"] += topic_stats["new"]
                            run_stats["skipped"] += topic_stats["skipped_cached"] + topic_stats["skipped_no_text"]
                            run_stats["errors"] += topic_stats["errors"]

                            for pmc_id in new_ids:
                                indexed_ids.add(pmc_id)

                            progress.setdefault("completed_topics", []).append(topic_name)
                            progress.setdefault("stats", {})[topic_name] = {
                                **topic_stats,
                                "timestamp": datetime.now().isoformat(),
                            }
                            save_progress(progress)
                    except Exception as e:
                        log.error(f"Galutinis upsert'as nepavyko: {e}")
                        run_stats["errors"] += 1

        # Run baigtas
        elapsed = (datetime.now() - start_time).total_seconds()
        cache_info = qdrant.cache_stats()

        log.info(f"\n{'=' * 60}")
        log.info(f"Run baigtas [{elapsed:.0f}s]")
        log.info(f"  Nauji straipsniai: {run_stats['new']}")
        log.info(f"  Praleista:         {run_stats['skipped']}")
        log.info(f"  Klaidos:           {run_stats['errors']}")
        log.info(f"  Viso Qdrant:       {cache_info['total_chunks']} chunks")
        log.info(f"  Unikalūs PMC ID:   {len(indexed_ids)}")

        # Išvalome progress po sėkmingo run'o
        save_progress({"completed_topics": [], "stats": {}})

        # Atnaujiname ID cache
        try:
            with open(INDEXED_IDS_CACHE, "w", encoding="utf-8") as f:
                json.dump({"ids": list(indexed_ids), "saved_at": datetime.now().isoformat()}, f)
            log.info(f"ID cache atnaujintas → {INDEXED_IDS_CACHE}")
        except Exception as e:
            log.warning(f"ID cache atnaujinti nepavyko: {e}")

        if once:
            pipeline_pool.shutdown(wait=True)
            embedding_pool.shutdown(wait=True)
            upsert_pool.shutdown(wait=True)
            break

        log.info(f"Kitas run po {interval}s...")
        time.sleep(interval)


def _do_upsert(
    qdrant: QdrantVectorClient,
    topic: str,
    chunks: list[str],
    vectors: list[list[float]],
    payloads: list[dict],
    article_chunk_counts: dict[str, int],
    fetch_stats: dict,
) -> tuple[str, dict, list[str]]:
    """
    UPSERT operacija, vykdoma atskirame thread'e.
    Tai leidžia pagrindiniam thread'ui tęsti darbą (pradėti kitą embedding'ą).
    """
    t0 = time.monotonic()
    qdrant.upsert_points(chunks, vectors, payloads)
    elapsed = time.monotonic() - t0

    topic_stats = {
        "new": len(article_chunk_counts),
        "skipped_cached": fetch_stats.get("skipped_cached", 0),
        "skipped_no_text": fetch_stats.get("skipped_no_text", 0),
        "errors": fetch_stats.get("errors", 0),
    }

    new_ids = list(article_chunk_counts.keys())

    log.info(f"✓ UPSERT baigtas fone: '{topic}' [{elapsed:.1f}s] → {len(new_ids)} straipsniai")

    return topic, topic_stats, new_ids


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
    parser.add_argument("--embed-workers", type=int, default=None,
                        help=f"Kiek embedding thread'ų vienu metu (default: {EMBED_WORKERS})")
    parser.add_argument("--upsert-workers", type=int, default=None,
                        help=f"Kiek upsert thread'ų fone (default: {UPSERT_WORKERS})")
    parser.add_argument("--prefetch", type=int, default=None,
                        help=f"Pipeline prefetch gylis (default: {PREFETCH_DEPTH})")
    args = parser.parse_args()

    if args.reset_progress and Path(PROGRESS_FILE).exists():
        Path(PROGRESS_FILE).unlink()
        log.info("Progress failas išvalytas.")
    if args.reset_progress and Path(INDEXED_IDS_CACHE).exists():
        Path(INDEXED_IDS_CACHE).unlink()
        log.info("ID cache failas išvalytas.")

    if args.embed_workers:
        EMBED_WORKERS = args.embed_workers
    if args.upsert_workers:
        UPSERT_WORKERS = args.upsert_workers
    if args.prefetch:
        PREFETCH_DEPTH = args.prefetch
    if args.topics:
        from MeshParser import get_optimal_topics
        all_topics = get_optimal_topics()
        TOPICS[:] = all_topics[:args.topics]
        log.info(f"Debug režimas: {len(TOPICS)} topic(s)")

    run_indexer(once=not args.loop, interval=args.interval)