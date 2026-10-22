import sys
import time

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = [pg for pg in ctx.pages if "flow.google.com" in pg.url][0]

        print("Testing interaction with character composer on:", page.url)
        composer = page.locator("div.ProseMirror[role='textbox']").first
        composer.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Backspace")
        time.sleep(0.5)

        test_text = "Character portrait. An illustrative pet dog in a warm domestic setting. Soft lighting, neutral background, no text."
        page.keyboard.insert_text(test_text)
        time.sleep(1)

        print("Composer text:", composer.inner_text().strip())

        # Check submit button state
        submit = page.locator("button[aria-label*='Start generation' i], button:has-text('arrow_forward')").first
        print("Submit button visible:", submit.is_visible())
        print("Submit button enabled:", submit.is_enabled())

        page.screenshot(path=".runtime/char_prompt_entered.png")
        print("Screenshot saved to .runtime/char_prompt_entered.png")

if __name__ == "__main__":
    main()
