import sys
import time


def main() -> None:
    sys.path.insert(0, "src")
    from playwright.sync_api import sync_playwright

    from youtube_automation.core.utils import (
        is_port_in_use,
        kill_cdp_chrome,
        launch_browser_with_profile,
    )

    print("1. Killing current Chrome on 9222...")
    killed = kill_cdp_chrome(9222)
    print("Kill result:", killed)
    time.sleep(2)

    print("Port in use after kill:", is_port_in_use(9222))

    print("2. Launching Chrome cleanly with profile 2 on port 9222...")
    launched = launch_browser_with_profile("chrome", "2", port=9222)
    print("Launch result:", launched)
    time.sleep(3)

    print("3. Testing Playwright connect_over_cdp...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=10000)
        print("SUCCESS! Connected over CDP!")
        print("Contexts count:", len(browser.contexts))
        for ctx in browser.contexts:
            print("  Pages:", len(ctx.pages))
            for pg in ctx.pages:
                print("   -", pg.url)
        browser.close()
    print("Cycle test complete.")

if __name__ == "__main__":
    main()
