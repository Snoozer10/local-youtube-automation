import sys
import time


def main() -> None:
    sys.path.insert(0, "src")
    from playwright.sync_api import sync_playwright

    from youtube_automation.core.utils import kill_cdp_chrome, launch_browser_with_profile

    print("1. Killing current Chrome on 9222...")
    kill_cdp_chrome(9222)
    time.sleep(2)

    print("2. Launching Chrome with profile 3 (Profile 2)...")
    launch_browser_with_profile("chrome", "3", port=9222)
    time.sleep(3)

    print("3. Checking Google Flow project URL in Profile 2...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        page.goto("https://flow.google.com/project/e9fabf13-dddf-4d0d-8fc4-24c008f4022e", timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)
        print("Page URL:", page.url)
        print("Page Title:", page.title())
        page.screenshot(path=".runtime/flow_profile2_verified.png")
        print("Screenshot saved to .runtime/flow_profile2_verified.png")

if __name__ == "__main__":
    main()
