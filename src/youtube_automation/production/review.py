"""Review evidence is explicit; technical validation never self-approves aesthetics."""

from __future__ import annotations

import html
import json
import shutil
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw
from pydantic import Field, model_validator

from youtube_automation.core.utils import atomic_write_json

from .assets import asset_storage_id, file_digest, read_shot_receipt
from .contracts import Brief, Contract, Digest, Text, fingerprint, load_brief
from .flow import verify_generated_assets
from .ledger import publication_guard
from .shots import ShotPlan, require_editorial_review, validate_plan
from .writing import atomic_text


class HumanPreviewRejection(Contract):
    version: Literal[1] = 1
    decision: Literal["rejected"] = "rejected"
    reviewer: Text
    overall_rating: float | None = Field(default=None, ge=0, le=5)
    rating_scale: Literal[5] = 5
    plan_sha256: Digest
    preview_sha256: Digest
    source_sha256: Digest | None = None
    reasons: list[Text] = Field(min_length=1)
    supersedes: str = "human_review_intent.json"
    required_next: Text
    source: Text


def record_preview_rejection(
    run_dir: str | Path,
    reviewer: str,
    reasons: list[str],
    *,
    overall_rating: float | None = None,
) -> HumanPreviewRejection:
    root = Path(run_dir).resolve()
    plan = ShotPlan.model_validate_json((root / "shot_plan.json").read_text(encoding="utf-8"))
    preview = json.loads((root / "adaptive_preview.json").read_text(encoding="utf-8"))
    artifact = (root / preview["path"]).resolve()
    if (
        not artifact.is_relative_to(root)
        or file_digest(artifact) != preview["sha256"]
        or preview["inputs"]["plan"] != fingerprint(plan)
    ):
        raise ValueError("Rejection must bind the current verified preview and plan")
    rejection = HumanPreviewRejection(
        reviewer=reviewer.strip(),
        overall_rating=overall_rating,
        plan_sha256=fingerprint(plan),
        preview_sha256=preview["sha256"],
        source_sha256=load_brief(root).source_sha256,
        reasons=reasons,
        required_next="Revise the preview and obtain a fresh complete human review.",
        source="Explicit human feedback; an overall rating is not seven dimension scores.",
    )
    archive = root / "editorial_rejections" / "human" / fingerprint(rejection)
    with publication_guard():
        if json.loads((root / "adaptive_preview.json").read_text(encoding="utf-8")) != preview:
            raise ValueError("Preview changed while recording human rejection")
        archive.mkdir(parents=True, exist_ok=True)
        atomic_write_json(str(archive / "rejection.json"), rejection.model_dump(mode="json"))
        atomic_write_json(str(root / "human_review_rejection.json"), rejection.model_dump(mode="json"))
        for name in ("human_review_intent.json", "visual_audit.json", "preview_scorecard.json"):
            path = root / name
            if path.exists():
                destination = archive / f"{path.stem}-{file_digest(path)}{path.suffix}"
                if not destination.exists():
                    temporary = destination.with_suffix(".tmp")
                    shutil.copyfile(path, temporary)
                    temporary.replace(destination)
                if file_digest(destination) != file_digest(path):
                    raise ValueError("Human-rejection evidence archive failed byte verification")
                if name != "human_review_intent.json":
                    path.unlink()
    return rejection


def require_no_human_rejection(
    root: Path, plan_sha256: str, preview_sha256: str
) -> None:
    paths = [root / "human_review_rejection.json"]
    paths.extend(sorted((root / "editorial_rejections" / "human").glob("*/rejection.json")))
    for path in paths:
        if not path.exists():
            continue
        rejection = HumanPreviewRejection.model_validate_json(path.read_text(encoding="utf-8"))
        if rejection.preview_sha256 == preview_sha256:
            raise ValueError("Human rejected this preview; a revised preview and fresh review are required")


class PreviewScorecard(Contract):
    version: Literal[1] = 1
    plan_sha256: Digest
    preview_sha256: Digest
    reviewer: Text
    semantic_match: int = Field(ge=1, le=5)
    hook_strength: int = Field(ge=1, le=5)
    attractiveness: int = Field(ge=1, le=5)
    progression: int = Field(ge=1, le=5)
    continuity: int = Field(ge=1, le=5)
    readability: int = Field(ge=1, le=5)
    motion: int = Field(ge=1, le=5)
    notes: Text

    @model_validator(mode="after")
    def require_publishable_scores(self) -> PreviewScorecard:
        dimensions = (
            self.semantic_match,
            self.hook_strength,
            self.attractiveness,
            self.progression,
            self.continuity,
            self.readability,
            self.motion,
        )
        if min(dimensions) < 4:
            raise ValueError("Every preview quality dimension must score at least 4 to approve")
        return self


