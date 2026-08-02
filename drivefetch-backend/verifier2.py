from curl_cffi import requests
from bs4 import BeautifulSoup

def verify_pw_slug(make, model, slug):
    url = f"https://www.pakwheels.com/used-cars/search/-/mk_{make}/md_{model}/vg_{slug}/"
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            h1 = soup.find('h1')
            if h1 and "for sale" in h1.text.lower():
                return True
    except:
        pass
    return False

session = requests.Session(impersonate="chrome120")

tests = [
    ("toyota", "yaris", "ativ"),
    ("toyota", "yaris", "ativ-x"),
    ("toyota", "yaris", "gli"),
    ("toyota", "corolla", "altis"),
    ("toyota", "fortuner", "g"),
    ("toyota", "fortuner", "2-7-vvti"),
    ("toyota", "vitz", "f"),
    ("toyota", "aqua", "g"),
    ("toyota", "hilux", "revo-g"),
    ("honda", "civic", "turbo"),
    ("honda", "civic", "vti"),
    ("honda", "civic", "exi"),
    ("honda", "city", "i-dsi"),
    ("honda", "city", "aspire"),
    ("honda", "city", "1-2l"),
    ("honda", "city", "1-5l"),
    ("honda", "br-v", "i-vtec"),
    ("honda", "vezel", "x"),
    ("honda", "vezel", "e-hev"),
    ("honda", "hr-v", "vti"),
    ("suzuki", "alto", "vxr"),
    ("suzuki", "alto", "vxl-ags"),
    ("suzuki", "cultus", "auto-gear-shift"),
    ("suzuki", "swift", "dlx"),
    ("kia", "sportage", "alpha"),
    ("kia", "stonic", "ex"),
    ("hyundai", "tucson", "gls-sport"),
    ("hyundai", "elantra", "1-6-gl"),
    ("haval", "h6", "1-5t"),
    ("haval", "h6", "hev"),
    ("changan", "oshan-x7", "future-sense"),
    ("mg", "hs", "exclusive")
]

for make, model, slug in tests:
    res = verify_pw_slug(make, model, slug)
    print(f"{make} {model} {slug} -> {'Valid' if res else 'Invalid'}")
