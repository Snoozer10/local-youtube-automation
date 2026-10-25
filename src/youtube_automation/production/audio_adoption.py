"""Exact-byte, journaled adoption of explicitly accepted polished narration."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from youtube_automation.audio.wav_validation import parse_wav_file
from youtube_automation.core.utils import atomic_write_json

from .contracts import fingerprint, narration_fingerprint
from .ledger import lease_database, leased_resource, publication_guard

PENDING = ".audio_adoption_publication.json"
RECEIPT = "audio_adoption_receipt.json"
STAGE = "adopt-polished-audio"
_JSON_LIMIT = 2_000_000
_AUDIO_LIMIT = 128_000_000
_SHIMS = ("image_timestamps.txt", "timestamped_transcript.txt", "timestamped_transcript.srt", "subtitle_chunks.srt")
_SHIM_SIDECARS = tuple(name + ".sha256" for name in _SHIMS)


def _bytes(path: Path, limit: int = _JSON_LIMIT) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Audio adoption input exceeds its byte bound: {path.name}")
    return data


def _digest(path: Path, limit: int = _JSON_LIMIT) -> str:
    return hashlib.sha256(_bytes(path, limit)).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(_bytes(path).decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Audio adoption requires a JSON object")
    return value


def _contained(root: Path, name: str) -> Path:
    relative = Path(name)
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root) or ".." in relative.parts:
        raise ValueError("Audio adoption path escapes its run")
    return path


def _stat(path: Path) -> list[int]:
    value = path.stat()
    return [value.st_size, value.st_mtime_ns, value.st_ino]


def _selected_audio(root: Path, name: str) -> Path:
    configured = Path(name)
    path = configured.resolve() if configured.is_absolute() else (root / configured).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Canonical audio escapes its run")
    return path


def _identity(root: Path) -> dict[str, Any]:
    from .contracts import load_brief

    brief = load_brief(root)
    return {"brief": narration_fingerprint(brief), "script": _digest(root / "refined_script.txt"),
            "voice": brief.channel.voice}


def _verify_shims(root: Path) -> None:
    from youtube_automation.timeline.engine import verify_shim

    if not all((root / name).is_file() and verify_shim(str(root / name), str(root / "timeline.json"))
               for name in _SHIMS):
        raise ValueError("Canonical timing shims are missing or do not match the timeline")


def assert_no_pending_audio_adoption(root: str | Path) -> None:
    if (Path(root) / PENDING).exists():
        raise ValueError("Audio adoption is pending; resume the exact adoption request first")


def capture_audio_state(root: str | Path, *, validate_pair: bool = True) -> dict[str, Any]:
    """Capture bounded current identities inside publication_guard, without media hashing."""
    root = Path(root).resolve()
    assert_no_pending_audio_adoption(root)
    names = ("episode_brief.json", "timeline.json", "shot_plan.json", "refined_script.txt", RECEIPT)
    state: dict[str, Any] = {name: _digest(root / name) if (root / name).is_file() else None for name in names}
    timeline = _json(root / "timeline.json") if state["timeline.json"] else None
    if timeline and timeline.get("audio_file"):
        audio = _selected_audio(root, timeline["audio_file"])
        state["audio"] = [str(audio), _stat(audio) if audio.is_file() else None]
    if validate_pair and timeline and state["shot_plan.json"] and state["episode_brief.json"]:
        from .contracts import load_brief
        from .shots import ShotPlan

        plan = ShotPlan.model_validate(_json(root / "shot_plan.json"))
        if plan.timeline_sha256 != fingerprint(timeline) or plan.brief_sha256 != fingerprint(load_brief(root)):
            raise ValueError("Current audio/plan lineage mismatch")
    if state[RECEIPT]:
        receipt = _json(root / RECEIPT)
        if (receipt.get("version") != 1 or receipt.get("kind") != "accepted_polish"
                or receipt.get("narration_identity") != _identity(root)
                or not timeline or timeline.get("audio_file") != receipt.get("audio_path")
                or timeline.get("audio_sha256") != receipt.get("audio_sha256")):
            raise ValueError("Accepted audio selection or narration identity changed")
    return state


def assert_current_audio_state(root: str | Path, expected: dict[str, Any], *, validate_pair: bool = True) -> None:
    if capture_audio_state(root, validate_pair=validate_pair) != expected:
        raise ValueError("Current audio inputs changed before publication")


def assert_audio_lineage(root: str | Path, brief: Any, timeline: dict[str, Any] | None = None,
                         plan: Any = None) -> None:
    """Compare caller snapshots at the shared publication boundary, including legacy APIs."""
    from .contracts import load_brief

    root = Path(root)
    assert_no_pending_audio_adoption(root)
    if (root / "episode_brief.json").is_file() and load_brief(root) != brief:
        raise ValueError("Current audio brief changed before publication")
    if timeline is not None and (root / "timeline.json").is_file():
        if fingerprint(_json(root / "timeline.json")) != fingerprint(timeline):
            raise ValueError("Current audio timeline changed before publication")
    if plan is not None and (root / "shot_plan.json").is_file():
        from .shots import ShotPlan

        if ShotPlan.model_validate(_json(root / "shot_plan.json")) != plan:
            raise ValueError("Current audio plan changed before publication")


def _authority(path: Path, audio: Path, digest: str) -> dict[str, Any]:
    value = _json(path)
    matches = [item for item in value.get("files", []) if isinstance(item, dict)
               and item.get("sha256") == digest and Path(str(item.get("path", ""))).resolve() == audio]
    if (value.get("record_type") != "direct_user_audio_acceptance"
            or not str(value.get("user_response", "")).strip() or len(matches) != 1):
        raise ValueError("Exact audio acceptance entry is missing or ambiguous")
    return matches[0]


def _request(audio_file: str | Path, audio_sha256: str, acceptance_file: str | Path,
             acceptance_sha256: str) -> dict[str, Any]:
    audio, authority = Path(audio_file).resolve(strict=True), Path(acceptance_file).resolve(strict=True)
    if _digest(authority) != acceptance_sha256:
        raise ValueError("Audio acceptance authority changed")
    if _digest(audio, _AUDIO_LIMIT) != audio_sha256:
        raise ValueError("Accepted audio digest changed")
    _authority(authority, audio, audio_sha256)
    return {"audio_file": str(audio), "audio_sha256": audio_sha256,
            "acceptance_file": str(authority), "acceptance_sha256": acceptance_sha256}


def _pcm(path: Path, *, require_compliant: bool = True) -> dict[str, Any]:
    value = parse_wav_file(path)
    if (not value.parseable or (require_compliant and not value.fully_compliant)
            or value.channels != 1 or value.bits_per_sample != 16
            or not value.frame_count or not value.sample_rate):
        raise ValueError("Accepted audio must be complete mono PCM16 WAV")
    return {"channels": value.channels, "sample_rate": value.sample_rate,
            "sample_width_bytes": 2, "frames": value.frame_count,
            "duration_seconds": value.frame_count / value.sample_rate}


def _immutable(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if _bytes(path, _AUDIO_LIMIT) != data:
            raise ValueError("Immutable audio adoption artifact collision")
        return
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _encoded(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=4).encode("utf-8")


def _activation_outputs(timeline: dict[str, Any], plan: dict[str, Any], receipt: dict[str, Any]) -> dict[str, bytes]:
    timeline_bytes = _encoded(timeline)
    sidecar = (hashlib.sha256(timeline_bytes).hexdigest() + "\n").encode("ascii")
    return {"timeline.json": timeline_bytes, "shot_plan.json": _encoded(plan), RECEIPT: _encoded(receipt),
            **dict.fromkeys(_SHIM_SIDECARS, sidecar)}


def _publish_bytes(path: Path, data: bytes) -> None:
    """Activate exact staged bytes; text-mode newline conversion is never permitted."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".audio-adoption.tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if _bytes(temporary) != data:
            raise ValueError("Audio adoption staged activation bytes changed")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _recipe(request: dict[str, Any], inputs: dict[str, str], identity: dict[str, Any]) -> str:
    return fingerprint({"version": 1, "kind": "accepted_polish", "request": request,
                        "source_inputs": inputs, "narration_identity": identity})


