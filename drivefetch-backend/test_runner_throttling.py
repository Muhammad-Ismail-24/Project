import asyncio
import os
from scrapers.runner import execute_search_pipeline

async def main():
    try:
        # Pass basic arguments that won't require DB or AI depending on their fallback behavior
        clean, empty = await execute_search_pipeline("Toyota", "Corolla", "Lahore", max_budget=2000000, min_budget=1000000)
        print(f"Scraped {len(clean)} listings.")
    except Exception as e:
        print(f"Failed with exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