def record_preview_scorecard(
    run_dir: str | Path, reviewer: str, scores: dict[str, object]
) -> PreviewScorecard:
    from .audio_adoption import (
        assert_current_audio_state,
        capture_audio_state,
    )
    root = Path(run_dir)
    with publication_guard():
        audio_state = capture_audio_state(root, validate_pair=True)
    _, plan = review_context(root)
    preview = json.loads((root / "adaptive_preview.json").read_text(encoding="utf-8"))
    artifact = (root / preview["path"]).resolve()
    if not artifact.is_relative_to(root.resolve()) or file_digest(artifact) != preview["sha256"]:
        raise ValueError("Preview artifact changed or is outside this run")
    require_no_human_rejection(root, fingerprint(plan), preview["sha256"])
    scorecard = PreviewScorecard.model_validate(
        {
            **scores,
            "version": 1,
            "plan_sha256": fingerprint(plan),
            "preview_sha256": preview["sha256"],
            "reviewer": reviewer.strip(),
        }
    )
    with publication_guard():
        assert_current_audio_state(root, audio_state, validate_pair=True)
        require_no_human_rejection(root, fingerprint(plan), preview["sha256"])
        atomic_write_json(
            str(root / "preview_scorecard.json"), scorecard.model_dump(mode="json")
        )
    return scorecard


def review_context(root: Path) -> tuple[Brief, ShotPlan]:
    from .audio_adoption import (
        capture_audio_state,
        require_adopted_audio_review,
    )
    with publication_guard():
        capture_audio_state(root)
        brief = load_brief(root)
        require_adopted_audio_review(root, brief)
        plan = ShotPlan.model_validate_json((root / "shot_plan.json").read_text(encoding="utf-8"))
        timeline = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
    validate_plan(plan, timeline, brief)
    if brief.version >= 3:
        require_editorial_review(root, plan, brief)
    return brief, plan


