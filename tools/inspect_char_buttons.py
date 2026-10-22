import sys

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = [pg for pg in ctx.pages if "flow.google.com" in pg.url][0]

        print("Checking buttons inside prompt container on Characters view:")
        box = page.locator("div.ProseMirror[role='textbox']").first
        print("Composer box visible:", box.is_visible())

        # Check buttons near the box
        parent = page.locator("flow-character-prompt-box, flow-base-prompt-box, [role='region'], form").all()
        print("Parent regions found:", len(parent))

        # Check submit button
        submit_btn = page.locator("button[aria-label*='Start generation' i], button[aria-label*='Generate' i], button:has-text('arrow_forward')").all()
        print("Submit buttons found:", len(submit_btn))
        for s in submit_btn:
            print("  Submit btn visible:", s.is_visible(), "aria:", s.get_attribute("aria-label"))

        # Check 1x or count buttons
        count_btns = page.locator("button").filter(has_text="1x").all()
        print("1x buttons found:", len(count_btns))
        for c in count_btns:
            print("  1x btn visible:", c.is_visible(), "text:", c.inner_text().strip())

if __name__ == "__main__":
    main()
