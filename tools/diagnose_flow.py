from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp('http://127.0.0.1:9222')
        flow_pages = [pg for pg in b.contexts[0].pages if 'flow' in pg.url]
        if not flow_pages:
            print("No flow page found!")
            return
        page = flow_pages[0]
        print("Page URL:", page.url)
        print("Page Title:", page.title())
        input_loc = page.locator("div[contenteditable='true'], textarea").first
        print("Input visible:", input_loc.is_visible() if input_loc else False)
        if input_loc and input_loc.is_visible():
            print("Input text:", repr(input_loc.inner_text()[:100]))

        cards_angular = page.locator("flow-image-tile, flow-tile-container, flow-grid-tile-container, div[data-card-index], .generation-card, [role='article']").all()
        print("Flow tiles count (all):", len(cards_angular))
        print("flow-image-tile count:", page.locator("flow-image-tile").count())
        print("flow-tile-container count:", page.locator("flow-tile-container").count())
        print("flow-grid-tile-container count:", page.locator("flow-grid-tile-container").count())

        # Check modal / dialog / alerts
        alerts = page.locator("[role='alert'], [role='dialog'], .modal, [class*='dialog']").all()
        print("Alerts/Modals count:", len(alerts))
        for a in alerts[:3]:
            try:
                if a.is_visible():
                    print("Alert visible text:", repr(a.inner_text()[:200]))
            except Exception:
                pass

        # Check buttons
        submit_btn = page.locator("button[aria-label*='Start generation' i], button:has-text('arrow_forward')").first
        print("Submit button visible:", submit_btn.is_visible() if submit_btn else False)

        imgs = page.locator("img").all()
        print("Total imgs on page:", len(imgs))
        for idx, img in enumerate(imgs):
            try:
                box = img.bounding_box()
                if box and box["width"] > 180 and box["height"] > 120:
                    src = img.get_attribute("src")[:60]
                    # Evaluate parent tag and classes in browser JS
                    parent_info = img.evaluate("""el => {
                        let p = el.parentElement;
                        let chain = [];
                        while (p && chain.length < 5) {
                            chain.push(p.tagName.toLowerCase() + (p.className ? '.' + p.className.split(' ').join('.') : ''));
                            p = p.parentElement;
                        }
                        return chain.join(' > ');
                    }""")
                    print(f"Img {idx}: size={int(box['width'])}x{int(box['height'])}, src={src}..., parent chain: {parent_info}")
            except Exception as e:
                print(f"Img {idx} err:", e)

if __name__ == '__main__':
    main()
