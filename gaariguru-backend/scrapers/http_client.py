"""
scrapers/http_client.py
Restored to WorkDone.md Original Spec: Dual-Layer Stealth Fetcher.
Uses aiohttp for fast requests, and a stealth-patched headless Playwright for JS-rendered pages.
"""
import aiohttp
import asyncio
from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth  

async def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/"
    }
    use_fallback = False
    html_content = ""
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as response:
                if response.status in [401, 403]:
                    use_fallback = True
                else:
                    html_content = await response.text()
                    if "cf-browser-verification" in html_content or "challenges.cloudflare.com" in html_content or len(html_content) < 500:
                        use_fallback = True
    except Exception:
        use_fallback = True

    if use_fallback:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
                context = await browser.new_context(viewport={"width": 1280, "height": 800})
                page = await context.new_page()
                await Stealth().apply_stealth_async(page)
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                html_content = await page.content()
                await browser.close()
                return html_content
        except Exception:
            return ""
    return html_content

async def fetch_page_content(context, url: str, selector: str) -> str:
    page = await context.new_page()
    try:
        await Stealth().apply_stealth_async(page)
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception:
            pass

        # Wait out the Cloudflare screen natively without fancy mouse movements
        initial_html = await page.content()
        if "cf-browser-verification" in initial_html or "challenges.cloudflare.com" in initial_html or "Just a moment" in initial_html:
            print(f"[Runner] Cloudflare intercept detected for {url}, waiting for native resolution...")
            await page.wait_for_timeout(10000)

        try:
            await page.wait_for_selector(selector, timeout=15000)
        except PlaywrightTimeoutError:
            print(f"[Runner] ⚠ Wait selector timed out for {url}. Grabbing HTML anyway.")

        html = await page.content()
        return html
    except Exception as e:
        print(f"[Runner] Fatal Playwright fetch error for {url}: {e}")
        return ""
    finally:
        await page.close()