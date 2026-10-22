from pathlib import Path

from playwright.sync_api import sync_playwright

from youtube_automation.production.characters import ensure_episode_characters
from youtube_automation.production.contracts import load_brief
from youtube_automation.production.shots import ShotPlan


def main() -> None:
    root = Path("youtube_runs/adaptive-h10-professor-dog-cues-phase2-20261005T080653Z-codex-cache-rebuild-20261007T094309Z")
    brief = load_brief(root)
    plan = ShotPlan.model_validate_json((root / "shot_plan.json").read_text(encoding="utf-8"))

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = [pg for pg in ctx.pages if "flow.google.com" in pg.url][0]
        print("Page URL before ensure:", page.url)
        project_url = "https://flow.google.com/project/9320d0c1-252e-4799-9fb3-9dcbaefcca8d"
        ensure_episode_characters(
            page,
            root,
            plan,
            brief,
            profile_index="3",
            project_url=project_url,
        )
        print("ensure_episode_characters PASSED!")
        print("Page URL after ensure:", page.url)

if __name__ == "__main__":
    main()
