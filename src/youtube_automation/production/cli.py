"""Explicit-run CLI for staged adaptive production and editorial review."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from youtube_automation.core.utils import get_config_value

from .assets import file_digest
from .briefs import browser_ask, ensure_brief
from .contracts import Brief, fingerprint, load_brief, load_channel
from .invalidation import invalidate_stage, reconcile_invalidation
from .ledger import Ledger, durable_stage, leased_resource, resource_database
from .render import probe_video, render_plan
from .review import approve_review, write_review
from .shots import ShotPlan, ensure_shot_plan, validate_plan
from .writing import write_episode


@contextmanager
def gemini_transport(
    *,
    persistent_chat: bool = False,
    receipt_dir: Path | None = None,
    timeout_seconds: int = 180,
) -> Iterator[Callable[[str], str]]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{int(get_config_value('CDP_PORT', '9222'))}", timeout=30000
        )
        context = browser.contexts[0]
        # Own this page; do not close or repurpose unrelated user tabs.
        page = context.new_page()
        try:
            page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
            yield browser_ask(
                page,
                get_config_value("IMAGE_PLANNER_MODEL", "Pro"),
                persistent_chat=persistent_chat,
                receipt_dir=receipt_dir,
                timeout_seconds=timeout_seconds,
            )
        finally:
            page.close()


def _file_input(path: Path | None) -> str | None:
    return file_digest(path) if path is not None and path.is_file() else None


def _asset_inputs(root: Path) -> list[tuple[str, str]]:
    receipts = root / "asset_receipts"
    if not receipts.is_dir():
        return []
    return [(path.name, file_digest(path)) for path in sorted(receipts.glob("*.json"))]


def _stage_recipe(root: Path, args: argparse.Namespace) -> str:
    stage = str(args.stage)
    inputs: dict[str, Any] = {"version": 1, "stage": stage}
    paths: dict[str, Path | None] = {
        "raw": root / "raw_transcript.txt",
        "brief": root / "episode_brief.json",
        "timeline": root / "timeline.json",
        "plan": root / "shot_plan.json",
        "preview": root / "adaptive_preview.json",
        "approval": root / "editorial_approval.json",
        "config": Path(__file__).resolve().parents[3] / "video_config.txt",
    }
    stage_paths = {
        "analyze": ["raw"],
        "write": ["raw", "brief"],
        "source-audio": ["raw", "brief"],
        "plan": ["brief", "timeline"],
        "generate": ["brief", "plan"],
        "report": ["plan"],
        "preview": ["brief", "timeline", "plan", "config"],
        "approve": ["preview"],
        "render": ["brief", "timeline", "plan", "preview", "approval", "config"],
    }
    inputs["files"] = {name: _file_input(paths[name]) for name in stage_paths[stage]}
    if stage == "analyze":
        profile = Path(args.channel_profile).resolve() if args.channel_profile else None
        inputs["channel_profile"] = _file_input(profile)
    if stage in {"analyze", "write", "plan"}:
        inputs["planner_model"] = get_config_value("IMAGE_PLANNER_MODEL", "Pro")
    if stage == "source-audio":
        media = Path(args.media_file).resolve() if args.media_file else None
        inputs.update(
            media=_file_input(media),
            start_seconds=args.start_seconds,
            end_seconds=args.end_seconds,
        )
    if stage in {"report", "preview", "render"}:
        inputs["assets"] = _asset_inputs(root)
    if stage == "generate":
        inputs["flow"] = {
            "model": get_config_value("FLOW_IMAGE_MODEL", "Nano Banana 2"),
            "count": get_config_value("FLOW_IMAGE_COUNT", "1x"),
        }
    if stage in {"preview", "render"}:
        from youtube_automation.video.compiler import load_video_config

        inputs["render_config"] = load_video_config("video_config.txt")
        try:
            timeline = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
            audio = (root / timeline["audio_file"]).resolve()
            inputs["audio"] = _file_input(audio) if audio.is_relative_to(root) else None
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            inputs["audio"] = None
    if stage == "approve":
        inputs["reviewer"] = args.reviewer
    return fingerprint(inputs)


def _stage_key(root: Path, stage: str) -> str:
    return f"stage:{root.name}:{fingerprint(str(root))[:12]}:{stage}"


def _validated_plan(root: Path) -> tuple[Brief, ShotPlan, dict[str, Any]]:
    brief = load_brief(root)
    timeline = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
    plan = ShotPlan.model_validate_json((root / "shot_plan.json").read_text(encoding="utf-8"))
    validate_plan(plan, timeline, brief)
    return brief, plan, timeline


def _render_output_complete(root: Path, *, preview: bool) -> bool:
    from youtube_automation.video.compiler import load_video_config

    from .assets import read_receipt
    from .flow import verify_generated_assets

    brief, plan, timeline = _validated_plan(root)
    verify_generated_assets(root, plan, brief)
    assets = {shot.asset_id: read_receipt(root, shot.asset_id)["sha256"] for shot in plan.shots}
    audio = (root / timeline["audio_file"]).resolve()
    if not audio.is_relative_to(root) or not audio.is_file():
        return False
    pointer_name = "adaptive_preview.json" if preview else "active_master.json"
    pointer = json.loads((root / pointer_name).read_text(encoding="utf-8"))
    artifact = (root / pointer["path"]).resolve()
    inputs = pointer["inputs"]
    expected_config = dict(load_video_config("video_config.txt"), OUTPUT_FPS=plan.fps)
    expected_status = "pending" if preview else "approved"
    if (
        not artifact.is_relative_to(root)
        or not artifact.is_file()
        or file_digest(artifact) != pointer["sha256"]
        or pointer.get("frames") != plan.total_frames
        or pointer.get("editorial_status") != expected_status
        or pointer.get("generation") != fingerprint(inputs)
        or inputs.get("plan") != fingerprint(plan)
        or inputs.get("assets") != assets
        or inputs.get("audio") != file_digest(audio)
        or inputs.get("config") != expected_config
    ):
        return False
    probe_video(artifact, plan.total_frames, plan.fps, require_audio=True)
    if not preview:
        approval = json.loads((root / "editorial_approval.json").read_text(encoding="utf-8"))
        approved_preview = json.loads(
            (root / "adaptive_preview.json").read_text(encoding="utf-8")
        )
        if (
            approval.get("plan") != fingerprint(plan)
            or approval.get("assets") != assets
            or approval.get("generation") != pointer["generation"]
            or approval.get("preview_sha256") != approved_preview.get("sha256")
        ):
            return False
    return True


def _stage_complete(root: Path, args: argparse.Namespace) -> bool:
    try:
        if args.stage == "analyze":
            brief = load_brief(root)
            raw = (root / "raw_transcript.txt").read_text(encoding="utf-8-sig")
            channel = load_channel(args.channel_profile)
            return (
                brief.source_sha256 == fingerprint(raw)
                and brief.profile_sha256 == fingerprint(channel)
            )
        if args.stage == "write":
            from .writing import verify_written_episode

            return verify_written_episode(root)
        if args.stage == "source-audio":
            from .source_narration import verify_source_narration

            verify_source_narration(root)
            return True
        if args.stage == "plan":
            _validated_plan(root)
            return True
        if args.stage == "generate":
            from .flow import verify_generated_assets

            brief, plan, _ = _validated_plan(root)
            verify_generated_assets(root, plan, brief)
            return True
        if args.stage == "report":
            report = root / "adaptive_review" / "index.html"
            return report.is_file() and report.stat().st_size > 0
        if args.stage == "preview":
            return _render_output_complete(root, preview=True)
        if args.stage == "approve":
            if not _render_output_complete(root, preview=True):
                return False
            _, plan, _ = _validated_plan(root)
            from .assets import read_receipt

            assets = {
                shot.asset_id: read_receipt(root, shot.asset_id)["sha256"] for shot in plan.shots
            }
            preview = json.loads((root / "adaptive_preview.json").read_text(encoding="utf-8"))
            approval = json.loads((root / "editorial_approval.json").read_text(encoding="utf-8"))
            return bool(
                approval
                == {
                    "version": 1,
                    "plan": fingerprint(plan),
                    "assets": assets,
                    "generation": preview["generation"],
                    "preview_sha256": preview["sha256"],
                    "reviewer": args.reviewer.strip(),
                }
            )
        if args.stage == "render":
            return _render_output_complete(root, preview=False)
    except Exception:
        return False
    return False


def _execute_stage(args: argparse.Namespace, root: Path, database: Path) -> None:
    if args.stage == "analyze":
        if not args.channel_profile:
            raise ValueError("analyze requires --channel-profile")
        channel = load_channel(args.channel_profile)
        with leased_resource(database, "browser"), gemini_transport() as ask:
            ensure_brief(root, channel, ask)
    elif args.stage in {"write", "plan"}:
        planning = args.stage == "plan"
        with leased_resource(database, "browser"), gemini_transport(
            persistent_chat=planning,
            receipt_dir=root / "planner_responses" if planning else None,
            timeout_seconds=(
                int(get_config_value("IMAGE_PLANNER_TIMEOUT_SECONDS", "600"))
                if planning
                else 180
            ),
        ) as ask:
            if args.stage == "write":
                write_episode(root, load_brief(root), ask)
            else:
                ensure_shot_plan(root, ask)
    elif args.stage == "source-audio":
        if args.media_file is None or args.start_seconds is None or args.end_seconds is None:
            raise ValueError(
                "source-audio requires --media-file, --start-seconds and --end-seconds"
            )
        from .source_narration import import_source_narration

        print(
            import_source_narration(
                root,
                args.media_file,
                start_seconds=args.start_seconds,
                end_seconds=args.end_seconds,
            )
        )
    elif args.stage == "generate":
        from youtube_automation.visuals.flow_generator import main as generate

        load_brief(root)
        generate(str(root))
    elif args.stage == "report":
        print(write_review(root))
    elif args.stage == "approve":
        if not args.reviewer:
            raise ValueError("approve requires --reviewer after an actual editorial review")
        approve_review(root, args.reviewer)
    else:
        from youtube_automation.video.compiler import load_video_config

        print(
            render_plan(
                root, load_video_config("video_config.txt"), preview=args.stage == "preview"
            )
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Adaptive multi-channel production (explicit run, opt-in)"
    )
    parser.add_argument(
        "stage",
        choices=[
            "analyze",
            "write",
            "source-audio",
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
    parser.add_argument("--media-file")
    parser.add_argument("--start-seconds", type=float)
    parser.add_argument("--end-seconds", type=float)
    parser.add_argument(
        "--force-retry",
        action="store_true",
        help="retry a corrected stage after its bounded failure circuit opens",
    )
    args = parser.parse_args(argv)
    root = Path(args.run_dir).resolve()
    if not root.is_dir():
        parser.error("Run directory must already exist")
    # Shared across runs in this installation; never scope exclusive devices per run.
    database = resource_database()
    if args.stage == "analyze" and not args.channel_profile:
        parser.error("analyze requires --channel-profile")
    if args.stage == "source-audio" and (
        args.media_file is None or args.start_seconds is None or args.end_seconds is None
    ):
        parser.error("source-audio requires --media-file, --start-seconds and --end-seconds")
    if args.stage == "approve" and not args.reviewer:
        parser.error("approve requires --reviewer after an actual editorial review")
    if args.stage == "status":
        database.parent.mkdir(exist_ok=True)
        for row in Ledger(database).status():
            print(row)
    else:
        try:
            reconcile_invalidation(root)
            recipe = _stage_recipe(root, args)
            key = _stage_key(root, args.stage)
            existing = Ledger(database).get(key)
            complete = _stage_complete(root, args)
            adoptable = args.stage != "report"
            repair_success = bool(
                existing
                and existing["state"] == "SUCCEEDED"
                and existing["recipe"] == recipe
                and not complete
            )
            recover_complete = bool(
                adoptable and complete and existing and existing["state"] == "BLOCKED"
            )
            with durable_stage(
                database,
                key,
                recipe,
                force=args.force_retry or repair_success or recover_complete,
                detail={"stage": args.stage, "run": str(root)},
            ) as execute:
                if not execute:
                    print(f"Stage already succeeded for unchanged inputs: {args.stage}")
                    return
                if existing and existing["recipe"] != recipe:
                    archived = invalidate_stage(root, args.stage, existing["recipe"], recipe)
                    if archived:
                        print(
                            f"Archived {len(archived)} invalidated activation file(s) "
                            f"before retrying stage: {args.stage}"
                        )
                    # The earlier completion check examined the prior activation.
                    # Recheck after archiving before adopting any remaining output.
                    complete = _stage_complete(root, args)
                if adoptable and complete:
                    print(f"Registered existing verified stage output: {args.stage}")
                    return
                _execute_stage(args, root, database)
        except ValueError as exc:
            parser.error(str(exc))
