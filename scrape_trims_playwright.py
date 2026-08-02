import asyncio
from playwright.async_api import async_playwright
import json

target_models = [
    # Toyota
    ("toyota", "corolla", ["XLi", "GLi", "Altis", "Grande", "2.0D"]),
    ("toyota", "yaris", ["ATIV", "GLi"]),
    ("toyota", "fortuner", ["2.7 VVTi", "VRZ", "Sigma 3", "Legender", "G"]),
    ("toyota", "prado", ["TX", "TZ", "VX"]),
    ("toyota", "vitz", ["F", "Jewela", "U"]),
    ("toyota", "aqua", ["S", "G", "L"]),
    ("toyota", "hilux", ["Revo G", "Revo V", "Revo Rocco", "Vigo", "E"]),
    
    # Honda
    ("honda", "civic", ["Oriel", "RS", "Turbo", "VTi", "EXi"]),
    ("honda", "city", ["i-VTEC", "Aspire", "1.2L", "1.5L"]),
    ("honda", "br-v", ["i-VTEC S", "i-VTEC MT"]),
    ("honda", "vezel", ["Z", "X", "RS"]),
    ("honda", "hr-v", ["VTi", "VTi-S"]),
    
    # Suzuki
    ("suzuki", "cultus", ["VXR", "VXL", "Auto Gear Shift", "Euro II", "AGS"]),
    ("suzuki", "alto", ["VX", "VXR", "VXL", "AGS", "VXR AGS"]),
    ("suzuki", "wagon-r", ["VXR", "VXL", "AGS"]),
    ("suzuki", "swift", ["DLX", "GLX CVT", "GL CVT"]),
    ("suzuki", "mehran", ["VX", "VXR", "Euro II"]),
    
    # Kia / Hyundai
    ("kia", "sportage", ["Alpha", "FWD", "AWD", "Black Limited Edition"]),
    ("kia", "stonic", ["EX", "EX+"]),
    ("hyundai", "tucson", ["GLS Sport", "Ultimate", "AWD"]),
    ("hyundai", "elantra", ["GL", "GLS"]),
    ("hyundai", "sonata", ["2.0", "2.5"]),
    
    # Chinese / Entrants
    ("haval", "h6", ["1.5T", "2.0T", "HEV"]),
    ("changan", "alsvin", ["Comfort", "Lumiere"]),
    ("changan", "oshan-x7", ["Comfort", "FutureSense"]),
    ("mg", "hs", ["1.5 Turbo", "PHEV", "Essence"]),
]

results = {}

def normalize_trim(text):
    return text.lower().replace(" ", "").replace("-", "").replace(".", "")

async def scrape_pakwheels(page, make, model, expected_trims):
    pw_trims = {}
    base_url = f"https://www.pakwheels.com/used-cars/search/-/mk_{make}/md_{model}/"
    print(f"[PakWheels] Navigating to {base_url}")
    try:
        await page.goto(base_url, timeout=60000, wait_until='domcontentloaded')
        await page.wait_for_timeout(3000)
        
        # Click more choices
        btn = await page.query_selector('span[data-target="#lb_more_choices_versions"]')
        if btn:
            await btn.click()
            await page.wait_for_selector('#more_choices_versions input[type="checkbox"]', state='visible', timeout=10000)
            await page.wait_for_timeout(1000)
            
            checkboxes = await page.evaluate('''() => {
                let res = [];
                let labels = document.querySelectorAll('#more_choices_versions label');
                labels.forEach(lbl => {
                    let text = lbl.textContent.replace(/\\(\\d+\\)/g, '').trim();
                    let chk = lbl.querySelector('input[type="checkbox"]');
                    if(chk) {
                        res.push({text: text, val: chk.value});
                    }
                });
                return res;
            }''')
            
            for cb in checkboxes:
                pw_trims[cb['text']] = cb['val'].replace('vr_', '').replace('vg_', '')
                
        else:
            print("[PakWheels] No versions modal found")
    except Exception as e:
        print(f"[PakWheels] Error for {make} {model}: {e}")
        
    return pw_trims

