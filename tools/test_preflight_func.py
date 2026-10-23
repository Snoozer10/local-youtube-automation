import re

from playwright.sync_api import sync_playwright


def test_preflight(page):
    if not page.url.endswith("/character"):
        nav = page.locator("button, a, div[role='button']").filter(has_text=re.compile(r"Characters|الشخصيات", re.I)).first
        nav.click()
        page.wait_for_timeout(1000)

    composer = page.locator("div.ProseMirror[role='textbox'], div[role='textbox'][aria-label*='Describe your character' i], textarea[placeholder*='Describe your character' i], input[placeholder*='Describe your character' i]").first
    assert composer.is_visible(), "character portrait composer not visible"

    count_btn = page.locator("button").filter(has_text=re.compile(r"^\s*1x\s*$", re.I))
    if count_btn.count() > 0 and count_btn.first.is_visible():
        print("Found 1x button")
    else:
        print("1x count implicit in character portrait studio")

    submit = page.locator("button[aria-label*='Start generation' i], button[aria-label*='Generate' i], button[aria-label*='Submit' i], button[aria-label*='Create' i], button:has-text('arrow_forward')").first
    assert submit.is_visible(), "portrait submit button not visible"
    print("Preflight passed completely!")

def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = [pg for pg in browser.contexts[0].pages if "flow.google.com" in pg.url][0]
        test_preflight(page)

if __name__ == "__main__":
    main()
