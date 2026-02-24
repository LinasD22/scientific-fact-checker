# app/api/utils/test.py
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv



sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv(Path(__file__).parent.parent.parent / ".env")  # ← nuskaito app/.env
logging.basicConfig(level=logging.INFO)

from api.services.fact_checker import create_fact_checker

service = create_fact_checker()

# Test 1: Pinecone snippet paieška
print("=== Test 1: Pinecone snippet search ===")
snippets = service.pinecone_client.search_snippets_for_claim(
    claim="Are migraines a leading cause of disability?",
    top_k=3,
)
print(f"Snippets found: {len(snippets)}")
for s in snippets:
    print(f"  [{s['score']:.3f}] {s['source']}: {s['text'][:100]}...")

# Test 2: Pilnas pipeline su Pinecone
print("\n=== Test 2: Full pipeline (Core API → Pinecone → AI) ===")
result = service.check_claim(
    original_claim="Migraines are a leading cause of disability worldwide.", # pvz Vaccines cause autism
    limit=10,
)
print(f"Works searched:  {result.works_searched}")
print(f"Works with text: {result.works_with_text}")
print(f"Snippets used:   {result.snippets_used}")
print(f"Final verdict:   {result.final_verdict}")
print(f"Consensus:       {result.consensus}")
print(f"Agreement score: {result.agreement_score}")
print(f"Summary:         {result.summary}")

print("\nIndividual results:")
for r in result.individual_results:
    score = f"[pinecone: {r['pinecone_score']:.3f}]" if r['pinecone_score'] else ""
    print(f"  {score} {r['source_title']}: {r['result']} (confidence: {r['confidence']})")
    print(f"Source snippet: {r['source_text']}")
    print(f"Explanation: { r['explanation']}")
