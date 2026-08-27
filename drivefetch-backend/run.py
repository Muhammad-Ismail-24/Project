import sys
import os
import asyncio
import uvicorn
from core.logger import get_logger

logger = get_logger(__name__)

# 1. Force the correct Windows loop BEFORE Uvicorn starts
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 2. Start the Uvicorn server manually, after the policy is already set
from agents.config import settings
if __name__ == "__main__":
    logger.info("🚀 [Startup] Starting Drive Fetch with Windows Subprocess Support...")
    port = settings.port
    host = settings.host
    
    # ProxyHeadersMiddleware in main.py now handles proxy headers safely
    uvicorn.run(
        "main:app", 
        host=host, 
        port=port, 
        reload=False
    )