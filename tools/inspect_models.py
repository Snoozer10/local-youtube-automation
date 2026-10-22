import sys

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222')
        page = [pg for ctx in browser.contexts for pg in ctx.pages if 'flow.google.com' in pg.url][0]

        # Open settings
        settings_btn = page.locator('button').filter(has_text='Nano Banana').first
        if not settings_btn.is_visible():
            settings_btn = page.locator('button').filter(has_text='x1').first
        settings_btn.click(force=True)
        page.wait_for_timeout(500)

        # Check button attributes
        btns = page.locator('.cdk-overlay-container button').all()
        for b in btns:
            txt = b.inner_text().strip().replace('\n', ' ')
            aria = b.get_attribute('aria-label')
            cls = b.get_attribute('class')
            print(f'Btn: text="{txt}", aria="{aria}", class="{cls}"')
        page.keyboard.press('Escape')

if __name__ == "__main__":
    main()
