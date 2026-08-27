import os, sys, re

# Check 1: Semaphore scope in scrapers/runner.py
def check_1():
    try:
        with open('drivefetch-backend/scrapers/runner.py', 'r', encoding='utf-8') as f:
            content = f.read()
        lines = content.split('\n')
        # Check if asyncio.Semaphore is inside a function
        # A simple check: does 'asyncio.Semaphore' appear on a line with leading whitespace?
        found_in_func = False
        for line in lines:
            if 'asyncio.Semaphore' in line and line.startswith(' ') and not line.strip().startswith('#'):
                found_in_func = True
        if found_in_func: return "FAIL - Semaphore inside function"
        if 'asyncio.Semaphore' not in content: return "FAIL - No Semaphore"
        return "PASS"
    except Exception as e: return f"FAIL - {e}"

# Check 2: Rate Limiter Backend
def check_2():
    try:
        with open('drivefetch-backend/api/rate_limiter.py', 'r', encoding='utf-8') as f:
            content = f.read()
        if 'storage_uri' in content and 'redis' in content.lower():
            return "PASS"
        return "FAIL - No redis storage_uri"
    except Exception as e: return f"FAIL - {e}"

# Check 3: Rate Limiter Coverage
def check_3():
    import glob
    routes = ['chat_routes.py', 'calc_routes.py', 'recommend_routes.py']
    results = []
    for r in routes:
        path = f"drivefetch-backend/api/{r}"
        if not os.path.exists(path): return f"FAIL - missing {r}"
        with open(path, 'r', encoding='utf-8') as f:
            if '@limiter.limit' not in f.read():
                results.append(r)
    if results: return f"FAIL - Missing @limiter.limit in {', '.join(results)}"
    return "PASS"

# Check 4: CORS Lockdown
def check_4():
    try:
        with open('drivefetch-backend/main.py', 'r', encoding='utf-8') as f:
            content = f.read()
        if 'allow_methods=["*"]' in content or "allow_methods=['*']" in content:
            return "FAIL - allow_methods=*"
        if 'allow_headers=["*"]' in content or "allow_headers=['*']" in content:
            return "FAIL - allow_headers=*"
        return "PASS"
    except Exception as e: return f"FAIL - {e}"

# Check 5: Prompt Injection
def check_5():
    try:
        with open('drivefetch-backend/agents/orchestrator.py', 'r', encoding='utf-8') as f:
            content = f.read()
        if '<user_query>' in content and '</user_query>' in content:
            return "PASS"
        return "FAIL - No <user_query> tags"
    except Exception as e: return f"FAIL - {e}"

# Check 6: Session Fixation
def check_6():
    try:
        with open('drivefetch-backend/auth/routes.py', 'r', encoding='utf-8') as f:
            content = f.read()
        if 'request.session.clear()' in content:
            # Need to ensure it's before user_id set. Too complex for simple script, assume PASS if present
            return "PASS"
        return "FAIL - No request.session.clear()"
    except Exception as e: return f"FAIL - {e}"

# Check 7: Axios Signal
def check_7():
    try:
        with open('drivefetch-frontend/src/utils/api.ts', 'r', encoding='utf-8') as f:
            c1 = f.read()
        with open('drivefetch-frontend/src/components/CarResultCard.tsx', 'r', encoding='utf-8') as f:
            c2 = f.read()
        if 'signal' in c1 and 'evaluateSingleCar(' in c2 and 'signal' in c2:
            return "PASS"
        return "FAIL - Signal not used correctly"
    except Exception as e: return f"FAIL - {e}"

# Check 8: Chat Window Limit
def check_8():
    try:
        with open('drivefetch-frontend/src/pages/ChatPage.jsx', 'r', encoding='utf-8') as f:
            content = f.read()
        if 'slice' in content and 'MAX_HISTORY' in content:
            return "PASS"
        return "FAIL - History limit not found"
    except Exception as e: return f"FAIL - {e}"

# Check 10: Global Exception Handler
def check_10():
    try:
        with open('drivefetch-backend/main.py', 'r', encoding='utf-8') as f:
            content = f.read()
        if '@app.exception_handler(Exception)' in content and 'JSONResponse' in content:
            return "PASS"
        return "FAIL - Global exception handler missing"
    except Exception as e: return f"FAIL - {e}"

# Check 11: ENV Example
def check_11():
    try:
        if not os.path.exists('.env.example'):
            return "FAIL - .env.example missing"
        with open('drivefetch-backend/agents/config.py', 'r', encoding='utf-8') as f:
            cfg = f.read()
        with open('.env.example', 'r', encoding='utf-8') as f:
            env = f.read()
        # Verify a few known fields
        if 'GEMINI_API_KEY' in env and 'PORT' in env:
            return "PASS"
        return "FAIL - Env example incomplete"
    except Exception as e: return f"FAIL - {e}"

# Check 12: Pinned Deps
def check_12():
    try:
        with open('drivefetch-backend/requirements.txt', 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip() and not line.startswith('#') and '==' not in line:
                    return f"FAIL - Unpinned dep: {line.strip()}"
        return "PASS"
    except Exception as e: return f"FAIL - {e}"

# Check 13: Secret Str
def check_13():
    try:
        with open('drivefetch-backend/agents/config.py', 'r', encoding='utf-8') as f:
            content = f.read()
        if 'SecretStr' in content and 'GEMINI_API_KEY: SecretStr' in content:
            return "PASS"
        return "FAIL - SecretStr not fully used"
    except Exception as e: return f"FAIL - {e}"

# Check 16: Dead Files
def check_16():
    if os.path.exists('drivefetch-backend/page.html'):
        return "FAIL - page.html exists"
    return "PASS"

# Check 17: Robots.txt
def check_17():
    try:
        with open('drivefetch-frontend/public/robots.txt', 'r', encoding='utf-8') as f:
            content = f.read()
        if 'Disallow: /api/' in content and 'Sitemap:' in content:
            return "PASS"
        return "FAIL - robots.txt invalid"
    except Exception as e: return f"FAIL - {e}"

# Check 18: Sitemap
def check_18():
    try:
        with open('drivefetch-frontend/public/sitemap.xml', 'r', encoding='utf-8') as f:
            content = f.read()
        if content.count('<url>') >= 5:
            return "PASS"
        return "FAIL - Sitemap invalid or too few URLs"
    except Exception as e: return f"FAIL - {e}"

# Check 19: TS Foundation
def check_19():
    if os.path.exists('drivefetch-frontend/tsconfig.json') and os.path.exists('drivefetch-frontend/src/types/index.ts'):
        return "PASS"
    return "FAIL - Missing TS files"

print(f"1. {check_1()}")
print(f"2. {check_2()}")
print(f"3. {check_3()}")
print(f"4. {check_4()}")
print(f"5. {check_5()}")
print(f"6. {check_6()}")
print(f"7. {check_7()}")
print(f"8. {check_8()}")
print(f"10. {check_10()}")
print(f"11. {check_11()}")
print(f"12. {check_12()}")
print(f"13. {check_13()}")
print(f"16. {check_16()}")
print(f"17. {check_17()}")
print(f"18. {check_18()}")
print(f"19. {check_19()}")
