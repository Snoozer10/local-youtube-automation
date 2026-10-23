
from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = browser.contexts[0].new_page()
        url = "https://flow.google.com/project/9320d0c1-252e-4799-9fb3-9dcbaefcca8d"
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        print("Final URL:", page.url)
        print("Title:", page.title())
        page.close()

if __name__ == "__main__":
    main()
