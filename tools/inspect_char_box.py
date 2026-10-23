import sys

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = [pg for pg in ctx.pages if "flow.google.com" in pg.url][0]

        print("Checking prompt/input box on Characters view:")
        for el in page.locator("div[role='textbox'], [contenteditable='true'], textarea").all():
            if el.is_visible():
                tag = el.evaluate("e => e.tagName")
                role = el.get_attribute("role") or ""
                aria = el.get_attribute("aria-label") or ""
                ph = el.get_attribute("placeholder") or ""
                cls = el.get_attribute("class") or ""
                print(f"  Input: tag={tag}, role={role}, aria='{aria}', ph='{ph}', class='{cls}'")

if __name__ == "__main__":
    main()
