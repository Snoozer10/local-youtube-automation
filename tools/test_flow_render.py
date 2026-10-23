import time

from playwright.sync_api import sync_playwright


def test_render():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = [pg for ctx in browser.contexts for pg in ctx.pages if "flow.google.com" in pg.url][0]
        print("Page URL:", page.url)

        # Find input box
        input_box = None
        for ce in page.locator("div[contenteditable='true'], [role='textbox'][contenteditable='true']").all():
            if ce.is_visible():
                box = ce.bounding_box()
                if box and box["width"] > 250:
                    input_box = ce
                    break
        if not input_box:
            print("No input box found!")
            return

        print("Found input box. Injecting test prompt...")
        input_box.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Backspace")
        time.sleep(0.2)
        test_prompt = "A simple serene wooden table with a vintage ceramic mug in morning sunlight, clean archival photography, no text."
        page.keyboard.insert_text(test_prompt)
        time.sleep(0.5)

        # Submit
        submit_btn = page.locator("button[aria-label*='Start generation' i], button:has-text('arrow_forward')").first
        if submit_btn.is_visible() and submit_btn.is_enabled():
            print("Clicking submit button...")
            submit_btn.click(force=True)
        else:
            print("Pressing Enter...")
            page.keyboard.press("Enter")

        print("Submitted! Monitoring DOM for 90 seconds...")
        for sec in range(90):
            time.sleep(1)
            state = page.evaluate("""() => {
                const pending = document.querySelector('flow-pending-tile');
                const pct = document.querySelector('.loading-percentage');
                const imgs = Array.from(document.querySelectorAll('flow-image-tile img, flow-grid-tile-container img, img')).map(img => ({
                    src: (img.src || '').substring(0, 50),
                    naturalWidth: img.naturalWidth,
                    clientWidth: img.clientWidth,
                    visible: img.offsetParent !== null,
                    cls: img.className
                }));
                const errs = Array.from(document.querySelectorAll('[role="alert"], mat-snack-bar-container')).map(e => e.innerText);
                return {
                    pendingVisible: !!pending,
                    pct: pct ? pct.innerText : null,
                    imgs: imgs,
                    errs: errs
                };
            }""")
            if sec % 5 == 0 or not state["pendingVisible"]:
                print(f"[{sec}s] Pending={state['pendingVisible']}, Pct={state['pct']}, Imgs={len(state['imgs'])}, Errs={state['errs']}")
            if not state["pendingVisible"] and any(im["naturalWidth"] > 100 for im in state["imgs"]):
                print(f"SUCCESS at {sec}s! Img details:", [im for im in state["imgs"] if im["naturalWidth"] > 100])
                break

if __name__ == "__main__":
    test_render()
