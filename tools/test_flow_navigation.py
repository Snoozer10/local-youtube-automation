import sys
import time

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        print("Navigating to Google Flow project...")
        project_url = "https://flow.google.com/project/e9fabf13-dddf-4d0d-8fc4-24c008f4022e"
        page.goto(project_url, timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)
        print("Page URL:", page.url)
        print("Page Title:", page.title())

        # Check if prompt box is visible
        input_box = page.locator("div[contenteditable='true'], textarea").first
        print("Input box visible:", input_box.is_visible())

        # Take screenshot for evidence
        page.screenshot(path=".runtime/flow_project_verified.png")
        print("Screenshot saved to .runtime/flow_project_verified.png")

if __name__ == "__main__":
    main()