def verify_audio_adoption(root: str | Path, *, request: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    with publication_guard():
        state = capture_audio_state(root)
        receipt = _json(root / RECEIPT)
        if request is not None and receipt.get("request") != request:
            raise ValueError("A different polished audio adoption already exists; use a fresh run")
        if receipt.get("recipe") != _recipe(receipt["request"], receipt["source_inputs"], receipt["narration_identity"]):
            raise ValueError("Audio adoption receipt recipe is invalid")
        accepted = _contained(root, receipt["audio_path"])
        authority = _contained(root, receipt["acceptance_path"])
    if _digest(accepted, _AUDIO_LIMIT) != receipt["audio_sha256"] or _pcm(accepted) != receipt["pcm"]:
        raise ValueError("Accepted polished WAV changed")
    if _digest(authority) != receipt["request"]["acceptance_sha256"]:
        raise ValueError("Archived audio acceptance authority changed")
    _authority(authority, Path(receipt["request"]["audio_file"]), receipt["audio_sha256"])
    with publication_guard():
        assert_current_audio_state(root, state)
        _verify_shims(root)
    return receipt


def adoption_recipe(root: str | Path, **kwargs: Any) -> str:
    root = Path(root).resolve()
    request = _request(**kwargs)
    if (root / RECEIPT).exists() and not (root / PENDING).exists():
        return str(verify_audio_adoption(root, request=request)["recipe"])
    if (root / PENDING).exists():
        pending = _json(root / PENDING)
        if pending.get("request") != request:
            raise ValueError("Conflicting pending audio adoption request")
        return str(pending["recipe"])
    with publication_guard():
        capture_audio_state(root)
        inputs = _source_inputs(root)
        identity = _identity(root)
    return _recipe(request, inputs, identity)


def _source_inputs(root: Path) -> dict[str, str]:
    names = ("episode_brief.json", "timeline.json", "shot_plan.json", "refined_script.txt",
             "voice_generation_manifest.json", "audio_manifest.json", "source_audio_receipt.json",
             *_SHIMS, *_SHIM_SIDECARS)
    return {name: _digest(root / name) for name in names if (root / name).is_file()}


def _checkpoint(root: Path, pending: dict[str, Any], phase: str) -> None:
    pending["phase"] = phase
    atomic_write_json(str(root / PENDING), pending)


def _validate_pending(root: Path, pending: dict[str, Any], request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, bytes]]:
    from .contracts import load_brief
    from .shots import ShotPlan, validate_plan

    receipt = pending["receipt"]
    recipe = _recipe(request, pending["source_inputs"], receipt["narration_identity"])
    if (pending.get("version") != 1 or pending.get("kind") != "accepted_polish"
            or pending.get("request") != request or pending.get("recipe") != recipe
            or receipt.get("recipe") != recipe or receipt.get("request") != request
            or pending.get("phase") not in {"PREPARED", "INVALIDATED"}
            or receipt.get("audio_path") != f"accepted_audio/{request['audio_sha256']}.wav"
            or receipt.get("audio_sha256") != request["audio_sha256"]
            or receipt.get("source_inputs") != pending["source_inputs"]
            or receipt.get("acceptance_path") != f".audio_adoption/{recipe}/acceptance.json"
            or receipt.get("narration_identity") != _identity(root)):
        raise ValueError("Invalid or stale audio adoption journal")
    home = _contained(root, f".audio_adoption/{recipe}")
    for name, digest in pending["source_inputs"].items():
        if _digest(_contained(home / "inputs", name)) != digest:
            raise ValueError("Audio adoption snapshot changed")
        if name not in {"timeline.json", "shot_plan.json", *_SHIM_SIDECARS} and _digest(_contained(root, name)) != digest:
            raise ValueError("Audio adoption source inputs changed")
    timeline = _json(home / "inputs/timeline.json")
    timeline.update(audio_file=receipt["audio_path"], audio_sha256=request["audio_sha256"])
    plan_data = _json(home / "inputs/shot_plan.json")
    plan_data["timeline_sha256"] = fingerprint(timeline)
    if (receipt.get("initial_timeline_sha256") != fingerprint(timeline)
            or receipt.get("initial_plan_sha256") != fingerprint(plan_data)):
        raise ValueError("Audio adoption initial output lineage changed")
    validate_plan(ShotPlan.model_validate(plan_data), timeline, load_brief(root))
    outputs = _activation_outputs(timeline, plan_data, receipt)
    if pending.get("outputs") != {name: hashlib.sha256(data).hexdigest() for name, data in outputs.items()}:
        raise ValueError("Audio adoption activation intent changed")
    return receipt, outputs


