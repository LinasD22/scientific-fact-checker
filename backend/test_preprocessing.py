"""
Test script for preprocessing - breaking text into individual facts.
"""
import sys
from pathlib import Path

# Load .env file first, before any imports that depend on it
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.utils.ai_calls import extract_individual_facts

# Test cases
test_cases = [
    "Vaccines are safe and effective. They are developed through rigorous testing protocols. Autism is not caused by vaccines.",
    "Water boils at 100 degrees Celsius at sea level. The human body contains about 60% water.",
    "Migraines are a leading cause of disability worldwide. They affect approximately 1 in 10 people. Treatment options include preventive medications.",
]

print("=== Testing Fact Extraction (Preprocessing) ===\n")

for i, text in enumerate(test_cases, 1):
    print(f"\n--- Test Case {i} ---")
    print(f"Original text: {text}\n")
    
    try:
        result = extract_individual_facts(text)
        facts = result.get("facts", [])
        
        print(f"Extracted {len(facts)} individual fact(s):")
        for j, fact in enumerate(facts, 1):
            print(f"  {j}. {fact}")
    
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

print("\n=== Test Complete ===")
