"""Offline verifier for explicitly selected adaptive-production receipts.

A caller-supplied version 1 receipt may pin exact artifact bytes and/or request
named semantic acceptance profiles. Relative paths resolve from the receipt
directory. No production run is assumed; the selected checks are read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

# Keep the standalone acceptance command aligned with pytest's configured
# ``src`` import path when it calls existing production validators.
_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
_REPOSITORY_ROOT = _SOURCE_ROOT.parent
for _import_root in (_REPOSITORY_ROOT, _SOURCE_ROOT):
    if str(_import_root) not in sys.path:
        sys.path.insert(0, str(_import_root))

_MAX_RECEIPT_BYTES = 1_048_576
_MAX_ARTIFACT_BYTES = 4 * 1024 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ReceiptError(ValueError):
    """A selected receipt or one of its pinned artifacts is invalid."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptError(f"duplicate receipt key: {key}")
        result[key] = value
    return result


def _read_receipt(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > _MAX_RECEIPT_BYTES:
            raise ReceiptError("receipt exceeds the 1 MiB limit")
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptError(f"cannot read selected receipt: {exc}") from exc
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ReceiptError("receipt must be a version 1 object")
    artifacts = value.get("artifacts")
    checks = value.get("semantic_checks", [])
    if not isinstance(artifacts, list) or (not artifacts and not checks):
        raise ReceiptError("receipt needs artifact pins or semantic checks")
    return value


def audit_receipt(receipt_path: str | Path) -> list[dict[str, Any]]:
    """Verify exact bytes for the paths named by one caller-selected receipt."""
    receipt = Path(receipt_path).resolve()
    payload = _read_receipt(receipt)
    verified: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for index, item in enumerate(payload.get("artifacts", [])):
        if not isinstance(item, dict):
            raise ReceiptError(f"artifact {index} must be an object")
        path_value = item.get("path")
        expected_size = item.get("size_bytes")
        expected_hash = item.get("sha256")
        if (
            not isinstance(path_value, str)
            or not path_value.strip()
            or isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
            or not isinstance(expected_hash, str)
            or not _SHA256.fullmatch(expected_hash)
        ):
            raise ReceiptError(f"artifact {index} needs path, size_bytes and lowercase SHA-256")
        path = Path(path_value)
        path = (path if path.is_absolute() else receipt.parent / path).resolve()
        if path in seen:
            raise ReceiptError(f"duplicate artifact path: {path}")
        seen.add(path)
        try:
            size = path.stat().st_size
            if not path.is_file() or size > _MAX_ARTIFACT_BYTES:
                raise ReceiptError(f"artifact is missing, not a file, or exceeds 4 GiB: {path}")
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise ReceiptError(f"cannot read artifact {path}: {exc}") from exc
        actual_hash = digest.hexdigest()
        if size != expected_size or actual_hash != expected_hash:
            raise ReceiptError(
                f"artifact pin mismatch: {path} "
                f"(size {size}/{expected_size}, sha256 {actual_hash}/{expected_hash})"
            )
        verified.append({"path": str(path), "size_bytes": size, "sha256": actual_hash})
    _run_semantic_checks(receipt, payload)
    return verified


def _selected_path(receipt: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ReceiptError("semantic check paths must be non-empty strings")
    path = Path(value)
    return (path if path.is_absolute() else receipt.parent / path).resolve()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReceiptError(message)


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptError(f"cannot read semantic JSON artifact {path}: {exc}") from exc


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _audit_pilot_profile(receipt: Path, check: dict[str, Any]) -> None:
    """Run historical timeline, shot-plan and canary checks on a selected pilot."""
    from youtube_automation.production.contracts import fingerprint, load_brief
    from youtube_automation.production.shots import ShotPlan, validate_plan
    from youtube_automation.timeline.engine import load_timeline_or_shim
    from youtube_automation.visuals.flow_generator import (
        _select_canary_storyboard,
        parse_json_prompts,
    )

    run_dir = _selected_path(receipt, check.get("run_dir"))
    timeline_path = run_dir / "timeline.json"
    timeline = _json(timeline_path)
    expected = check.get("expected")
    if not isinstance(expected, dict):
        raise ReceiptError("pilot_profile requires an expected object")
    for key in ("version", "fps", "total_frames", "audio_duration"):
        if key in expected:
            _require(timeline.get(key) == expected[key], f"pilot timeline {key} mismatch")
    _require(len(timeline.get("words", [])) == expected.get("words"), "pilot timeline word count mismatch")
    _require(len(timeline.get("spans", [])) == expected.get("spans"), "pilot timeline span count mismatch")
    spans = timeline["spans"]
    _require(bool(spans) and spans[0]["start_frame"] == 0, "pilot timeline must start at frame zero")
    _require(spans[-1]["end_frame"] == expected["total_frames"], "pilot timeline end frame mismatch")
    for previous, current in zip(spans[:-1], spans[1:], strict=True):
        _require(current["start_frame"] == previous["end_frame"], "pilot timeline has a frame gap")
    blocks = load_timeline_or_shim(str(run_dir))
    _require(len(blocks) == expected["loaded_blocks"], "production timeline loader block count mismatch")

    brief_source = (
        run_dir / "episode_brief.v2.json"
        if expected.get("plan_version") == 2 and (run_dir / "episode_brief.v2.json").is_file()
        else run_dir
    )
    brief = load_brief(brief_source)
    plan_path = run_dir / "shot_plan.json"
    plan = ShotPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    _require(plan.version == expected["plan_version"], "pilot shot-plan version mismatch")
    _require(plan.fps == expected["fps"], "pilot shot-plan fps mismatch")
    _require(plan.total_frames == expected["total_frames"], "pilot shot-plan duration mismatch")
    _require(len(plan.shots) == expected["shots"], "pilot shot count mismatch")
    _require(plan.timeline_sha256 == fingerprint(timeline), "pilot timeline lineage mismatch")
    _require(plan.brief_sha256 == fingerprint(brief), "pilot brief lineage mismatch")
    validate_plan(plan, timeline, brief)

    max_frames = round(plan.editorial_policy.max_shot_seconds * plan.fps)
    _require(max_frames == expected["max_shot_frames"], "pilot cadence limit mismatch")
    _require(
        all(shot.end_frame - shot.start_frame <= max_frames for shot in plan.shots),
        "pilot shot exceeds cadence limit",
    )
    script = (run_dir / "refined_script.txt").read_text(encoding="utf-8").strip()
    words = script.split()
    _require(len(words) == expected["words"], "pilot refined-script word count mismatch")
    plan_words = " ".join(shot.narration_excerpt for shot in plan.shots).split()
    _require(plan_words == words, "pilot shot excerpts do not preserve narration words")

    prompts = parse_json_prompts(str(run_dir / "flow_prompts.json"))
    _require(len(prompts) == len(plan.shots), "pilot Flow prompt count mismatch")
    prompt_ids = [frame.raw_payload["adaptive_shot"]["shot_id"] for frame in prompts]
    _require(prompt_ids == [shot.shot_id for shot in plan.shots], "pilot Flow prompts do not match the validated shot plan")
    canary_ids = check.get("canary_ids")
    if not isinstance(canary_ids, list) or not 1 <= len(canary_ids) <= 3:
        raise ReceiptError("pilot_profile requires one to three canary_ids")
    selected = _select_canary_storyboard(prompts, canary_ids)
    selected_ids = [frame.raw_payload["adaptive_shot"]["shot_id"] for frame in selected]
    _require(selected_ids == canary_ids, "pilot canary selection order mismatch")
    try:
        _select_canary_storyboard(prompts, ["__unknown_acceptance_shot__"])
    except ValueError:
        pass
    else:
        raise ReceiptError("pilot canary accepted an unknown shot")
    if len(plan.shots) >= 4:
        too_many = [shot.shot_id for shot in plan.shots[:4]]
        try:
            _select_canary_storyboard(prompts, too_many)
        except ValueError:
            pass
        else:
            raise ReceiptError("pilot canary accepted more than three shots")


def _audit_professor_profile(receipt: Path, check: dict[str, Any]) -> None:
    """Run the former full-episode timing and provenance assertions on selected files."""
    import csv
    import wave

    from youtube_automation.timeline.engine import load_timeline_or_shim, verify_shim

    files = check.get("files")
    if not isinstance(files, dict):
        raise ReceiptError("professor_profile requires a files object")
    paths = {key: _selected_path(receipt, files.get(key)) for key in (
        "audio", "script", "pilot_audio", "timeline", "timeline_dir", "intervals",
        "d3_plan", "provenance",
    )}
    expected_hashes = check.get("sha256", {})
    if not isinstance(expected_hashes, dict):
        raise ReceiptError("professor_profile sha256 must be an object")
    for key, expected_hash in expected_hashes.items():
        if key not in paths or not isinstance(expected_hash, str) or not _SHA256.fullmatch(expected_hash):
            raise ReceiptError(f"invalid Professor hash pin: {key}")
        _require(_hash_file(paths[key]) == expected_hash, f"Professor artifact hash mismatch: {key}")
    audio_bytes = paths["audio"].read_bytes()
    _require(len(audio_bytes) == 24_452_138, "Professor source audio byte count mismatch")
    with wave.open(str(paths["audio"]), "rb") as audio:
        _require((audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 24_000), "Professor WAV format mismatch")
        _require(audio.getnframes() == 12_226_047, "Professor WAV frame count mismatch")
        _require(audio.getnframes() / audio.getframerate() == 509.418625, "Professor WAV duration mismatch")
    script_bytes = paths["script"].read_bytes()
    _require(len(script_bytes) == 10_751, "Professor script byte count mismatch")
    script_words = script_bytes.decode("utf-8-sig").split()
    _require(len(script_words) == 1_019, "Professor script word count mismatch")

    pilot = paths["pilot_audio"]
    _require(pilot.stat().st_size == 7_348_878, "Professor pilot-cut byte count mismatch")
    _require(hashlib.sha256(pilot.read_bytes()).hexdigest() != hashlib.sha256(audio_bytes).hexdigest(), "Professor pilot cut unexpectedly equals full episode audio")
    with wave.open(str(pilot), "rb") as audio:
        _require(round(audio.getnframes() / audio.getframerate(), 2) == 76.55, "Professor pilot-cut duration mismatch")

    timeline = _json(paths["timeline"])
    _require(timeline["version"] == "1.0.0" and timeline["fps"] == 30, "Professor timeline version/fps mismatch")
    _require(timeline["total_frames"] == 15_283 and timeline["audio_duration"] == 509.419, "Professor timeline duration mismatch")
    _require(len(timeline["words"]) == 1_019 and len(timeline["spans"]) == 124, "Professor timeline counts mismatch")
    _require(timeline["checksums"]["words_sha256"] == "b5ade2ebe4a4cfed31b6ce6e70f261f2850cff742a3decf3b88c6d6e60fdcbd8", "Professor word checksum mismatch")
    _require(timeline["checksums"]["spans_sha256"] == "99b3ee4d117132fca4784e42c98b28775b8928b3e1fe857f7f2d9ccb37839c95", "Professor span checksum mismatch")
    spans = timeline["spans"]
    _require(spans[0]["start_frame"] == 0 and spans[-1]["end_frame"] == 15_283, "Professor span endpoints mismatch")
    _require(all(span["frame_count"] == span["end_frame"] - span["start_frame"] for span in spans), "Professor span frame count mismatch")
    _require(all(a["end_frame"] == b["start_frame"] for a, b in zip(spans[:-1], spans[1:], strict=True)), "Professor timeline spans are not contiguous")
    for name in ("image_timestamps.txt", "timestamped_transcript.txt", "timestamped_transcript.srt", "subtitle_chunks.srt"):
        shim = paths["timeline_dir"] / name
        _require(shim.is_file() and verify_shim(str(shim), str(paths["timeline"])), f"Professor shim failed: {name}")
    blocks = load_timeline_or_shim(str(paths["timeline_dir"]))
    _require(len(blocks) == 124 and blocks[0]["sec"] == 0.0, "Professor production timeline loader result mismatch")
    _require(abs(blocks[-1]["sec"] - 507.586) <= 0.001, "Professor final timeline block mismatch")

    with paths["intervals"].open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    _require(len(rows) == 174, "Professor interval count mismatch")
    _require({row["interval_type"] for row in rows} == {"SPEECH", "SILENCE_PAUSE", "TAIL_SILENCE"}, "Professor interval classes mismatch")
    _require(float(rows[0]["start"]) == 0.0 and float(rows[-1]["end"]) == 509.418625, "Professor interval endpoints mismatch")
    total_frames = 0
    for index, row in enumerate(rows):
        start = int(row["start_frame_30fps"])
        end = int(row["end_frame_30fps"])
        frames = int(row["frame_count_30fps"])
        _require(frames == end - start, f"Professor interval frame count mismatch at {index}")
        _require(index == 0 or math.isclose(float(row["start"]), float(rows[index - 1]["end"]), abs_tol=1e-5), f"Professor interval time gap at {index}")
        _require(index == 0 or start == int(rows[index - 1]["end_frame_30fps"]), f"Professor interval frame gap at {index}")
        total_frames += frames
    _require(total_frames == 15_283 and int(rows[-1]["end_frame_30fps"]) == 15_283, "Professor interval coverage mismatch")

    plan = _json(paths["d3_plan"])
    shots = plan["shots"]
    _require(len(shots) == 70 and sum(shot["frames_30fps"] for shot in shots) == 15_283, "Professor visual plan frame coverage mismatch")
    _require(shots[0]["start_s"] == 0.0 and shots[-1]["end_s"] == 509.418625, "Professor visual plan endpoints mismatch")
    for shot_id in (11, 12):
        shot = next(shot for shot in shots if shot["shot_id"] == shot_id)
        _require(shot["schulte_40s_static_label_enforced"] is True and shot["played_countdown_hold"] is False, f"Professor Schulte shot {shot_id} mismatch")

    provenance = _json(paths["provenance"])
    summary = provenance["summary"]
    for key, value in {
        "total_words": 1_019,
        "aligner_estimates_count": 1_019,
        "actual_asr_anchors_count": 0,
        "audio_fidelity": "OPEN",
        "listening_performed": False,
    }.items():
        _require(summary.get(key) == value, f"Professor word provenance {key} mismatch")
    _require(len(provenance["words"]) == 1_019, "Professor word provenance count mismatch")


def _audit_snoozer_profile(receipt: Path, check: dict[str, Any]) -> None:
    """Run former Snoozer asset, review-receipt and Flow-canary assertions."""
    from youtube_automation.production.assets import file_digest
    from youtube_automation.production.contracts import fingerprint
    from youtube_automation.production.review import PreviewScorecard
    from youtube_automation.production.shots import ShotPlan
    from youtube_automation.production.visual_gate import VisualAudit
    from youtube_automation.visuals.flow_generator import (
        _select_canary_storyboard,
        parse_json_prompts,
    )

    run_dir = _selected_path(receipt, check.get("run_dir"))
    expected_assets = check.get("assets")
    if not isinstance(expected_assets, dict) or not expected_assets:
        raise ReceiptError("snoozer_profile requires caller-selected asset pins")
    for name, sha256 in expected_assets.items():
        asset = run_dir / "accepted_assets" / f"{sha256}.png"
        _require(asset.is_file() and file_digest(asset) == sha256, f"Snoozer accepted asset mismatch: {name}")
    voice = run_dir / "full_episode_voice.wav"
    _require(voice.is_file() and bool(file_digest(voice)), "Snoozer episode voice artifact missing")

    plan_path = run_dir / "shot_plan.json"
    raw_plan = _json(plan_path)
    plan = ShotPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    expected = check.get("expected")
    if not isinstance(expected, dict):
        raise ReceiptError("snoozer_profile requires an expected object")
    _require(plan.total_frames == expected["total_frames"] and len(plan.shots) == expected["shots"], "Snoozer shot plan counts mismatch")
    _require(fingerprint(raw_plan) == expected["plan_sha256"], "Snoozer shot plan hash mismatch")
    scorecard_path = run_dir / "preview_scorecard.json"
    scorecard = PreviewScorecard.model_validate_json(scorecard_path.read_text(encoding="utf-8"))
    _require(scorecard.plan_sha256 == fingerprint(raw_plan), "Snoozer preview scorecard plan lineage mismatch")
    _require(scorecard.preview_sha256 == expected["preview_sha256"] and scorecard.reviewer == expected["reviewer"], "Snoozer preview scorecard identity mismatch")
    scorecard.require_publishable_scores()
    audit = VisualAudit.model_validate_json((run_dir / "visual_audit.json").read_text(encoding="utf-8"))
    _require(audit.version == expected["audit_version"] and audit.plan_sha256 == fingerprint(raw_plan), "Snoozer visual audit plan lineage mismatch")
    _require(audit.render_inputs_sha256 == expected["render_inputs_sha256"] and len(audit.decisions) == expected["shots"], "Snoozer visual audit identity mismatch")
    for decision in audit.decisions:
        _require(min(decision.semantic_match, decision.continuity, decision.readability, decision.attractiveness) >= 4, "Snoozer visual score below threshold")
        proof = run_dir / decision.proof_path
        _require(proof.is_file() and file_digest(proof) == decision.proof_sha256, "Snoozer visual proof mismatch")
    for filename in ("editorial_approval.json", "active_master.json"):
        _json(run_dir / filename)
    for filename in check.get("required_files", []):
        _require((run_dir / filename).is_file(), f"Snoozer required acceptance artifact missing: {filename}")
    prompts = parse_json_prompts(str(run_dir / "flow_prompts.json"))
    selected_ids = check.get("canary_ids", ["s01_arrival", "s03_cold_hits"])
    selected = _select_canary_storyboard(prompts, selected_ids)
    _require([frame.raw_payload["adaptive_shot"]["shot_id"] for frame in selected] == selected_ids, "Snoozer canary selection mismatch")
    for invalid in (["s03_cold_hits"], ["__unknown_acceptance_shot__"], selected_ids + ["s06_phone_map", "s08_minami_reveal"]):
        try:
            _select_canary_storyboard(prompts, invalid)
        except ValueError:
            pass
        else:
            raise ReceiptError("Snoozer canary accepted an invalid dependency, ID or size")


def _run_semantic_checks(receipt: Path, payload: dict[str, Any]) -> None:
    checks = payload.get("semantic_checks", [])
    if not isinstance(checks, list):
        raise ReceiptError("semantic_checks must be a list")
    runners = {
        "pilot_profile": _audit_pilot_profile,
        "professor_profile": _audit_professor_profile,
        "snoozer_profile": _audit_snoozer_profile,
    }
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise ReceiptError(f"semantic check {index} must be an object")
        kind = check.get("type")
        runner = runners.get(kind)
        if runner is None:
            raise ReceiptError(f"unknown semantic check type: {kind}")
        try:
            runner(receipt, check)
        except ReceiptError:
            raise
        except Exception as exc:
            raise ReceiptError(f"semantic check {kind} failed: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path, help="exact caller-selected JSON receipt")
    args = parser.parse_args(argv)
    try:
        verified = audit_receipt(args.receipt)
    except ReceiptError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "verified", "artifacts": verified}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
