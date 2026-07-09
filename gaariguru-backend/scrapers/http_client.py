"""
scrapers/http_client.py

Migrated from Playwright to curl_cffi.
curl_cffi impersonates a real Chrome TLS fingerprint, bypassing Cloudflare
without needing a headless browser (saving ~400MB RAM on the server).
"""
from curl_cffi.requests import AsyncSession

CHROME_IMPERSONATE = "chrome120"
REQUEST_TIMEOUT = 20  # seconds


async def fetch_html(url: str) -> str:
    """
    Fetches HTML from a URL using curl_cffi with Chrome TLS fingerprint impersonation.
    Returns the HTML string, or an empty string on failure.
    """
    try:
        async with AsyncSession(impersonate=CHROME_IMPERSONATE) as session:
            response = await session.get(url, timeout=REQUEST_TIMEOUT)

            if response.status_code in (401, 403):
                print(f"[HTTP Client] Blocked ({response.status_code}) for {url}")
                return ""

            html = response.text
            if not html or len(html) < 500:
                print(f"[HTTP Client] Response too short ({len(html) if html else 0} chars) for {url}")
                return ""

            # Detect Cloudflare challenge pages
            if "cf-browser-verification" in html or "challenges.cloudflare.com" in html:
                print(f"[HTTP Client] Cloudflare challenge detected for {url}")
                return ""

            return html

    except Exception as e:
        print(f"[HTTP Client] Request failed for {url}: {e}")
        return ""