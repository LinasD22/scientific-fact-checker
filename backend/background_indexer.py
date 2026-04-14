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
from mesh import *
from datetime import datetime
from pathlib import Path

from MeshParser import get_optimal_topics

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from api.utils.pubmed_api_client import PubMedAPIClient
from api.utils.qdrant_vector_client import QdrantVectorClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("background_indexer.log"),
    ],
)
log = logging.getLogger(__name__)

# ── Konfigūracija ─────────────────────────────────────────────────────────────

# Straipsnių kiekis per topic per run (PubMed rate limit: 10 req/s su API key)
ARTICLES_PER_TOPIC = int(os.getenv("INDEXER_ARTICLES_PER_TOPIC", "50"))

# Pauzė tarp topic'ų (sekundės) — kad nepersikrautų PubMed
DELAY_BETWEEN_TOPICS = float(os.getenv("INDEXER_TOPIC_DELAY", "2.0"))

# Pauzė tarp straipsnių fetch'inimo
DELAY_BETWEEN_ARTICLES = float(os.getenv("INDEXER_ARTICLE_DELAY", "0.5"))

# Progress failo kelias
PROGRESS_FILE = os.getenv("INDEXER_PROGRESS_FILE", "indexer_progress.json")


TOPICS = []


# ── Text cleaning ─────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Valo tekstą prieš embed'inimą."""
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\x0c', '\n', text)  # PDF form feed artefaktai
    text = re.sub(r'\s+\.\s+', '. ', text)  # spaces around periods
    return text.strip()


# ── Progress tracking ─────────────────────────────────────────────────────────

def load_progress() -> dict:
    if Path(PROGRESS_FILE).exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"indexed_pmc_ids": [], "completed_topics": [], "stats": {}}


def save_progress(progress: dict) -> None:
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


# ── Qdrant helpers ────────────────────────────────────────────────────────────

