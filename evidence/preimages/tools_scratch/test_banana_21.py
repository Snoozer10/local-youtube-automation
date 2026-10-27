import sys
import time

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222')
        page = [pg for ctx in browser.contexts for pg in ctx.pages if 'flow.google.com' in pg.url][0]

        # Open settings
        settings_btn = page.locator('button').filter(has_text='x1').first
        settings_btn.click(force=True)
        time.sleep(1)

        # Select Nano Banana 2.1
        model_trigger = page.locator('button:has-text("Nano Banana")').last
        model_trigger.click(force=True)
        time.sleep(1)
        page.locator('.cdk-overlay-container [role="menuitem"], .cdk-overlay-container button').filter(has_text='Nano Banana 2.1').first.click(force=True)
        time.sleep(1)
        page.keyboard.press("Escape")
        time.sleep(0.5)
        page.keyboard.press("Escape")
        time.sleep(0.5)

        # Submit prompt
        input_box = page.locator("div[contenteditable='true']").first
        input_box.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Backspace")
        time.sleep(0.2)
        test_prompt = "A solitary vintage lighthouse at twilight on rocky coast, soft oceanic mist, fine architectural linework, no text."
        page.keyboard.insert_text(test_prompt)
        time.sleep(0.5)

        submit_btn = page.locator("button[aria-label*='Start generation' i], button:has-text('arrow_forward')").first
        if submit_btn.is_visible() and submit_btn.is_enabled():
            submit_btn.click(force=True)
        else:
            page.keyboard.press("Enter")

        print("Submitted with Nano Banana 2.1! Monitoring...")
        for sec in range(60):
            time.sleep(1)
            state = page.evaluate("""() => {
                const pending = document.querySelector('flow-pending-tile');
                const pct = document.querySelector('.loading-percentage');
                const errs = Array.from(document.querySelectorAll('.error-title, .error-message-text, [role="alert"]')).map(e => e.innerText);
                const imgs = Array.from(document.querySelectorAll('flow-image-tile img, flow-grid-tile-container img')).map(i => ({src: i.src.substring(0, 50), w: i.naturalWidth}));
                return {
                    pending: !!pending,
                    pct: pct ? pct.innerText : null,
                    errs: errs,
                    imgs: imgs
                };
            }""")
            if sec % 5 == 0 or not state["pending"]:
                print(f"[{sec}s] Pending={state['pending']}, Pct={state['pct']}, Imgs={state['imgs']}, Errs={state['errs']}")
            if not state["pending"] and len(state["imgs"]) > 0:
                print("SUCCESS with 2.1!")
                break

if __name__ == "__main__":
    main()
