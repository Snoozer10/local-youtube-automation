from pathlib import Path


def main() -> None:
    p = Path("src/youtube_automation/visuals/asset_studio.py")
    content = p.read_text(encoding="utf-8")

    new_preflight_block = """def preflight_episode_character(page: Any) -> None:
        if not page.url.endswith("/character"):
            try:
                _exact_visible(page.get_by_text(re.compile(r"^(Characters|الشخصيات)$")), "Characters navigation").click()
            except Exception:
                char_nav = page.locator("button, a, div[role='button']").filter(has_text=re.compile(r"Characters|الشخصيات", re.I))
                if char_nav.count() > 0 and char_nav.first.is_visible():
                    char_nav.first.click()
        _exact_visible(
            page.locator(
                "textarea[placeholder*='Describe your character' i], input[placeholder*='Describe your character' i], div.ProseMirror[role='textbox'], div[role='textbox'][aria-label*='Describe your character' i]"
            ),
            "character portrait composer",
        )
        try:
            try:
                _exact_visible(page.get_by_role("button", name="1x", exact=True), "1x image count")
            except Exception:
                pass
            _exact_visible(
                page.locator(
                    "button[aria-label*='Generate' i], button[aria-label*='Submit' i], button[aria-label*='Create' i], button[aria-label*='Start generation' i], button:has-text('arrow_forward')"
                ),
                "portrait submit button",
            )
        except RuntimeError as error:
            raise RuntimeError("Episode character studio unsupported: exact 1x and semantic submit controls require live verification") from error"""

    new_create_block = """    portrait_input = _exact_visible(
            page.locator(
                "textarea[placeholder*='Describe your character' i], input[placeholder*='Describe your character' i], div.ProseMirror[role='textbox'], div[role='textbox'][aria-label*='Describe your character' i]"
            ),
            "character portrait composer",
        )
        portrait_input.fill(f"Character portrait. {description}. {style}. Plain background, no text or labels.")

        def send(scope: Any, stage: str) -> None:
            try:
                _exact_visible(page.get_by_role("button", name="1x", exact=True), "1x image count")
            except Exception:
                pass
            button = _exact_visible(
                scope.locator(
                    "button[aria-label*='Generate' i], button[aria-label*='Submit' i], button[aria-label*='Create' i], button[aria-label*='Start generation' i], button:has-text('arrow_forward')"
                ),
                f"{stage} submit button",
            )"""

    # Locate preflight_episode_character in content
    import re
    pattern_preflight = re.compile(r"def preflight_episode_character\(page: Any\) -> None:.*?(?=\ndef create_episode_character)", re.DOTALL)
    content = pattern_preflight.sub(new_preflight_block + "\n\n", content, count=1)

    # Locate portrait_input and send in create_episode_character
    pattern_create = re.compile(r"    portrait_input = _exact_visible\(.*?button\.click\(\)", re.DOTALL)
    replacement_create = new_create_block + """
            if button.is_disabled():
                raise RuntimeError(f"{stage} submit is disabled")
            reserve(stage)
            button.click()"""
    content = pattern_create.sub(replacement_create, content, count=1)

    p.write_text(content, encoding="utf-8")
    print("Updated asset_studio.py successfully!")

if __name__ == "__main__":
    main()
