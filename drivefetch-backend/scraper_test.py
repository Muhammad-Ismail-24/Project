from curl_cffi import requests
from bs4 import BeautifulSoup
import re
import json

models = [
    ("toyota", "corolla"), ("toyota", "yaris"), ("toyota", "fortuner"), ("toyota", "prado"),
    ("toyota", "vitz"), ("toyota", "aqua"), ("toyota", "hilux"),
    ("honda", "civic"), ("honda", "city"), ("honda", "br-v"), ("honda", "vezel"), ("honda", "hr-v"),
    ("suzuki", "alto"), ("suzuki", "cultus"), ("suzuki", "wagon-r"), ("suzuki", "swift"),
    ("kia", "sportage"), ("kia", "stonic"), 
    ("hyundai", "tucson"), ("hyundai", "elantra"),
    ("haval", "h6"), ("changan", "oshan-x7"), ("mg", "hs")
]

results = {}

session = requests.Session(impersonate="chrome120")

for make, model in models:
    url = f"https://www.pakwheels.com/used-cars/search/-/mk_{make}/md_{model}/"
    print(f"Fetching {url}...")
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Versions are usually in a filter ul or in a tags with vg_
            links = soup.find_all('a', href=True)
            versions = set()
            for link in links:
                href = link['href']
                match = re.search(r'/vg_([^/]+)', href)
                if match:
                    versions.add(match.group(1))
            results[f"{make}:{model}"] = list(versions)
            print(f"  Found versions: {len(versions)}")
        else:
            print(f"  Failed: {resp.status_code}")
    except Exception as e:
        print(f"  Error: {e}")

with open("scraped_versions.json", "w") as f:
    json.dump(results, f, indent=2)

print("Done collecting variants.")