def is_pmc_indexed(qdrant: QdrantVectorClient, pmc_id: str) -> bool:
    """Tikrina ar pmc_id jau yra Qdrant kolekcijoje."""
    try:
        results = qdrant.client.scroll(
            collection_name="fact_checker_cache",
            scroll_filter=Filter(must=[
                FieldCondition(
                    key="source_id",
                    match=MatchValue(value=pmc_id),
                )
            ]),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        return len(results[0]) > 0
    except Exception as e:
        log.warning(f"Klaida tikrinant cache pmc_id={pmc_id}: {e}")
        return False


def index_article(
        qdrant: QdrantVectorClient,
        article: dict,
        pmc_id: str,
) -> bool:
    """
    Indeksuoja vieną straipsnį į Qdrant.
    Grąžina True jei sėkmingai indeksuota, False jei praleista.
    """
    title = article.get("title") or "Unknown"
    full_text = article.get("full_text") or ""
    abstract = article.get("abstract") or ""

    # Pirmenybė full_text, fallback į abstract
    text = clean_text(full_text) if full_text else clean_text(abstract)

    if not text:
        log.debug(f"Praleista (nėra teksto): {title[:60]}")
        return False

    fingerprint = qdrant._fingerprint(title, text)

    # Papildomas check pagal fingerprint (tuo atveju jei source_id indeksas dar nebuvo)
    if qdrant._is_cached(fingerprint):
        log.debug(f"Jau indeksuota (fingerprint): {title[:60]}")
        return False

    n_chunks = qdrant._store_work(
        title=title,
        text=text,
        fingerprint=fingerprint,
        source_db="pubmed_bulk",
        source_id=pmc_id,
    )

    log.info(f"  ✓ [{pmc_id}] {title[:70]} → {n_chunks} chunks")
    return True


# ── Pagrindinis indexer ───────────────────────────────────────────────────────

def index_topic(
        topic: str,
        pubmed: PubMedAPIClient,
        qdrant: QdrantVectorClient,
        progress: dict,
        limit: int = ARTICLES_PER_TOPIC,
) -> dict:
    """Indeksuoja vieno topic'o straipsnius. Grąžina statistiką."""
    stats = {"new": 0, "skipped_cached": 0, "skipped_no_text": 0, "errors": 0}

    log.info(f"\n{'─' * 60}")
    log.info(f"Topic: '{topic}' (limit={limit})")

    try:
        article_ids = pubmed.search_article_ids(topic, limit=limit)
    except Exception as e:
        log.error(f"esearch nepavyko: {e}")
        stats["errors"] += 1
        return stats

    log.info(f"Rasta {len(article_ids)} straipsnių IDs")
    already_indexed = set(progress.get("indexed_pmc_ids", []))

    for pmc_id in article_ids:
        # Greitas check iš progress failo (be Qdrant query)
        if pmc_id in already_indexed:
            log.debug(f"  Skip (progress): {pmc_id}")
            stats["skipped_cached"] += 1
            continue

        # Tikrina Qdrant (tuo atveju jei progress failas neaktualus)
        if is_pmc_indexed(qdrant, pmc_id):
            log.debug(f"  Skip (qdrant): {pmc_id}")
            already_indexed.add(pmc_id)
            stats["skipped_cached"] += 1
            continue

        try:
            content = pubmed.fetch_article_content(pmc_id)
            time.sleep(DELAY_BETWEEN_ARTICLES)

            if not content:
                stats["skipped_no_text"] += 1
                continue

            content["pmc_id"] = pmc_id
            success = index_article(qdrant, content, pmc_id)

            if success:
                stats["new"] += 1
                progress["indexed_pmc_ids"].append(pmc_id)
            else:
                stats["skipped_no_text"] += 1

        except Exception as e:
            log.warning(f"  Klaida [{pmc_id}]: {e}")
            stats["errors"] += 1
            time.sleep(1)  # backoff po klaidos
            continue

    return stats


def run_indexer(once: bool = True, interval: int = 3600) -> None:
    """
    Paleidžia background indexer'į.

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
    log.info(f"  Režimas: {'vienkartinis' if once else f'kas {interval}s'}")

    while True:
        progress = load_progress()
        run_stats = {"new": 0, "skipped": 0, "errors": 0}
        start_time = datetime.now()

        completed = set(progress.get("completed_topics", []))

        for topic in TOPICS:
            if topic in completed:
                log.info(f"Topic jau atliktas šiame run'e: '{topic}'")
                continue

            topic_stats = index_topic(topic, pubmed, qdrant, progress)

            run_stats["new"] += topic_stats["new"]
            run_stats["skipped"] += topic_stats["skipped_cached"] + topic_stats["skipped_no_text"]
            run_stats["errors"] += topic_stats["errors"]

            progress.setdefault("completed_topics", []).append(topic)
            progress.setdefault("stats", {})[topic] = {
                **topic_stats,
                "timestamp": datetime.now().isoformat(),
            }
            save_progress(progress)

            time.sleep(DELAY_BETWEEN_TOPICS)

        # Run baigtas — reset completed topics kitam run'ui
        progress["completed_topics"] = []
        elapsed = (datetime.now() - start_time).total_seconds()

        cache_info = qdrant.cache_stats()
        log.info(f"\n{'=' * 60}")
        log.info(f"Run baigtas [{elapsed:.0f}s]")
        log.info(f"  Nauji chunks: {run_stats['new']}")
        log.info(f"  Praleista:    {run_stats['skipped']}")
        log.info(f"  Klaidos:      {run_stats['errors']}")
        log.info(f"  Viso Qdrant:  {cache_info['total_chunks']} chunks")
        save_progress(progress)

        if once:
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
        # Debug režimas — apriboja topic sąrašą
        original = TOPICS.copy()
        TOPICS[:] = TOPICS[:args.topics]
        log.info(f"Debug režimas: {len(TOPICS)} topic(s)")

    run_indexer(once=not args.loop, interval=args.interval)