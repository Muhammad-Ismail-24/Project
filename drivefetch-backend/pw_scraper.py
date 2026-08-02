import time
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 3. Drive.pk
        print("--- Drive.pk ---")
        try:
            page.goto("https://www.drivepk.com/cars/list?brands=Toyota&models=Corolla", timeout=20000)
            time.sleep(3)
            # Find all inputs, selects, or links
            dropdowns = page.locator("select").all()
            for dd in dropdowns:
                print("Drive.pk Select:", dd.get_attribute("name"), dd.get_attribute("id"))
                options = dd.locator("option").all_inner_texts()
                if any("Grande" in opt or "VXR" in opt for opt in options):
                    print("Found Trim Options:", options[:10])
            # also check query string from url
            print("Current URL Drivepk:", page.url)
        except Exception as e:
            print("Drive.pk Error:", e)

        # 4. AutoDeals
        print("--- AutoDeals ---")
        try:
            page.goto("https://autodeals.pk/used-cars/search/-/mk_toyota_7/md_corolla_58", timeout=20000)
            time.sleep(3)
            selects = page.locator("select").all()
            for dd in selects:
                print("AutoDeals Select:", dd.get_attribute("name"), dd.get_attribute("id"))
                options = dd.locator("option").all_inner_texts()
                print("Options:", options[:5])
                if any("Grande" in opt or "VXR" in opt for opt in options):
                    print("Found Trim Options:", options[:10])
        except Exception as e:
            print("AutoDeals Error:", e)

        # 5. WiseWheels
        print("--- WiseWheels ---")
        try:
            page.goto("https://wisewheels.com.pk/used-cars?make=toyota&model=corolla", timeout=20000)
            time.sleep(3)
            selects = page.locator("select").all()
            for dd in selects:
                print("WiseWheels Select:", dd.get_attribute("name"), dd.get_attribute("id"))
                options = dd.locator("option").all_inner_texts()
                print("Options:", options[:5])
                if any("Grande" in opt or "VXR" in opt for opt in options):
                    print("Found Trim Options:", options[:10])
        except Exception as e:
            print("WiseWheels Error:", e)

        browser.close()

if __name__ == "__main__":
    run()
