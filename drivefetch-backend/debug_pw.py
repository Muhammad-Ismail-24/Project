from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.pakwheels.com/used-cars/search/-/mk_suzuki/md_cultus/", wait_until="load")
        
        # Give it a second to render
        page.wait_for_timeout(3000)
        
        # Get all filter headers
        html = page.evaluate('''() => {
            let res = "NO MATCH";
            let h3s = document.querySelectorAll('h3');
            let versionH3 = Array.from(h3s).find(h => h.textContent.trim().includes('Version'));
            if(versionH3) {
                let panel = versionH3.closest('.filter-panel');
                res = panel.innerHTML;
            }
            return res;
        }''')
        
        print("Filter HTML:", html)
        browser.close()

if __name__ == "__main__":
    run()
