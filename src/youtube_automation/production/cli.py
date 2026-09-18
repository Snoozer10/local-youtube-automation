"""Explicit-run CLI for staged adaptive production and editorial review."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from .briefs import browser_ask, ensure_brief
from .contracts import load_brief, load_channel
from .ledger import Ledger, leased_resource, resource_database
from .render import render_plan
from .review import approve_review, write_review
from .shots import ensure_shot_plan
from .writing import write_episode


@contextmanager
def gemini_transport() -> Iterator[Callable[[str], str]]:
    from playwright.sync_api import sync_playwright

    from youtube_automation.core.utils import get_config_value

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{int(get_config_value('CDP_PORT', '9222'))}", timeout=30000
        )
        context = browser.contexts[0]
        # Own this page; do not close or repurpose unrelated user tabs.
        page = context.new_page()
        try:
            page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
            yield browser_ask(page, get_config_value("IMAGE_PLANNER_MODEL", "Pro"))
        finally:
            page.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Adaptive multi-channel production (explicit run, opt-in)"
    )
    parser.add_argument(
        "stage",
        choices=[
            "analyze",
            "write",
            "plan",
            "generate",
            "report",
            "preview",
            "approve",
            "render",
            "status",
        ],
    )
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--channel-profile")
    parser.add_argument("--reviewer")
    args = parser.parse_args(argv)
    root = Path(args.run_dir).resolve()
    if not root.is_dir():
        parser.error("Run directory must already exist")
    # Shared across runs in this installation; never scope exclusive devices per run.
    database = resource_database()
    if args.stage == "status":
        database.parent.mkdir(exist_ok=True)
        for row in Ledger(database).status():
            print(row)
    elif args.stage == "analyze":
        if not args.channel_profile:
            parser.error("analyze requires --channel-profile")
        channel = load_channel(args.channel_profile)
        with leased_resource(database, "browser"), gemini_transport() as ask:
            ensure_brief(root, channel, ask)
    elif args.stage in {"write", "plan"}:
        with leased_resource(database, "browser"), gemini_transport() as ask:
            if args.stage == "write":
                write_episode(root, load_brief(root), ask)
            else:
                ensure_shot_plan(root, ask)
    elif args.stage == "generate":
        from youtube_automation.visuals.flow_generator import main as generate

        load_brief(root)
        generate(str(root))
    elif args.stage == "report":
        print(write_review(root))
    elif args.stage == "approve":
        if not args.reviewer:
            parser.error("approve requires --reviewer after an actual editorial review")
        approve_review(root, args.reviewer)
    else:
        from youtube_automation.video.compiler import load_video_config

        print(
            render_plan(
                root, load_video_config("video_config.txt"), preview=args.stage == "preview"
            )
        )
