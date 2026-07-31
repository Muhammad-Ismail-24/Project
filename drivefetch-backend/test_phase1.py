import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from agents.recommender import extract_intent, resolve_constraints

async def test_pipeline():
    test_queries = [
        "I need a fast luxury sedan under 5 crore",
        "cheap automatic for a student, budget 18 lacs",
        "Chinese electric crossover",
        "rugged 4x4 chahiye, northern areas ke liye"
    ]
    
    for query in test_queries:
        print(f"\n--- Testing Query: '{query}' ---")
        try:
            intent = await extract_intent(query)
            print("1. Intent Extracted:", intent.model_dump_json(indent=2))
            
            constraints = resolve_constraints(intent)
            print("2. Constraints Resolved:", constraints)
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test_pipeline())
