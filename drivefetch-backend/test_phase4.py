import asyncio
import os
from dotenv import load_dotenv
from api.recommend_routes import run_recommend_pipeline

load_dotenv()

async def test_end_to_end():
    print("\n--- Testing End-to-End Recommendation Pipeline ---")
    
    user_prompt = "Need a reliable hybrid family car under 60 lacs in Lahore"
    print(f"Query: {user_prompt}\n")
    
    # We will iterate through the AsyncGenerator returned by run_recommend_pipeline
    generator = run_recommend_pipeline(
        user_prompt=user_prompt,
        override_city="Lahore",
        override_budget=6000000
    )
    
    try:
        async for event in generator:
            # event is an SSE string like "event: status\ndata: {...}\n\n"
            print(event.strip())
            print("-" * 40)
    except Exception as e:
        print(f"Pipeline error: {e}")

if __name__ == "__main__":
    asyncio.run(test_end_to_end())
