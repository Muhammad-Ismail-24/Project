import asyncio
from agents.recommender import recommend_cars

async def main():
    print("Testing Recommend Pipeline with Range Rover 4 Crore")
    try:
        # recommend_cars is a generator
        async for chunk in recommend_cars("Range Rover 4 Crore"):
            print(chunk)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
