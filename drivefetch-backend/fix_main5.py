import os

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add get_logger
content = "from core.logger import get_logger\nlogger = get_logger(__name__)\n" + content

# Add global exception handler
exception_handler_code = """
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}",
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "An unexpected error occurred. Our team has been notified.",
            "request_id": str(request.headers.get("x-request-id", "unknown"))
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )
"""

content = content.replace('app.state.limiter = limiter\napp.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)', 'app.state.limiter = limiter\napp.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)\n' + exception_handler_code)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
