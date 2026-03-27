# app/api/utils/test.py
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv


sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv(Path(__file__).parent.parent.parent / ".env")  # ← nuskaito app/..env
logging.basicConfig(level=logging.INFO)

from api.services.fact_checker import create_fact_checker
from api.utils.ai_calls import fact_preprocess


claim="VACCINES CAUSE AUTISM!" # pvz Vaccines cause autism



service = create_fact_checker()

#    # Test 1: Qdrant snippet paieška
    # print("=== Test 1: Qdrant snippet search ===")
    # snippets = service.qdrant_client.search_snippets_for_claim(
#     claim="Are migraines a leading cause of disability?",
#     top_k=3,
# )
# print(f"Snippets found: {len(snippets)}")
# for s in snippets:
#     print(f"  [{s['score']:.3f}] {s['source']}: {s['text'][:100]}...")
# claim="Migraines are a leading cause of disability worldwide."



# ================= su fact preprocessing =================
preprocessing_json = fact_preprocess(claim) #################### Change claim
if preprocessing_json["is_health_related"] == "false":
    print("\n\n")
    print("This fact is not related to health.")
    print("\n\n")

    print(f"Justification:\n\t{preprocessing_json["justification"]}")

else:
    # Test 2: Pilnas pipeline su Qdrant
    print("\n=== Test 2: Full pipeline (Core API → Qdrant → AI) ===")
    result = service.check_claim(
        original_claim=claim, # pvz Vaccines cause autism
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
        score = f"[qdrant score: {r['qdrant_score']:.3f}]" if r['qdrant_score'] else ""
        rerank_score = r["rerank_score"]
        print(f"  {score}\n rerank_score: {rerank_score}\n {r['source_title']}: {r['result']} (confidence: {r['confidence']})")
        print(f"Source snippet: {r['source_text']}")
        print(f"Explanation: { r['explanation']}")
