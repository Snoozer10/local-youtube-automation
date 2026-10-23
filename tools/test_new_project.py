from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = [pg for ctx in browser.contexts for pg in ctx.pages if "flow.google.com" in pg.url][0]
        page.goto("https://flow.google.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        print("Homepage URL:", page.url)
        btn = page.locator("button:has-text('New project'), a:has-text('New project')").first
        print("New project btn visible:", btn.is_visible())
        if btn.is_visible():
            btn.click()
            page.wait_for_timeout(3000)
            print("After click URL:", page.url)

if __name__ == "__main__":
    main()