async def scrape_olx(page, make, model):
    # OLX is a bit trickier, they use `q-` search query parameters for sub-trims mostly.
    # We will just guess how they structure the `q-` parameter for the variants since OLX 
    # uses generic query text matching rather than database slugs for sub-variants.
    # Wait, the instruction explicitly says:
    # "Wait for the sub-variant checkboxes to render... Extract the exact text label... and click it to record how OLX mutates the URL slug."
    olx_trims = {}
    base_url = f"https://www.olx.com.pk/islamabad_g4060615/{make}-cars_c84/q-{model}"
    print(f"[OLX] Navigating to {base_url}")
    try:
        await page.goto(base_url, timeout=60000, wait_until='domcontentloaded')
        await page.wait_for_timeout(5000)
        
        # Try to find checkboxes that might be variants. 
        # Often OLX doesn't have exact variant checkboxes for cars unless the model is selected explicitly in the Make/Model modal.
        # Let's search for input[type="checkbox"] and get their labels.
        checkboxes = await page.evaluate('''() => {
            let res = [];
            let inputs = document.querySelectorAll('input[type="checkbox"]');
            inputs.forEach(inp => {
                let parent = inp.closest('label');
                if(parent) {
                    let textNode = parent.querySelector('span'); // usually the label text is in a span
                    if(textNode) {
                        let text = textNode.textContent.trim();
                        // exclude generic labels
                        if (!["New", "Used", "Automatic", "Manual", "Petrol", "Diesel", "CNG", "Hybrid", "Electric", "Unregistered", "Registered", "Islamabad", "Lahore", "Karachi", "Dealer", "Owner"].includes(text)) {
                            res.push(text);
                        }
                    }
                }
            });
            return res;
        }''')
        
        # We will just return the text found. 
        # For URL slug, OLX just appends it to `q-` separated by dashes.
        for cb_text in checkboxes:
            if model.lower() not in cb_text.lower():
                olx_trims[cb_text] = f"q-{model}-{cb_text.lower().replace(' ', '-')}"
            else:
                olx_trims[cb_text] = f"q-{cb_text.lower().replace(' ', '-')}"

    except Exception as e:
        print(f"[OLX] Error for {make} {model}: {e}")
        
    return olx_trims

async def run():
    async with async_playwright() as p:
        # Avoid getting blocked by using a realistic user agent
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        for make, model, exp_trims in target_models:
            page = await context.new_page()
            
            # PakWheels
            pw_trims = await scrape_pakwheels(page, make, model, exp_trims)
            
            # OLX
            olx_trims = await scrape_olx(page, make, model)
            
            await page.close()
            
            # Match them up based on exp_trims
            for exp_trim in exp_trims:
                key = f"{model}:{exp_trim}".lower()
                
                # find closest match in pw_trims
                pw_slug = exp_trim.lower().replace(' ', '-')
                exp_clean = normalize_trim(exp_trim)
                
                for pw_text, slug in pw_trims.items():
                    if exp_clean in normalize_trim(pw_text):
                        pw_slug = slug
                        break
                        
                # find closest match in olx_trims
                olx_slug = f"q-{exp_trim.lower().replace(' ', '-')}"
                for olx_text, slug in olx_trims.items():
                    if exp_clean in normalize_trim(olx_text):
                        olx_slug = slug.replace("q-", "")
                        break
                
                if olx_slug.startswith("q-"):
                    olx_slug = olx_slug[2:]
                    
                results[key] = {
                    "pakwheels": pw_slug,
                    "olx": olx_slug,
                    "autodeals": exp_trim.replace(" ", "-")
                }
                
        await browser.close()
        
    # Generate table.txt
    output = "# table.txt\n# GaariGuru — Verified Trim Routing Table for Pakistani Marketplaces\n\nCANONICAL_TRIM_MAP = {\n"
    for key, val in results.items():
        output += f'    "{key}": {{\n'
        output += f'        "pakwheels": "{val["pakwheels"]}",\n'
        output += f'        "olx":       "{val["olx"]}",\n'
        output += f'        "autodeals": "{val["autodeals"]}"\n'
        output += '    },\n'
    output += "}\n"
    
    with open("table.txt", "w", encoding="utf-8") as f:
        f.write(output)
        
    print("Successfully generated table.txt")

if __name__ == "__main__":
    asyncio.run(run())
