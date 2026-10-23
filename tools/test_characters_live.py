import sys
import time

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = [pg for pg in ctx.pages if "flow.google.com" in pg.url][0]
        print("Active page:", page.url)

        # Check navigation items
        print("Finding Characters nav...")
        char_btn = page.locator("button, div, a").filter(has_text="Characters").first
        print("Found character nav:", char_btn.is_visible())
        char_btn.click()
        time.sleep(2)
        print("URL after clicking Characters:", page.url)
        page.screenshot(path=".runtime/characters_page_live.png")

        # Inspect all inputs and editable elements
        elements = page.locator("textarea, input, [contenteditable='true'], div[role='textbox']").all()
        print(f"Found {len(elements)} input/textbox elements:")
        for i, el in enumerate(elements):
            if el.is_visible():
                tag = el.evaluate("e => e.tagName")
                role = el.get_attribute("role") or ""
                aria = el.get_attribute("aria-label") or ""
                ph = el.get_attribute("placeholder") or ""
                cls = el.get_attribute("class") or ""
                txt = el.inner_text().strip()[:40]
                print(f"  [{i}] tag={tag}, role={role}, aria='{aria}', ph='{ph}', class='{cls}', text='{txt}'")

if __name__ == "__main__":
    main()
