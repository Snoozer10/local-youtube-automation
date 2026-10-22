
from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = [pg for pg in browser.contexts[0].pages if "flow.google.com" in pg.url][0]
        box = page.locator("div.ProseMirror[role='textbox']").first
        try:
            box.fill("Test fill")
            print("box.fill succeeded!")
        except Exception as e:
            print("box.fill failed:", e)

if __name__ == "__main__":
    main()
