from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = [pg for ctx in browser.contexts for pg in ctx.pages if "flow.google.com" in pg.url][0]

        cand = page.locator("div[contenteditable='true'], [role='textbox']").all()
        print("Found contenteditables:", len(cand))
        for c in cand:
            print("  tag:", c.evaluate("el => el.tagName"), "vis:", c.is_visible(), "outer:", c.evaluate("el => el.outerHTML.substring(0, 200)"))

        wrapper = page.locator("flow-character-prompt-box, flow-prompt-box, .prompt-box, flow-base-prompt-box").all()
        print("Found prompt boxes:", len(wrapper))
        for w in wrapper:
            print("  wrapper:", w.evaluate("el => el.tagName"), "vis:", w.is_visible(), "outer:", w.evaluate("el => el.outerHTML.substring(0, 200)"))

if __name__ == "__main__":
    main()
