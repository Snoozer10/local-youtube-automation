import sys
import time

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222')
        page = [pg for ctx in browser.contexts for pg in ctx.pages if 'flow.google.com' in pg.url][0]

        # Try selecting Nano Banana Pro
        pro_opt = page.locator('.cdk-overlay-container [role="menuitem"], .cdk-overlay-container button').filter(has_text='Nano Banana Pro').first
        if pro_opt.is_visible():
            print("Clicking Nano Banana Pro...")
            pro_opt.click(force=True)
            time.sleep(1)
        else:
            print("Pro opt not visible, opening settings...")
            settings_btn = page.locator('button').filter(has_text='Nano Banana').first
            settings_btn.click(force=True)
            time.sleep(1)
            model_trigger = page.locator('button:has-text("Nano Banana")').last
            model_trigger.click(force=True)
            time.sleep(1)
            page.locator('.cdk-overlay-container [role="menuitem"], .cdk-overlay-container button').filter(has_text='Nano Banana Pro').first.click(force=True)
            time.sleep(1)

        page.keyboard.press("Escape")
        time.sleep(0.5)
        page.keyboard.press("Escape")
        time.sleep(0.5)

        # Inject prompt and submit
        input_box = page.locator("div[contenteditable='true']").first
        input_box.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Backspace")
        time.sleep(0.2)
        test_prompt = "Serene quiet lake surrounded by pine trees at dawn, soft mist over still water, professional landscape photograph, no text."
        page.keyboard.insert_text(test_prompt)
        time.sleep(0.5)

        submit_btn = page.locator("button[aria-label*='Start generation' i], button:has-text('arrow_forward')").first
        if submit_btn.is_visible() and submit_btn.is_enabled():
            submit_btn.click(force=True)
        else:
            page.keyboard.press("Enter")

        print("Submitted with Nano Banana Pro! Monitoring...")
        for sec in range(90):
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
            if not state["pending"]:
                break

if __name__ == "__main__":
    main()
