import re, json

with open(r'C:\Users\123\.gemini\antigravity-cli\brain\61419938-09fa-4c94-8bf1-4e4ec12fa892\.system_generated\steps\4143\content.md', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the canonical URL (contains the city slug with _g{id})
canonical = re.search(r'<link rel="canonical" href="([^"]+)"', content)
if canonical:
    print(f"Canonical: {canonical.group(1)}")

# Find the loc_id and loc_name from dataLayer
loc_id = re.search(r'"loc_id":"(\d+)"', content)
loc_name = re.search(r'"loc_name":"([^"]+)"', content)
if loc_id and loc_name:
    print(f"City: {loc_name.group(1)}, External ID: {loc_id.group(1)}")

# Find all location slugs mentioned on the page
slugs = re.findall(r'([a-z-]+_g\d{7})', content)
unique_slugs = sorted(set(slugs))
print(f"\nAll slugs found on page ({len(unique_slugs)}):")
for s in unique_slugs:
    print(f"  {s}")

# Try to extract the locations data from window.state
match = re.search(r'window\.state\s*=\s*(\{.*?\});', content, re.DOTALL)
if match:
    data = json.loads(match.group(1))
    
    # Check locations key
    locations = data.get('locations', {})
    print(f"\nlocations key type: {type(locations).__name__}, keys: {list(locations.keys())[:10]}")
    
    # Check if there's location data in the content
    loc_data = locations.get('data', locations.get('content', None))
    if loc_data:
        print(f"Location data found: {type(loc_data)}")
        if isinstance(loc_data, list):
            for loc in loc_data[:5]:
                print(f"  {json.dumps(loc, ensure_ascii=False)[:200]}")
    
    # Also check the algolia facets for location data
    facets = data.get('algolia', {}).get('content', {}).get('facets', {})
    lvl2 = facets.get('location.lvl2', [])
    print(f"\nFacet location.lvl2 entries: {len(lvl2) if isinstance(lvl2, list) else 'N/A'}")
    if isinstance(lvl2, list):
        for loc in lvl2[:30]:
            if isinstance(loc, dict):
                val = loc.get('value', {})
                if isinstance(val, dict):
                    print(f"  {val.get('name', '?')}: externalID={val.get('externalID', '?')}, slug={val.get('slug', '?')}")
                else:
                    print(f"  key={loc.get('key')}, value={val}, count={loc.get('count')}")

    # Check the dataLayer for location breadcrumb which has hierarchical IDs
    print("\n=== Searching for province/region level locations ===")
    lvl1 = facets.get('location.lvl1', [])
    if isinstance(lvl1, list):
        for loc in lvl1:
            if isinstance(loc, dict):
                val = loc.get('value', {})
                if isinstance(val, dict):
                    print(f"  Province: {val.get('name')}, externalID={val.get('externalID')}")
    
    # Try to find ALL location references in the router or other keys
    router = data.get('router', {})
    print(f"\nRouter keys: {list(router.keys())[:10]}")
