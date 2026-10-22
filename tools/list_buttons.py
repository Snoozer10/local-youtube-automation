import sys

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = [pg for pg in ctx.pages if "flow.google.com" in pg.url][0]
        print("Listing all visible buttons on page:")
        for b in page.locator("button, a").all():
            if b.is_visible():
                txt = b.inner_text().strip().replace("\n", " ")
                aria = b.get_attribute("aria-label") or ""
                print(f"  Btn/Link: text='{txt}' aria='{aria}'")

if __name__ == "__main__":
    main()
