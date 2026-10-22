from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = [pg for pg in browser.contexts[0].pages if "flow.google.com" in pg.url][0]
        print("Testing on page:", page.url)
        loc = page.locator("div.ProseMirror[role='textbox'], div[role='textbox'][aria-label*='Describe your character' i], textarea[placeholder*='Describe your character' i], input[placeholder*='Describe your character' i]")
        loc.first.wait_for(state="visible", timeout=15000)
        print("Found visible composer! Count:", loc.count())

if __name__ == "__main__":
    main()
