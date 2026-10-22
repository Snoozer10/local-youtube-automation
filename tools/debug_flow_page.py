import json

from playwright.sync_api import sync_playwright


def inspect():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        flow_pages = [pg for ctx in browser.contexts for pg in ctx.pages if "flow.google.com" in pg.url]
        if not flow_pages:
            print("No Flow page found!")
            return
        page = flow_pages[0]
        print("Page URL:", page.url)
        print("Page Title:", page.title())

        # Check alerts / banners
        data = page.evaluate("""() => {
            const getTexts = sel => Array.from(document.querySelectorAll(sel)).map(e => e.innerText.trim()).filter(Boolean);
            return {
                alerts: getTexts('[role="alert"]'),
                snackbars: getTexts('mat-snack-bar-container, snack-bar-container'),
                banners: getTexts('flow-banner'),
                pendingTileText: getTexts('flow-pending-tile'),
                allButtons: getTexts('button'),
                disabledButtons: Array.from(document.querySelectorAll('button:disabled')).map(e => e.innerText.trim())
            };
        }""")
        print("DOM Alerts/Snackbars:", json.dumps(data, indent=2))

if __name__ == "__main__":
    inspect()
