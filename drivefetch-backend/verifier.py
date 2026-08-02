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

# Testing a few known tricky ones to prove verification
tests = [
    ("toyota", "corolla", "1-3-gli"),
    ("toyota", "corolla", "altis-grande"),
    ("toyota", "fortuner", "sigma-3"),
    ("toyota", "fortuner", "legender"),
    ("honda", "civic", "rs-turbo"),
    ("honda", "civic", "oriel"),
    ("suzuki", "cultus", "vxl"),
    ("kia", "sportage", "awd")
]

for make, model, slug in tests:
    res = verify_pw_slug(make, model, slug)
    print(f"{make} {model} {slug} -> {'Valid' if res else 'Invalid'}")
