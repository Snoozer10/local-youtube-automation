"""Review evidence is explicit; technical validation never self-approves aesthetics."""

from __future__ import annotations

import html
import json
from pathlib import Path

from PIL import Image, ImageDraw

from youtube_automation.core.utils import atomic_write_json

from .assets import file_digest, read_receipt
from .contracts import Brief, fingerprint, load_brief
from .flow import verify_generated_assets
from .shots import ShotPlan, validate_plan
from .writing import atomic_text


def review_context(root: Path) -> tuple[Brief, ShotPlan]:
    brief = load_brief(root)
    plan = ShotPlan.model_validate_json((root / "shot_plan.json").read_text(encoding="utf-8"))
    timeline = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
    validate_plan(plan, timeline, brief)
    return brief, plan


def write_review(run_dir: str | Path) -> Path:
    root = Path(run_dir)
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
                receipt = read_receipt(root, shot.asset_id)
                with Image.open(root / receipt["path"]) as image:
                    image = image.convert("RGB")
                    image.thumbnail((320, 180))
                    sheet.paste(image, (x, y))
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
                "Reference",
                "Status",
                "Exact prompt",
            ]
        )
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )
    atomic_text(output / "index.html", page)
    return output / "index.html"


def approve_review(run_dir: str | Path, reviewer: str) -> None:
    if not reviewer.strip():
        raise ValueError("Record the person who reviewed the preview")
    root = Path(run_dir)
    brief, plan = review_context(root)
    verify_generated_assets(root, plan, brief)
    hashes = {s.asset_id: read_receipt(root, s.asset_id)["sha256"] for s in plan.shots}
    preview = json.loads((root / "adaptive_preview.json").read_text(encoding="utf-8"))
    artifact = (root / preview["path"]).resolve()
    if not artifact.is_relative_to(root.resolve()) or file_digest(artifact) != preview["sha256"]:
        raise ValueError("Preview artifact changed or is outside this run")
    timeline = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
    audio = (root / timeline["audio_file"]).resolve()
    if not audio.is_relative_to(root.resolve()):
        raise ValueError("Canonical audio escapes run directory")
    inputs = preview["inputs"]
    if (
        inputs["plan"] != fingerprint(plan)
        or inputs["assets"] != hashes
        or inputs["audio"] != file_digest(audio)
        or fingerprint(inputs) != preview["generation"]
    ):
        raise ValueError("Preview is stale; render a new preview before approval")
    atomic_write_json(
        str(root / "editorial_approval.json"),
        {
            "version": 1,
            "plan": fingerprint(plan),
            "assets": hashes,
            "generation": preview["generation"],
            "preview_sha256": preview["sha256"],
            "reviewer": reviewer.strip(),
        },
    )