def write_review(run_dir: str | Path) -> Path:
    from .audio_adoption import (
        assert_current_audio_state,
        capture_audio_state,
    )
    root = Path(run_dir)
    with publication_guard():
        audio_state = capture_audio_state(root, validate_pair=True)
    brief, plan = review_context(root)
    output = root / "adaptive_review"
    output.mkdir(exist_ok=True)
    rows = []
    # Paginated sheets remain bounded for long episodes.
    for offset in range(0, len(plan.shots), 20):
        batch = plan.shots[offset : offset + 20]
        sheet = Image.new("RGB", (1280, ((len(batch) + 3) // 4) * 210), "#171b24")
        draw = ImageDraw.Draw(sheet)
        for index, shot in enumerate(batch):
            x, y = (index % 4) * 320, (index // 4) * 210
            status = "missing or invalid"
            prompt = ""
            try:
                receipt = read_shot_receipt(root, shot)
                with Image.open(root / receipt["path"]) as image:
                    thumbnail = image.convert("RGB")
                    thumbnail.thumbnail((320, 180))
                    sheet.paste(thumbnail, (x, y))
                status = "technically verified; editorial review pending"
                prompt = receipt["prompt"]
            except (OSError, ValueError, KeyError):
                pass
            draw.text((x + 5, y + 184), shot.shot_id, fill="white")
            values = [
                shot.shot_id,
                f"{shot.start_frame / plan.fps:.2f}-{shot.end_frame / plan.fps:.2f}",
                shot.purpose,
                shot.treatment,
                shot.motion,
                f"({shot.focal_x:.2f}, {shot.focal_y:.2f}); zoom {shot.zoom:.3f}",
                shot.reference_asset_id or "none",
                status,
                prompt,
            ]
            rows.append(
                "<tr>"
                + "".join("<td>" + html.escape(value) + "</td>" for value in values)
                + "</tr>"
            )
        sheet.save(output / f"sheet_{offset // 20 + 1:03d}.jpg", quality=90)
    sheets = "".join(
        f'<img alt="Storyboard page {i + 1}" src="sheet_{i + 1:03d}.jpg">'
        for i in range((len(plan.shots) + 19) // 20)
    )
    page = "<!doctype html><meta charset='utf-8'><title>Editorial review</title><style>body{font:16px system-ui;margin:32px;background:#f6f7fa;color:#172033}img{max-width:100%}td,th{padding:10px;border:1px solid #ccd;vertical-align:top}table{border-collapse:collapse}td{max-width:420px}</style>"
    page += (
        "<h1>"
        + html.escape(brief.channel.name)
        + " — editorial review</h1><p>Check narration relevance, identity, meaningful progression, mobile readability and every crop. Passing file/OCR checks does not establish these qualities.</p>"
        + sheets
    )
    page += (
        "<table><thead><tr>"
        + "".join(
            "<th>" + title + "</th>"
            for title in [
                "Shot",
                "Seconds",
                "Purpose",
                "Treatment",
                "Motion",
                "Focal / zoom",
                "Reference",
                "Status",
                "Exact prompt",
            ]
        )
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )
    with publication_guard():
        assert_current_audio_state(root, audio_state)
        atomic_text(output / "index.html", page)
    return output / "index.html"


def approve_review(
    run_dir: str | Path,
    reviewer: str,
    *,
    config: dict[str, Any] | None = None,
    encoder_config: dict[str, Any] | None = None,
    asset_identity: Literal["storage", "shot"] = "storage",
) -> None:
    """Approve exact preview inputs using default or explicitly supplied render recipes."""
    if not reviewer.strip():
        raise ValueError("Record the person who reviewed the preview")
    if asset_identity not in {"storage", "shot"}:
        raise ValueError("Unknown render asset identity")
    from .audio_adoption import (
        assert_current_audio_state,
        capture_audio_state,
    )
    root = Path(run_dir)
    with publication_guard():
        audio_state = capture_audio_state(root, validate_pair=True)
    brief, plan = review_context(root)
    verify_generated_assets(root, plan, brief)
    hashes = {asset_storage_id(s): read_shot_receipt(root, s)["sha256"] for s in plan.shots}
    preview = json.loads((root / "adaptive_preview.json").read_text(encoding="utf-8"))
    artifact = (root / preview["path"]).resolve()
    if not artifact.is_relative_to(root.resolve()) or file_digest(artifact) != preview["sha256"]:
        raise ValueError("Preview artifact changed or is outside this run")
    require_no_human_rejection(root, fingerprint(plan), preview["sha256"])
    timeline = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
    audio = (root / timeline["audio_file"]).resolve()
    if not audio.is_relative_to(root.resolve()):
        raise ValueError("Canonical audio escapes run directory")
    inputs = preview["inputs"]
    from youtube_automation.video.compiler import load_video_config

    from .render import current_render_inputs, probe_video, require_current_preview
    from .visual_gate import _render_input_assets

    render_assets = _render_input_assets(plan, hashes, asset_identity)
    render_config = load_video_config("video_config.txt") if config is None else config
    if encoder_config is None:
        expected_inputs = current_render_inputs(plan, render_assets, audio, render_config)
    else:
        expected_inputs = current_render_inputs(
            plan, render_assets, audio, render_config, encoder_config=encoder_config
        )
    if (
        inputs != expected_inputs
        or fingerprint(inputs) != preview["generation"]
        or preview.get("frames") != plan.total_frames
        or preview.get("editorial_status") != "pending"
    ):
        raise ValueError("Preview is stale; render a new preview before approval")
    probe_video(artifact, plan.total_frames, plan.fps, require_audio=True)
    scorecard = None
    if brief.version >= 3:
        scorecard = PreviewScorecard.model_validate_json(
            (root / "preview_scorecard.json").read_text(encoding="utf-8")
        )
        if (
            scorecard.plan_sha256 != fingerprint(plan)
            or scorecard.preview_sha256 != preview["sha256"]
            or scorecard.reviewer != reviewer.strip()
        ):
            raise ValueError("Preview scorecard does not match this preview, plan and reviewer")
    approval = {
        "version": 1,
        "plan": fingerprint(plan),
        "assets": hashes,
        "generation": preview["generation"],
        "preview_sha256": preview["sha256"],
        "reviewer": reviewer.strip(),
    }
    if scorecard is not None:
        approval["version"] = 2
        approval["scorecard_sha256"] = fingerprint(scorecard)
    with publication_guard():
        assert_current_audio_state(root, audio_state, validate_pair=True)
        if require_current_preview(root, expected_inputs, plan.total_frames) != preview:
            raise ValueError("Preview changed while approving the review")
        require_no_human_rejection(root, fingerprint(plan), preview["sha256"])
        atomic_write_json(
            str(root / "editorial_approval.json"),
            approval,
        )
