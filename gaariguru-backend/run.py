import sys
import os
import asyncio
import uvicorn

# 1. Force the correct Windows loop BEFORE Uvicorn starts
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 2. Start the Uvicorn server manually, after the policy is already set
if __name__ == "__main__":
    print("🚀 [Startup] Starting GaariGuru with Windows Subprocess Support...")
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    # CRITICAL FIX: reload MUST be False on Windows when using Playwright.
    # If True, Uvicorn spawns a child process that forgets the Proactor loop policy!
    uvicorn.run("main:app", host=host, port=port, reload=False)