import sys

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = [pg for pg in ctx.pages if "flow.google.com" in pg.url][0]
        print("Current page URL:", page.url)
        composer = page.locator("div.ProseMirror[role='textbox'], [contenteditable='true']").first
        print("Composer visible:", composer.is_visible())
        submit = page.locator("button[aria-label*='Start generation' i]").first
        print("Submit btn visible:", submit.is_visible())

if __name__ == "__main__":
    main()
