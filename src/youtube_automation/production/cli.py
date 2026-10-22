"""Explicit-run CLI for staged adaptive production and editorial review."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from youtube_automation.core.utils import (
    active_profile_index,
    failover_owned_browser_profile,
    get_config_value,
    get_runtime_state,
    next_profile_index,
)

from .assets import asset_storage_id, file_digest, read_shot_receipt
from .briefs import (
    GeminiUsageLimitError,
    browser_ask,
    ensure_brief,
    is_visual_policy_update,
    rebind_visual_policy,
    requires_visual_strategy_migration,
    visual_policy_migration_pending,
)
from .contracts import Brief, fingerprint, load_brief, load_channel
from .invalidation import invalidate_stage, reconcile_invalidation
from .ledger import Ledger, durable_stage, leased_resource, resource_database
from .render import (
    RENDERER_VERSION,
    current_render_inputs,
    probe_video,
    render_code_fingerprint,
    render_plan,
    render_tool_version,
    require_current_preview,
)
from .review import approve_review, write_review
from .shots import (
    SEMANTIC_PLANNER_VERSION,
    SHOT_COMPILER_VERSION,
    ShotPlan,
    archive_editorial_rejection_for_retry,
    ensure_shot_plan,
    migrate_semantic_checkpoint,
    validate_plan,
)
from .writing import write_episode


def _planner_attachment_mode(*, persistent_chat: bool) -> Literal["inline", "file"]:
    if not persistent_chat:
        return "inline"
    configured = get_config_value("IMAGE_PLANNER_TRANSPORT", "file").strip().lower()
    if configured not in {"inline", "file"}:
        raise ValueError(
            "IMAGE_PLANNER_TRANSPORT must be either 'inline' or 'file'; "
            f"received {configured!r}"
        )
    return "file" if configured == "file" else "inline"



def _direction_generation_model() -> str:
    model = str(get_config_value("IMAGE_PLANNER_MODEL", "Pro")).strip()
    if not model or len(model) > 100 or any(ord(char) < 32 for char in model):
        raise ValueError("IMAGE_PLANNER_MODEL must be a bounded nonempty model label")
    return model



def _direction_transport_receipt(
    root: Path, *, model: str, prompt: str
) -> tuple[Path, str]:
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    receipt_dir = root / "direction_generation_receipts" / prompt_sha256
    receipt_path = receipt_dir / f"{prompt_sha256}.json"
    from .direction_stage import _contained_transport_receipt_path

    _contained_transport_receipt_path(root, receipt_path)
    if not receipt_path.exists():
        return receipt_dir, prompt_sha256
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Existing direction transport receipt is unreadable; inspect it before retrying") from exc
    attempts = receipt.get("attempts") if isinstance(receipt, dict) else None
    if (
        not isinstance(receipt, dict)
        or receipt.get("version") != 1
        or receipt.get("prompt_sha256") != prompt_sha256
        or receipt.get("model") != model
        or receipt.get("transport") != "inline"
        or receipt.get("window") is not None
        or not isinstance(attempts, list)
    ):
        raise ValueError("Existing direction transport receipt does not match this request")
    if not attempts:
        return receipt_dir, prompt_sha256
    last = attempts[-1]
    response = last.get("response") if isinstance(last, dict) else None
    if not isinstance(last, dict) or last.get("state") != "completed" or not isinstance(response, str):
        raise ValueError(
            "Prior direction request is unresolved; preserve its receipt and do not send again"
        )
    from youtube_automation.browser.gemini_utils import is_gemini_usage_limit_text

    from .briefs import _is_provider_soft_refusal

    if _is_provider_soft_refusal(response) or is_gemini_usage_limit_text(response):
        raise ValueError(
            "Prior direction response is a refusal or quota result; preserve it and do not retry"
        )
    return receipt_dir, prompt_sha256


@contextmanager
def gemini_transport(
    *,
    persistent_chat: bool = False,
    receipt_dir: Path | None = None,
    timeout_seconds: int = 180,
    model_name: str | None = None,
) -> Iterator[Callable[[str], str]]:
    model = model_name or get_config_value("IMAGE_PLANNER_MODEL", "Pro").strip()
    if not model or len(model) > 100 or any(ord(char) < 32 for char in model):
        raise ValueError("Gemini transport model must be a bounded nonempty label")
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
                model,
                persistent_chat=persistent_chat,
                receipt_dir=receipt_dir,
                timeout_seconds=timeout_seconds,
                attachment_mode=_planner_attachment_mode(persistent_chat=persistent_chat),
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
    if stage == "adopt-polished-audio":
        from .audio_adoption import adoption_recipe

        return adoption_recipe(root, audio_file=args.polished_audio_file, audio_sha256=args.polished_audio_sha256,
            acceptance_file=args.audio_acceptance_file, acceptance_sha256=args.audio_acceptance_sha256)
    inputs: dict[str, Any] = {"version": 1, "stage": stage}
    if stage == "generate-direction":
        from .direction_stage import assert_direction_generation_allowed, direction_prompt

        generation_model = _direction_generation_model()
        inputs["direction_inputs"] = assert_direction_generation_allowed(root)
        inputs["generation_model"] = generation_model
        inputs["prompt_sha256"] = hashlib.sha256(
            direction_prompt(root, generation_model=generation_model).encode("utf-8")
        ).hexdigest()
        return fingerprint(inputs)
    if stage in {"direct", "accept-direction"}:
        from .direction_stage import CANDIDATE_FILE, direction_inputs

        inputs["direction_inputs"] = direction_inputs(root)
        if stage == "direct":
            inputs["response"] = _file_input(Path(args.direction_response_file).resolve())
        else:
            inputs["candidate"] = _file_input(root / CANDIDATE_FILE)
            inputs["candidate_sha256"] = args.direction_sha256
            inputs["reviewer"] = args.reviewer.strip()
        return fingerprint(inputs)
    paths: dict[str, Path | None] = {
        "raw": root / "raw_transcript.txt",
        "brief": root / "episode_brief.json",
        "timeline": root / "timeline.json",
        "plan": root / "shot_plan.json",
        "editorial_review": root / "editorial_review.json",
        "preview": root / "adaptive_preview.json",
        "approval": root / "editorial_approval.json",
        "config": Path(__file__).resolve().parents[3] / "video_config.txt",
        "visual_budget": root / "visual_budget.json",
        "visual_audit": root / "visual_audit.json",
    }
    stage_paths = {
        "analyze": ["raw"],
        "write": ["raw", "brief"],
        "source-audio": ["raw", "brief"],
        "plan": ["brief", "timeline"],
        "generate": ["brief", "plan", "editorial_review"],
        "report": ["plan", "editorial_review"],
        "preview": ["brief", "timeline", "plan", "editorial_review", "config"],
        "approve": ["preview"],
        "render": [
            "brief",
            "timeline",
            "plan",
            "editorial_review",
            "preview",
            "approval",
            "config",
        ],
    }
    inputs["files"] = {name: _file_input(paths[name]) for name in stage_paths[stage]}
    if stage in {"generate", "report", "preview", "approve", "render"}:
        inputs["files"]["visual_budget"] = _file_input(paths["visual_budget"])
    if stage in {"report", "preview", "approve", "render"}:
        inputs["files"]["visual_audit"] = _file_input(paths["visual_audit"])
    if stage == "analyze":
        profile = Path(args.channel_profile).resolve() if args.channel_profile else None
        inputs["channel_profile"] = _file_input(profile)
        feedback_file = getattr(args, "strategy_feedback_file", None)
        feedback = (
            Path(feedback_file).resolve()
            if feedback_file
            else None
        )
        inputs["strategy_feedback"] = _file_input(feedback)
    if stage in {"analyze", "write", "plan"}:
        inputs["planner_model"] = get_config_value("IMAGE_PLANNER_MODEL", "Pro")
        inputs["planner_profile_index"] = get_runtime_state("ACTIVE_PROFILE_INDEX", "1")
    if stage == "plan":
        inputs["planner_transport"] = get_config_value("IMAGE_PLANNER_TRANSPORT", "file")
        inputs["semantic_planner_version"] = SEMANTIC_PLANNER_VERSION
        inputs["shot_compiler_version"] = SHOT_COMPILER_VERSION
        inputs["critic_renderer_version"] = RENDERER_VERSION
        inputs["critic_render_code_sha256"] = render_code_fingerprint()
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
    if stage in {"preview", "approve", "render"}:
        from youtube_automation.video.compiler import load_video_config

        inputs["renderer_version"] = RENDERER_VERSION
        inputs["render_code_sha256"] = render_code_fingerprint()
        inputs["render_tool"] = render_tool_version()
        inputs["render_config"] = load_video_config("video_config.txt")
        try:
            timeline = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
            audio = (root / timeline["audio_file"]).resolve()
            inputs["audio"] = _file_input(audio) if audio.is_relative_to(root) else None
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            inputs["audio"] = None
    if stage == "approve":
        inputs["reviewer"] = args.reviewer
        scorecard_file = getattr(args, "scorecard_file", None)
        scorecard = Path(scorecard_file).resolve() if scorecard_file else None
        inputs["scorecard_file"] = _file_input(scorecard)
    return fingerprint(inputs)


def _stage_key(root: Path, stage: str) -> str:
    return f"stage:{root.name}:{fingerprint(str(root))[:12]}:{stage}"


def _validated_plan(root: Path) -> tuple[Brief, ShotPlan, dict[str, Any]]:
    from .audio_adoption import capture_audio_state
    from .ledger import publication_guard

    with publication_guard():
        capture_audio_state(root)
        brief = load_brief(root)
        timeline = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
        plan = ShotPlan.model_validate_json((root / "shot_plan.json").read_text(encoding="utf-8"))
    validate_plan(plan, timeline, brief)
    if brief.version >= 3:
        from .shots import require_editorial_review

        require_editorial_review(root, plan, brief)
    return brief, plan, timeline


def _render_output_complete(root: Path, *, preview: bool) -> bool:
    root = root.resolve()
    from youtube_automation.video.compiler import load_video_config

    from .flow import verify_generated_assets
    from .render import require_encoder_execution

    brief, plan, timeline = _validated_plan(root)
    verify_generated_assets(root, plan, brief)
    assets = {asset_storage_id(shot): read_shot_receipt(root, shot)["sha256"] for shot in plan.shots}
    audio = (root / timeline["audio_file"]).resolve()
    if not audio.is_relative_to(root) or not audio.is_file():
        return False
    pointer_name = "adaptive_preview.json" if preview else "active_master.json"
    pointer = json.loads((root / pointer_name).read_text(encoding="utf-8"))
    artifact = (root / pointer["path"]).resolve()
    inputs = pointer["inputs"]
    expected_config = dict(load_video_config("video_config.txt"), OUTPUT_FPS=plan.fps)
    expected_inputs = current_render_inputs(plan, assets, audio, expected_config)
    expected_status = "pending" if preview else "approved"
    if (
        not artifact.is_relative_to(root)
        or not artifact.is_file()
        or file_digest(artifact) != pointer["sha256"]
        or pointer.get("frames") != plan.total_frames
        or pointer.get("editorial_status") != expected_status
        or pointer.get("generation") != fingerprint(inputs)
        or inputs != expected_inputs
    ):
        return False
    try:
        require_encoder_execution(pointer, expected_inputs)
    except (KeyError, TypeError, ValueError):
        return False
    probe_video(artifact, plan.total_frames, plan.fps, require_audio=True)
    if not preview:
        approval = json.loads((root / "editorial_approval.json").read_text(encoding="utf-8"))
        try:
            approved_preview = require_current_preview(root, expected_inputs, plan.total_frames)
        except (OSError, KeyError, TypeError, ValueError):
            return False
        from .review import require_no_human_rejection

        require_no_human_rejection(root, fingerprint(plan), approved_preview["sha256"])
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
        if args.stage == "adopt-polished-audio":
            from .audio_adoption import PENDING, adoption_recipe, verify_audio_adoption

            if (root / PENDING).exists():
                return False
            receipt = verify_audio_adoption(root)
            return bool(receipt["recipe"] == adoption_recipe(root, audio_file=args.polished_audio_file, audio_sha256=args.polished_audio_sha256,
            acceptance_file=args.audio_acceptance_file, acceptance_sha256=args.audio_acceptance_sha256))
        if args.stage == "generate-direction":
            from .direction_stage import verify_direction_candidate

            candidate = verify_direction_candidate(root)
            model = candidate["provenance"].get("generation_model")
            return isinstance(model, str) and model == _direction_generation_model()
        if args.stage == "direct":
            from .direction_stage import candidate_matches_response

            return candidate_matches_response(root, args.direction_response_file)
        if args.stage == "accept-direction":
            from .direction_stage import direction_acceptance_complete

            return direction_acceptance_complete(
                root, reviewer=args.reviewer, candidate_sha256=args.direction_sha256
            )
        if args.stage == "analyze":
            if visual_policy_migration_pending(root):
                return False
            brief = load_brief(root)
            raw = (root / "raw_transcript.txt").read_text(encoding="utf-8-sig")
            channel = load_channel(args.channel_profile)
            return (
                brief.source_sha256 == fingerprint(raw)
                and brief.profile_sha256 == fingerprint(channel)
                and (
                    channel.version < 3
                    or (brief.version >= 3 and brief.visual_strategy is not None)
                )
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
            brief, plan, _ = _validated_plan(root)

            assets = {
                asset_storage_id(shot): read_shot_receipt(root, shot)["sha256"] for shot in plan.shots
            }
            preview = json.loads((root / "adaptive_preview.json").read_text(encoding="utf-8"))
            from .review import require_no_human_rejection

            require_no_human_rejection(root, fingerprint(plan), preview["sha256"])
            approval = json.loads((root / "editorial_approval.json").read_text(encoding="utf-8"))
            expected = {
                "version": 1,
                "plan": fingerprint(plan),
                "assets": assets,
                "generation": preview["generation"],
                "preview_sha256": preview["sha256"],
                "reviewer": args.reviewer.strip(),
            }
            if brief.version >= 3:
                from .review import PreviewScorecard

                scorecard = PreviewScorecard.model_validate_json(
                    (root / "preview_scorecard.json").read_text(encoding="utf-8")
                )
                expected["version"] = 2
                expected["scorecard_sha256"] = fingerprint(scorecard)
            return bool(approval == expected)
        if args.stage == "render":
            return _render_output_complete(root, preview=False)
    except Exception:
        return False
    return False


def _execute_stage(args: argparse.Namespace, root: Path, database: Path) -> None:
    if args.stage == "adopt-polished-audio":
        from .audio_adoption import adopt_polished_audio

        print(adopt_polished_audio(root, audio_file=args.polished_audio_file, audio_sha256=args.polished_audio_sha256,
            acceptance_file=args.audio_acceptance_file, acceptance_sha256=args.audio_acceptance_sha256))
        return
    if args.stage == "generate-direction":
        from .direction_stage import (
            CANDIDATE_FILE,
            assert_direction_generation_allowed,
            direction_prompt,
            ensure_direction_candidate,
            recover_direction_candidate,
            verify_direction_candidate,
        )

        assert_direction_generation_allowed(root)
        generation_model = _direction_generation_model()
        candidate_path = root / CANDIDATE_FILE
        candidate = recover_direction_candidate(root, generation_model=generation_model)
        if candidate is None and candidate_path.is_file():
            candidate = verify_direction_candidate(root)
            if candidate["provenance"].get("generation_model") != generation_model:
                raise ValueError(
                    "A current candidate exists without matching automated generation provenance; preserve it"
                )
        elif candidate is None:
            prompt = direction_prompt(root, generation_model=generation_model)
            receipt_dir, prompt_sha256 = _direction_transport_receipt(
                root, model=generation_model, prompt=prompt
            )
            transport_receipt_path = receipt_dir / f"{prompt_sha256}.json"
            with leased_resource(database, "browser"), gemini_transport(
                model_name=generation_model, receipt_dir=receipt_dir
            ) as ask:
                candidate = ensure_direction_candidate(
                    root,
                    ask,
                    generation_model=generation_model,
                    transport_receipt_path=transport_receipt_path,
                )
        print(
            f"Unapproved generated direction candidate: {candidate_path} "
            f"({file_digest(candidate_path)})"
        )
    elif args.stage == "direct":
        from .direction_stage import (
            CANDIDATE_FILE,
            candidate_matches_response,
            ensure_direction_candidate,
        )

        response = Path(args.direction_response_file).read_text(encoding="utf-8-sig")
        ensure_direction_candidate(root, lambda _: response)
        if not candidate_matches_response(root, args.direction_response_file):
            raise ValueError("Existing direction candidate belongs to another response")
        print(f"Unapproved direction candidate: {root / CANDIDATE_FILE} ({file_digest(root / CANDIDATE_FILE)})")
    elif args.stage == "accept-direction":
        from .direction_stage import accept_direction

        print(accept_direction(root, reviewer=args.reviewer, candidate_sha256=args.direction_sha256))
    elif args.stage == "analyze":
        if not args.channel_profile:
            raise ValueError("analyze requires --channel-profile")
        channel = load_channel(args.channel_profile)
        feedback = ""
        if args.strategy_feedback_file:
            feedback = Path(args.strategy_feedback_file).read_text(encoding="utf-8-sig")
            if not feedback.strip():
                raise ValueError("Strategy feedback file is empty")
        with leased_resource(database, "browser"), gemini_transport() as ask:
            if requires_visual_strategy_migration(root, channel):
                rebind_visual_policy(root, channel, ask=ask, strategy_feedback=feedback,
                                     profile_path=args.channel_profile, feedback_path=args.strategy_feedback_file)
            else:
                if is_visual_policy_update(root, channel):
                    rebind_visual_policy(root, channel)
                ensure_brief(root, channel, ask, strategy_feedback=feedback)
    elif args.stage == "write" and (root / "script_acceptance.json").is_file():
        from .writing import publish_accepted_original

        # A human-accepted original script is published verbatim: no browser, no model.
        publish_accepted_original(root, load_brief(root))
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
        scorecard_file = getattr(args, "scorecard_file", None)
        if scorecard_file:
            from .review import record_preview_scorecard

            score_payload = json.loads(
                Path(scorecard_file).read_text(encoding="utf-8-sig")
            )
            record_preview_scorecard(root, args.reviewer, score_payload)
        approve_review(root, args.reviewer)
    else:
        from youtube_automation.video.compiler import load_video_config

        print(
            render_plan(
                root, load_video_config("video_config.txt"), preview=args.stage == "preview"
            )
        )


def _run_stage_attempt(args: argparse.Namespace, root: Path, database: Path) -> None:
    """Run one content-bound stage attempt for the currently active profile."""
    from .audio_adoption import assert_no_pending_audio_adoption

    if args.stage != "adopt-polished-audio":
        assert_no_pending_audio_adoption(root)
    reconcile_invalidation(root)
    recipe = _stage_recipe(root, args)
    key = _stage_key(root, args.stage)
    existing = Ledger(database).get(key)
    complete = _stage_complete(root, args)
    visual_policy_transition: tuple[str, str] | None = None
    strategy_migration = bool(args.stage == "analyze" and args.channel_profile
                              and requires_visual_strategy_migration(root, load_channel(args.channel_profile)))
    if args.stage == "analyze" and args.channel_profile and not strategy_migration:
        requested_channel = load_channel(args.channel_profile)
        if is_visual_policy_update(root, requested_channel):
            visual_policy_transition = (
                load_brief(root).profile_sha256,
                fingerprint(requested_channel),
            )
        elif args.strategy_feedback_file and not strategy_migration:
            feedback_path = Path(args.strategy_feedback_file).resolve()
            visual_policy_transition = (
                fingerprint(load_brief(root)),
                _file_input(feedback_path) or "missing-feedback",
            )
    visual_policy_rebind = visual_policy_transition is not None
    # A feedback file is an explicit request to replace the current strategy.
    # The existing brief can still be valid without proving that feedback was applied.
    adoptable = args.stage != "report" and not bool(args.strategy_feedback_file)
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
        force=(
            args.force_retry
            or repair_success
            or recover_complete
            or visual_policy_rebind
        ),
        detail={"stage": args.stage, "run": str(root)},
    ) as execute:
        if not execute:
            print(f"Stage already succeeded for unchanged inputs: {args.stage}")
            return
        if visual_policy_transition is not None:
            archived = invalidate_stage(
                root, "plan", visual_policy_transition[0], visual_policy_transition[1]
            )
            if archived:
                print(
                    f"Archived {len(archived)} invalidated activation file(s) "
                    f"before retrying stage: {args.stage}"
                )
            complete = _stage_complete(root, args)
        elif (existing and existing["recipe"] != recipe and args.stage != "adopt-polished-audio"
              and not strategy_migration):
            preserve_paths: set[str] | None = None
            if args.stage == "plan":
                archive_editorial_rejection_for_retry(root)
            if args.stage == "plan" and migrate_semantic_checkpoint(root):
                preserve_paths = {"shot_plan.semantic.partial.json"}
            if preserve_paths:
                archived = invalidate_stage(
                    root,
                    args.stage,
                    existing["recipe"],
                    recipe,
                    preserve_paths=preserve_paths,
                )
            else:
                archived = invalidate_stage(
                    root, args.stage, existing["recipe"], recipe
                )
            if archived:
                print(
                    f"Archived {len(archived)} invalidated activation file(s) "
                    f"before retrying stage: {args.stage}"
                )
            complete = _stage_complete(root, args)
        if adoptable and complete:
            print(f"Registered existing verified stage output: {args.stage}")
            return
        _execute_stage(args, root, database)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Adaptive multi-channel production (explicit run, opt-in)"
    )
    parser.add_argument(
        "stage",
        choices=[
            "analyze",
            "write",
            "direct",
            "generate-direction",
            "accept-direction",
            "source-audio",
            "adopt-polished-audio",
            "plan",
            "generate",
            "report",
            "preview",
            "approve",
            "render",
            "proofs",
            "status",
            "diagnose",
        ],
    )
    parser.add_argument("--run-dir", help="existing explicit run directory for production stages")
    parser.add_argument("--polished-audio-file", help="exact previously owner-accepted local WAV")
    parser.add_argument("--polished-audio-sha256", help="owner-accepted WAV SHA-256; no transcoding")
    parser.add_argument("--audio-acceptance-file", help="existing exact human audio acceptance JSON")
    parser.add_argument("--audio-acceptance-sha256", help="exact acceptance authority SHA-256")
    parser.add_argument("--last", action="store_true", help="diagnose only: show the latest bounded failure record")
    parser.add_argument("--path", dest="diagnostic_path", help="diagnose only: optional local failure JSONL path")
    parser.add_argument("--channel-profile")
    parser.add_argument(
        "--direction-response-file",
        help="local UTF-8 JSON response for an unapproved voice-direction candidate; no provider request",
    )
    parser.add_argument(
        "--direction-sha256", help="exact candidate file SHA-256 for explicit voice-direction acceptance"
    )
    parser.add_argument(
        "--strategy-feedback-file",
        help="UTF-8 editorial rejection used to revise a v3 episode visual strategy",
    )
    parser.add_argument("--reviewer")
    parser.add_argument(
        "--scorecard-file",
        help="JSON scores for semantic match, hook, attraction, progression, continuity, readability and motion",
    )
    parser.add_argument("--media-file")
    parser.add_argument("--start-seconds", type=float)
    parser.add_argument("--end-seconds", type=float)
    parser.add_argument(
        "--force-retry",
        action="store_true",
        help="retry a corrected stage after its bounded failure circuit opens",
    )
    args = parser.parse_args(argv)
    if args.stage == "diagnose":
        if not args.last:
            parser.error("diagnose requires --last")
        from youtube_automation.core.failure_record import digest, load_last_record

        record = load_last_record(args.diagnostic_path)
        print("No failure records." if record is None else digest(record))
        return
    if args.last or args.diagnostic_path:
        parser.error("--last and --path apply only to diagnose")
    if not args.run_dir:
        parser.error("--run-dir is required for production stages")
    root = Path(args.run_dir).resolve()
    if not root.is_dir():
        parser.error("Run directory must already exist")
    if args.stage == "proofs":
        from .render_proofs import render_current_proofs

        print(render_current_proofs(root))
        return
    # Shared across runs in this installation; never scope exclusive devices per run.
    database = resource_database()
    if args.stage == "direct" and not args.direction_response_file:
        parser.error("direct requires --direction-response-file; provider requests need separate authorization")
    if args.direction_response_file and args.stage != "direct":
        parser.error("--direction-response-file applies only to direct")
    if args.stage == "accept-direction" and (not args.reviewer or not args.direction_sha256):
        parser.error("accept-direction requires --reviewer and --direction-sha256 after human review")
    if args.direction_sha256 and args.stage != "accept-direction":
        parser.error("--direction-sha256 applies only to accept-direction")
    if args.stage == "analyze" and not args.channel_profile:
        parser.error("analyze requires --channel-profile")
    if args.strategy_feedback_file and args.stage != "analyze":
        parser.error("--strategy-feedback-file applies only to analyze")
    if args.strategy_feedback_file and not args.force_retry:
        parser.error("--strategy-feedback-file requires --force-retry")
    if args.stage == "source-audio" and (
        args.media_file is None or args.start_seconds is None or args.end_seconds is None
    ):
        parser.error("source-audio requires --media-file, --start-seconds and --end-seconds")
    if args.stage == "approve" and not args.reviewer:
        parser.error("approve requires --reviewer after an actual editorial review")
    adoption_flags = (args.polished_audio_file, args.polished_audio_sha256,
                      args.audio_acceptance_file, args.audio_acceptance_sha256)
    if args.stage == "adopt-polished-audio" and not all(adoption_flags):
        parser.error("adopt-polished-audio requires all four explicit audio/acceptance path and hash flags")
    if any(adoption_flags) and args.stage != "adopt-polished-audio":
        parser.error("Polished audio acceptance flags apply only to adopt-polished-audio")
    if args.stage == "adopt-polished-audio":
        _run_stage_attempt(args, root, database)
        return
    if args.stage == "status":
        database.parent.mkdir(exist_ok=True)
        for row in Ledger(database).status():
            print(row)
    else:
        if args.stage in {"report", "preview", "approve", "render"} and (root / "visual_budget.json").is_file():
            from .visual_gate import require_visual_audit

            brief, plan, _ = _validated_plan(root)
            require_visual_audit(root, plan, brief)
        failover_stages = {"analyze", "write", "plan"}
        accepted_write = args.stage == "write" and (root / "script_acceptance.json").is_file()
        if args.stage in failover_stages and not accepted_write and not _stage_complete(root, args):
            from youtube_automation.browser import network_health

            network_health.require_healthy(network_health.GEMINI_URL)
        attempted_profiles = {active_profile_index()}
        failover_limit = max(0, int(get_config_value("FAILOVER_RETRY_LIMIT", "4")))
        failovers = 0
        while True:
            try:
                _run_stage_attempt(args, root, database)
                return
            except GeminiUsageLimitError as exc:
                if args.stage not in failover_stages:
                    raise
                current = active_profile_index()
                target = next_profile_index(current)
                if failovers >= failover_limit or target in attempted_profiles:
                    raise RuntimeError(
                        "Gemini App quota is exhausted across the bounded profile failover ring"
                    ) from exc
                with leased_resource(database, "browser"):
                    activated = failover_owned_browser_profile()
                if activated != target:
                    raise RuntimeError(
                        f"Gemini profile failover selected unexpected account {activated}; "
                        f"expected {target}"
                    ) from exc
                attempted_profiles.add(activated)
                failovers += 1
                print(
                    f"Gemini App quota exhausted on profile {current}; "
                    f"retrying the exact stage request on verified profile {activated}."
                )
            except ValueError as exc:
                parser.error(str(exc))
