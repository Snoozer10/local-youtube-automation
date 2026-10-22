import sys
import time

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = [pg for ctx in browser.contexts for pg in ctx.pages if "flow.google.com" in pg.url][0]

        char_nav = page.get_by_text("Characters").first
        print("Characters nav visible:", char_nav.is_visible())
        char_nav.click()
        time.sleep(2)
        print("URL after click:", page.url)

        page.screenshot(path=".runtime/debug_characters_page.png")

        inputs = page.locator("textarea, input, [contenteditable='true']").all()
        print("Inputs count on Characters page:", len(inputs))
        for i, inp in enumerate(inputs):
            ph = inp.get_attribute("placeholder") or ""
            vis = inp.is_visible()
            tag = inp.evaluate("el => el.tagName")
            txt = inp.inner_text().strip()[:40]
            print(f"Input {i}: tag={tag}, vis={vis}, ph='{ph}', text='{txt}'")

        buttons = page.locator("button").all()
        print("Buttons on Characters page:")
        for b in buttons:
            if b.is_visible():
                print("  Btn:", b.inner_text().strip().replace("\n", " "))

if __name__ == "__main__":
    main()
