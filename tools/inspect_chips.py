from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = [pg for pg in browser.contexts[0].pages if "flow.google.com" in pg.url][0]
        chips = page.locator("flow-base-prompt-box flow-ingredient-chip, flow-base-prompt-box flow-image-ingredient-chip, flow-base-prompt-box button.chip-container").all()
        for i, c in enumerate(chips):
            print(f"Chip [{i}]: text='{c.inner_text().strip()}'")
            imgs = c.locator("img").all()
            for img in imgs:
                print(f"  img src: {img.get_attribute('src')}")

if __name__ == "__main__":
    main()
