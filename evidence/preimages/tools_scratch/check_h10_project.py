import sys

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        page.goto("https://flow.google.com/project/9320d0c1-252e-4799-9fb3-9dcbaefcca8d", timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        print("Page URL:", page.url)
        print("Page Title:", page.title())
        page.close()

if __name__ == "__main__":
    main()
