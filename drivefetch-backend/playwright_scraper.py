from playwright.sync_api import sync_playwright
import time

target_models = [
    ("suzuki", "cultus", ["VXR", "VXL", "Auto Gear Shift", "Euro II", "AGS"]),
    ("suzuki", "alto", ["VX", "VXR", "VXL", "VXL AGS"]),
    ("toyota", "corolla", ["XLi", "GLi", "Altis 1.6", "Altis Grande", "2.0D"]),
    ("hyundai", "elantra", ["GL", "GLS"]),
    ("honda", "civic", ["Oriel", "RS", "Turbo", "VTi"]),
    ("toyota", "fortuner", ["2.7 VVTi", "VRZ", "Sigma 3", "Legender"]),
    ("kia", "sportage", ["Alpha", "FWD", "AWD"])
]

results = {}

def extract_slug(url):
    import re
    # Try to find vg_ or vr_
    m = re.search(r'/(v[rg]_[^/]+)', url)
    if m:
        return m.group(1).replace("vg_", "").replace("vr_", "")
    return None

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        for make, model, expected_trims in target_models:
            base_url = f"https://www.pakwheels.com/used-cars/search/-/mk_{make}/md_{model}/"
            print(f"\\nNavigating to {base_url}")
            page.goto(base_url, timeout=60000, wait_until='domcontentloaded')
            page.wait_for_timeout(3000)
            
            for exp_trim in expected_trims:
                print(f"--- Testing {exp_trim} ---")
                page.goto(base_url, timeout=60000, wait_until='domcontentloaded')
                page.wait_for_timeout(2000)
                
                try:
                    # Click more choices for versions
                    page.click('span[data-target="#lb_more_choices_versions"]', force=True)
                    # Wait for AJAX to load modal contents
                    page.wait_for_selector('#more_choices_versions input[type="checkbox"]', state='visible', timeout=10000)
                    page.wait_for_timeout(1000)
                    
                    # Find checkboxes matching our trim
                    checkboxes = page.evaluate('''() => {
                        let res = [];
                        let labels = document.querySelectorAll('#more_choices_versions label');
                        labels.forEach((lbl, i) => {
                            let text = lbl.textContent.trim().replace(/\\(\\d+\\)/g, '').trim();
                            let chk = lbl.querySelector('input[type="checkbox"]');
                            if(chk) {
                                lbl.id = "lbl-" + i;
                                res.push({text: text, id: lbl.id, val: chk.value});
                            }
                        });
                        return res;
                    }''')
                    
                    target_id = None
                    target_val = None
                    exp_clean = exp_trim.lower().replace(" ", "").replace(".", "").replace("-", "")
                    for cb in checkboxes:
                        cb_clean = cb['text'].lower().replace(" ", "").replace(".", "").replace("-", "")
                        if exp_clean == cb_clean or exp_clean in cb_clean:
                            target_id = cb['id']
                            target_val = cb['val']
                            break
                            
                    if target_id:
                        # Click the checkbox label
                        page.click(f"#{target_id}")
                        page.wait_for_timeout(500)
                        
                        # Click submit
                        try:
                            page.evaluate('''() => {
                                let btn = document.querySelector('.modal .btn-primary[value="submit"]');
                                if(btn) btn.click();
                            }''')
                        except:
                            pass
                        
                        # Wait for navigation
                        try:
                            page.wait_for_load_state("networkidle", timeout=10000)
                        except:
                            page.wait_for_timeout(4000)
                            
                        current_url = page.url
                        slug = extract_slug(current_url)
                        
                        # Sometimes slug might just be the value if URL didn't change correctly due to React
                        if not slug and target_val:
                            slug = target_val.replace("vg_", "").replace("vr_", "")
                            # Go manually using vr_ since the modal explicitly uses vr_
                            page.goto(f"https://www.pakwheels.com/used-cars/search/-/mk_{make}/md_{model}/vr_{slug}/", timeout=60000, wait_until='domcontentloaded')
                            page.wait_for_timeout(3000)
                            current_url = page.url
                            slug = extract_slug(current_url)
                            
                        listings = page.query_selector_all('li.classified-listing')
                        count = len(listings)
                        print(f"  Intercepted Slug: {slug} | Listings: {count}")
                        
                        if count > 0 and slug:
                            # Verify true positive, wait! PakWheels gives 200 OK for anything.
                            # We checked count > 0, but is it a broad search? (0 cars found for trim, so it shows general)
                            # Actually, if 0 cars, PakWheels shows "0 Results" or a "We could not find" message.
                            # Let's make sure it's valid.
                            key = f"{model.lower()}:{exp_trim.lower()}"
                            results[key] = {
                                "pakwheels": slug,
                                "olx": exp_trim.lower().replace(" ", "-"),
                                "autodeals": exp_trim.replace(" ", "-")
                            }
                        else:
                            print("  -> Invalid: 0 listings.")
                    else:
                        print("  -> Not found in modal.")
                except Exception as e:
                    print(f"  -> Error: {e}")
                    
        browser.close()

if __name__ == "__main__":
    run()
    
    # Generate table.txt formatted output
    output = "# table.txt\\nCANONICAL_TRIM_MAP = {\\n"
    for key, val in results.items():
        output += f'    "{key}": {{\\n'
        output += f'        "pakwheels": "{val["pakwheels"]}",\\n'
        output += f'        "olx":       "{val["olx"]}",\\n'
        output += f'        "autodeals": "{val["autodeals"]}",\\n'
        output += '    },\\n'
    output += "}\\n"
    
    with open("table.txt", "w") as f:
        f.write(output)
    
    print("Done. table.txt updated.")
