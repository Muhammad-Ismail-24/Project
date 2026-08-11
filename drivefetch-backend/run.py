import sys
import os
import asyncio
import uvicorn

# 1. Force the correct Windows loop BEFORE Uvicorn starts
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 2. Start the Uvicorn server manually, after the policy is already set
from agents.config import settings
if __name__ == "__main__":
    print("🚀 [Startup] Starting Drive Fetch with Windows Subprocess Support...")
    port = settings.port
    host = settings.host
    
    # Added proxy_headers=True and forwarded_allow_ips
    uvicorn.run(
        "main:app", 
        host=host, 
        port=port, 
        reload=False, 
        proxy_headers=True, 
        forwarded_allow_ips="*"
    )