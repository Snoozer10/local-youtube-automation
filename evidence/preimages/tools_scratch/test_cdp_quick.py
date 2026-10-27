import traceback

from playwright.sync_api import sync_playwright


def main() -> None:
    print("Starting playwright...")
    try:
        with sync_playwright() as p:
            print("Calling connect_over_cdp with 10s timeout...")
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=10000)
            print("Connected! contexts:", len(browser.contexts))
            for ctx in browser.contexts:
                print("Context pages:", len(ctx.pages))
                for pg in ctx.pages:
                    print(" - Page URL:", pg.url)
            browser.close()
            print("Done.")
    except Exception as e:
        print("Caught exception:", type(e), e)
        traceback.print_exc()

if __name__ == "__main__":
    main()