def _recover(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    from .invalidation import invalidate_stage, reconcile_invalidation, stage_output_paths

    pending = _json(root / PENDING)
    receipt, outputs = _validate_pending(root, pending, request)
    accepted = _contained(root, receipt["audio_path"])
    if _digest(accepted, _AUDIO_LIMIT) != request["audio_sha256"] or _pcm(accepted) != receipt["pcm"]:
        raise ValueError("Staged accepted audio changed")
    authority = _contained(root, receipt["acceptance_path"])
    if _digest(authority) != request["acceptance_sha256"]:
        raise ValueError("Staged acceptance authority changed")
    accepted_stat = _stat(accepted)
    with publication_guard():
        # Re-read after media validation; no large media hash runs while holding SQLite.
        if _json(root / PENDING) != pending or _stat(accepted) != accepted_stat:
            raise ValueError("Audio adoption recovery inputs changed")
        _validate_pending(root, pending, request)
        if pending["phase"] == "PREPARED":
            reconcile_invalidation(root)

            intended = {record["source"] for record in pending["deactivated"]}
            actual = {path.relative_to(root).as_posix() for path in stage_output_paths(root, STAGE)}
            if not actual.issubset(intended):
                raise ValueError("Unknown downstream activation appeared during audio adoption")
            for record in pending["deactivated"]:
                source, archive = _contained(root, record["source"]), _contained(root, record["archive"])
                if source.exists() and archive.exists():
                    raise ValueError("Conflicting active and archived audio adoption inputs")
                current = source if source.exists() else archive
                if _digest(current) != record["sha256"]:
                    raise ValueError("Audio adoption invalidation preimage changed")
            invalidate_stage(root, STAGE, pending["previous_recipe"], pending["recipe"])
            _checkpoint(root, pending, "INVALIDATED")
        for name, data in outputs.items():
            target = root / name
            if target.exists() and _bytes(target) != data:
                raise ValueError("Conflicting audio adoption activation file")
        for name, data in outputs.items():
            target = root / name
            if not target.exists():
                _publish_bytes(target, data)
        _validate_pending(root, pending, request)
        for name, data in outputs.items():
            if _bytes(root / name) != data:
                raise ValueError("Audio adoption activation readback failed")
        _verify_shims(root)
        _immutable(_contained(root, f".audio_adoption/{pending['recipe']}/completed.json"), _encoded(pending))
        (root / PENDING).unlink()
    return verify_audio_adoption(root, request=request)


def adopt_polished_audio(root: str | Path, **kwargs: Any) -> dict[str, Any]:
    """Publish only the exact accepted WAV; no providers, DSP, transcription or encoding."""
    from .contracts import load_brief
    from .invalidation import stage_archive_destination, stage_output_paths
    from .shots import ShotPlan, validate_plan

    root = Path(root).resolve(strict=True)
    request = _request(**kwargs)
    with leased_resource(lease_database(), f"audio-adoption:{fingerprint(str(root))}"):
        if (root / PENDING).exists():
            return _recover(root, request)
        if (root / RECEIPT).exists():
            return verify_audio_adoption(root, request=request)
        with publication_guard():
            state = capture_audio_state(root)
            _verify_shims(root)
            source_inputs = _source_inputs(root)
            identity = _identity(root)
            brief = load_brief(root)
            timeline = _json(root / "timeline.json")
            plan_data = _json(root / "shot_plan.json")
            plan = ShotPlan.model_validate(plan_data)
            validate_plan(plan, timeline, brief)
            original_audio = _selected_audio(root, timeline["audio_file"])
            original_stat = _stat(original_audio)
        pcm = _pcm(Path(request["audio_file"]))
        original_pcm = _pcm(original_audio, require_compliant=False)
        duration = float(timeline["audio_duration"])
        if (pcm != original_pcm or not math.isfinite(duration) or duration <= 0
                or abs(duration - pcm["duration_seconds"]) > 1 / pcm["sample_rate"]
                or abs(plan.total_frames / plan.fps - duration) > 1 / plan.fps):
            raise ValueError("Accepted polish must preserve original PCM frames and canonical duration")
        recipe = _recipe(request, source_inputs, identity)
        home = _contained(root, f".audio_adoption/{recipe}")
        original_bytes = _bytes(original_audio, _AUDIO_LIMIT)
        _immutable(home / "original_audio.wav", original_bytes)
        for name, digest in source_inputs.items():
            data = _bytes(root / name)
            _immutable(_contained(home / "inputs", name), data)
            if hashlib.sha256(data).hexdigest() != digest or _digest(root / name) != digest:
                raise ValueError("Audio adoption source changed while snapshotting")
        audio_data = _bytes(Path(request["audio_file"]), _AUDIO_LIMIT)
        if hashlib.sha256(audio_data).hexdigest() != request["audio_sha256"]:
            raise ValueError("Accepted audio changed while copying")
        audio_path = f"accepted_audio/{request['audio_sha256']}.wav"
        _immutable(_contained(root, audio_path), audio_data)
        if _digest(Path(request["audio_file"]), _AUDIO_LIMIT) != request["audio_sha256"]:
            raise ValueError("Accepted source WAV changed after copying")
        acceptance_path = f".audio_adoption/{recipe}/acceptance.json"
        _immutable(_contained(root, acceptance_path), _bytes(Path(request["acceptance_file"])))
        if (_digest(_contained(root, acceptance_path)) != request["acceptance_sha256"]
                or _digest(Path(request["acceptance_file"])) != request["acceptance_sha256"]):
            raise ValueError("Audio acceptance authority changed while copying")
        receipt = {"version": 1, "kind": "accepted_polish", "recipe": recipe, "request": request,
                   "audio_path": audio_path, "audio_sha256": request["audio_sha256"], "pcm": pcm,
                   "acceptance_path": acceptance_path, "source_inputs": source_inputs,
                   "narration_identity": identity, "original_audio_path": timeline["audio_file"],
                   "original_audio_sha256": _digest(original_audio, _AUDIO_LIMIT),
                   "original_timeline_sha256": fingerprint(timeline), "original_plan_sha256": fingerprint(plan)}
        timeline = dict(timeline, audio_file=audio_path, audio_sha256=request["audio_sha256"])
        plan_data = dict(plan_data)
        plan_data["timeline_sha256"] = fingerprint(timeline)
        receipt.update(initial_timeline_sha256=fingerprint(timeline), initial_plan_sha256=fingerprint(plan_data))
        outputs = _activation_outputs(timeline, plan_data, receipt)
        previous = "original-" + fingerprint(source_inputs)
        with publication_guard():
            assert_current_audio_state(root, state)
            if _stat(original_audio) != original_stat or _identity(root) != identity:
                raise ValueError("Original narration changed before adoption")
            deactivated = []
            for path in stage_output_paths(root, STAGE):
                name = path.relative_to(root).as_posix()
                archive = stage_archive_destination(root, STAGE, previous, recipe, name)
                deactivated.append({"source": name, "archive": archive.as_posix(), "sha256": _digest(path)})
            pending = {"version": 1, "kind": "accepted_polish", "recipe": recipe, "request": request,
                       "source_inputs": source_inputs, "receipt": receipt, "previous_recipe": previous,
                       "outputs": {name: hashlib.sha256(data).hexdigest() for name, data in outputs.items()},
                       "deactivated": deactivated}
            _checkpoint(root, pending, "PREPARED")
        return _recover(root, request)


def require_adopted_audio_review(root: str | Path, brief: Any, plan: Any = None) -> None:
    """Accepted audio requires current editorial policy before visual work can advance."""
    root = Path(root)
    with publication_guard():
        adopted = (root / RECEIPT).is_file()
        if adopted:
            assert_audio_lineage(root, brief, plan=plan)
            if brief.version < 3:
                raise ValueError(
                    "Accepted audio visuals require editorial-policy v3 migration and a fresh critic"
                )
    if adopted and plan is not None:
        from .shots import require_editorial_review

        require_editorial_review(root, plan, brief)
