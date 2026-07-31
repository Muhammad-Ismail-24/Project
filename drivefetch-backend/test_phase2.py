import asyncio
import os
import json
from dotenv import load_dotenv
from agents.recommender import extract_intent, resolve_constraints, select_car_targets, _deduplicate_and_format_targets

load_dotenv()

async def test_pipeline():
    # Test query that requires mapping "Revo Hilux" to "Hilux" and JDM trims, or single brand dominance
    query = "rugged 4x4 chahiye, northern areas ke liye"
    
    print(f"\n--- Testing Query: '{query}' ---")
    try:
        # Phase 1
        intent = await extract_intent(query)
        print("1. Intent Extracted:", intent.model_dump_json(indent=2))
        
        constraints = resolve_constraints(intent)
        print("2. Constraints Resolved:", json.dumps(constraints, indent=2))
        
        # Phase 2
        raw_targets = await select_car_targets(constraints)
        print("3. Raw Targets from LLM:")
        for t in raw_targets:
            print(f"   - {t.make} {t.model} {t.trim}")
            
        # Canonicalization and formatting
        final_targets = _deduplicate_and_format_targets(raw_targets, constraints)
        print("4. Final 9-Key Canonical Targets:")
        print(json.dumps(final_targets, indent=2))
        
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test_pipeline())
