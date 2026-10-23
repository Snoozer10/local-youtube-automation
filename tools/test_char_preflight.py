import re
import sys

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = [pg for pg in ctx.pages if "flow.google.com" in pg.url][0]

        # Test navigation selector
        print("Testing navigation selector...")
        char_nav = page.locator("button, a, div[role='button']").filter(has_text=re.compile(r"Characters|الشخصيات", re.I)).first
        print("Char nav found:", char_nav.is_visible(), "text:", char_nav.inner_text().strip())

        # Test portrait composer selector
        print("Testing portrait composer selector...")
        composer = page.locator("div.ProseMirror[role='textbox'], div[role='textbox'][aria-label*='Describe your character' i], textarea[placeholder*='Describe your character' i], input[placeholder*='Describe your character' i]").first
        print("Composer found:", composer.is_visible(), "tag:", composer.evaluate("e => e.tagName"), "aria:", composer.get_attribute("aria-label"))

        # Test submit button selector
        print("Testing submit button selector...")
        submit = page.locator("button[aria-label*='Start generation' i], button[aria-label*='Generate' i], button[aria-label*='Submit' i], button:has-text('arrow_forward')").first
        print("Submit found:", submit.is_visible(), "aria:", submit.get_attribute("aria-label"))

        # Check if 1x exists or if it's implicit
        count_btn = page.locator("button").filter(has_text=re.compile(r"^\s*1x\s*$", re.I)).all()
        print("Exact 1x buttons count:", len(count_btn))

if __name__ == "__main__":
    main()
