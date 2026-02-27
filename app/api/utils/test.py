import logging
import os
import sys
from pathlib import Path
from threading import Thread
from time import sleep

from dotenv import load_dotenv


sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv(Path(__file__).parent.parent.parent / ".env")  # ← nuskaito app/.env
logging.basicConfig(level=logging.INFO)

from api.services.fact_checker import create_fact_checker
from api.utils.ai_calls import fact_preprocess

claims = ['Migraines are a leading cause of disability worldwide.',
          'Vaccines cause autism']

claim = claims[1]


service = create_fact_checker()


# ================= su fact preprocessing =================
preprocessing_json = fact_preprocess(claim) #################### Change claim
sleep(5)
if preprocessing_json["is_health_related"] == "false":
    print("\n\n")
    print("This fact is not related to health.")
    print("\n\n")

    print(f"Justification:\n\t{preprocessing_json['justification']}")

else:

    print("\n=== Test 2: Full pipeline (Core API → Pinecone → AI) ===")
    result = service.check_claim(
        original_claim=claim, # pvz Vaccines cause autism
        limit=3,
    )
    print(f"Original claim: {claim}")
    print(f"Works searched:  {result.works_searched}")
    print(f"Works with text: {result.works_with_text}")
    print(f"Snippets used:   {result.snippets_used}")
    print(f"Final verdict:   {result.final_verdict}")
    print(f"Agreement score: {result.agreement_score}")
    print(f"Summary:         {result.summary}")

    print("\nIndividual results:")
    for r in result.individual_results:
        score = f"[pinecone: {r['pinecone_score']:.3f}]" if r['pinecone_score'] else ""
        print(f"  {score} {r['source_title']} {r['citations']}: {r['result']} (confidence: {r['confidence']})")
        print(f"Source snippet: {r['source_text']}")
        print(f"Explanation: { r['explanation']}")