"""Offline voice-direction candidates; transport injection does not grant provider usage."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from youtube_automation.core.utils import atomic_write_json

from .contracts import fingerprint, load_brief, narration_fingerprint
from .ledger import publication_guard
from .voice_direction import (
    DIRECTION_FILE,
    FLASH_MODEL,
    MAX_STYLE_CHARS,
    VoiceDirectionError,
    adaptive_tts_model,
    build_direction,
    load_tag_library,
    strip_tags,
    validate_direction_payload,
)
from .writing import verify_written_episode

CANDIDATE_FILE = "voice_direction.candidate.json"
PUBLICATION_FILE = ".voice_direction_publication.json"
_RESPONSE_KEYS = {"channel_id", "voice", "model", "source_sha256", "script_sha256", "style", "paragraphs"}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()



def _contained_transport_receipt_path(root: Path, receipt_path: str | Path) -> Path:
    root = root.resolve()
    path = Path(receipt_path)
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_relative_to(root):
        raise VoiceDirectionError("Direction transport receipt escapes the run directory")
    return path


def _transport_receipt_binding(
    root: Path,
    receipt_path: str | Path,
    *,
    prompt_sha256: str,
    generation_model: str,
    response: str,
) -> tuple[str, str]:
    root = root.resolve()
    path = _contained_transport_receipt_path(root, receipt_path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise VoiceDirectionError("Direction transport receipt is unreadable") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VoiceDirectionError("Direction transport receipt is malformed") from exc
    attempts = payload.get("attempts") if isinstance(payload, dict) else None
    last = attempts[-1] if isinstance(attempts, list) and attempts else None
    if (
        not isinstance(payload, dict)
        or payload.get("version") != 1
        or payload.get("prompt_sha256") != prompt_sha256
        or payload.get("model") != generation_model
        or payload.get("transport") != "inline"
        or payload.get("window") is not None
        or not isinstance(last, dict)
        or last.get("state") != "completed"
        or last.get("response") != response
    ):
        raise VoiceDirectionError("Direction response lacks its matching completed transport receipt")
    return path.relative_to(root).as_posix(), _sha256(raw)


def _evidence_text(path: Path, text: str) -> None:
    raw = text.encode("utf-8")
    if len(raw) > 4 * 1024 * 1024:
        raise VoiceDirectionError("Direction evidence exceeds the four-MiB bound")
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _context(root: Path) -> tuple[str, dict[str, Any]]:
    brief = load_brief(root)
    verify_written_episode(root)
    if (root / "source_audio_receipt.json").exists():
        raise VoiceDirectionError("Imported source narration cannot enter voice direction")
    if not brief.channel.voice:
        raise VoiceDirectionError("Voice direction requires a selected channel voice")
    if adaptive_tts_model() != FLASH_MODEL:
        raise VoiceDirectionError(f"Voice direction must target {FLASH_MODEL}")
    raw = (root / "refined_script.txt").read_bytes()
    script = raw.decode("utf-8-sig")
    if not script.strip() or "<" in script or ">" in script:
        raise VoiceDirectionError("Voice direction needs nonempty narration without angle brackets")
    identity = {
        "version": 1,
        "source_sha256": brief.source_sha256,
        "source_bytes_sha256": _sha256((root / "raw_transcript.txt").read_bytes()),
        "script_bytes_sha256": _sha256(raw),
        "script_sha256": fingerprint(script.replace("\r\n", "\n").replace("\r", "\n").strip()),
        "brief_sha256": narration_fingerprint(brief),
        "channel_id": brief.channel.channel_id,
        "channel_sha256": fingerprint(brief.channel),
        "voice": brief.channel.voice,
        "model": FLASH_MODEL,
        "tags_sha256": _sha256(Path(__file__).with_name("voice_tags.json").read_bytes()),
    }
    return script, identity


def direction_inputs(run_dir: str | Path) -> dict[str, Any]:
    """Current verified narration, channel, voice, model and vocabulary identity."""
    return _context(Path(run_dir).resolve())[1]



def assert_direction_generation_allowed(run_dir: str | Path) -> dict[str, Any]:
    """Fail closed before browser setup when this run is imported or has audio decisions."""
    root = Path(run_dir).resolve()
    identity = _context(root)[1]
    if (root / DIRECTION_FILE).exists():
        raise VoiceDirectionError("An accepted voice direction blocks new generation")
    if any(
        (root / name).exists()
        for name in (
            "voice_generation_manifest.json",
            "audio_manifest.json",
            "full_episode_voice.wav",
        )
    ) or any(
        (root / folder).is_dir() and any((root / folder).iterdir())
        for folder in ("voice_chapters", "polished_chapters", "audacity_voice")
    ):
        raise VoiceDirectionError("Existing voice takes or audio checkpoints block direction generation")
    return identity


def direction_prompt(run_dir: str | Path, *, generation_model: str | None = None) -> str:
    root = Path(run_dir).resolve()
    script, identity = _context(root)
    brief = load_brief(root)
    data = {
        "task": "Supply voice direction only. Return one JSON object, no prose or fences. "
        "Preserve every word, punctuation mark and paragraph. Insert only listed tags. "
        "Do not approve the result or rewrite the narration. Use restrained narrator direction.",
        "identity": identity,
        "channel": brief.channel.model_dump(mode="json"),
        "narration": script,
        "tags": {k: v for k, v in load_tag_library().items() if v["level"] != "avoid"},
        "style_max_chars": MAX_STYLE_CHARS,
        "response_keys": sorted(_RESPONSE_KEYS),
        "tag_limits": "At most four tags per paragraph, one per eight words, two consecutive tags.",
    }
    if generation_model is not None:
        if (
            not isinstance(generation_model, str)
            or not generation_model.strip()
            or len(generation_model) > 100
            or any(ord(char) < 32 for char in generation_model)
        ):
            raise VoiceDirectionError("Voice-direction generation model must be a bounded label")
        data["generation_model"] = generation_model
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VoiceDirectionError(f"Duplicate response key: {key}")
        result[key] = value
    return result


def _candidate(response: str, script: str, identity: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(response, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise VoiceDirectionError("Direction response is malformed JSON or a provider refusal") from exc
    if not isinstance(data, dict) or set(data) != _RESPONSE_KEYS:
        raise VoiceDirectionError("Direction response has missing or unsupported fields")
    for key in ("channel_id", "voice", "model", "source_sha256", "script_sha256"):
        if data[key] != identity[key]:
            raise VoiceDirectionError(f"Direction response identity mismatch: {key}")
    payload = build_direction(
        script, channel_id=identity["channel_id"], style=data["style"], paragraphs=data["paragraphs"]
    )
    validate_direction_payload(payload, script, channel_id=identity["channel_id"], require_approval=False)
    clean = re.split(r"\n[ \t]*\n", script.replace("\r\n", "\n").replace("\r", "\n").strip())
    clean = [p.strip() for p in clean if p.strip()]
    if any(strip_tags(a) != strip_tags(b) for a, b in zip(data["paragraphs"], clean, strict=True)):
        raise VoiceDirectionError("Direction response must preserve narration and paragraph line breaks")
    payload["provenance"] = provenance
    return payload


def _validate_candidate(root: Path, payload: Any) -> dict[str, Any]:
    script, identity = _context(root)
    if not isinstance(payload, dict) or "approval" in payload:
        raise VoiceDirectionError("Direction candidate must be unapproved")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("identity") != identity:
        raise VoiceDirectionError("Direction candidate uses stale source, channel, voice, model or tags")
    attempt = provenance.get("attempt")
    if not isinstance(attempt, str) or not re.fullmatch(r"[0-9a-f]{32}", attempt):
        raise VoiceDirectionError("Direction candidate has an invalid attempt identity")
    generation_model = provenance.get("generation_model")
    if generation_model is not None and (
        not isinstance(generation_model, str) or not generation_model.strip() or len(generation_model) > 100
    ):
        raise VoiceDirectionError("Direction candidate has an invalid generation model")
    folder = (root / "direction_attempts" / attempt).resolve()
    if not folder.is_relative_to(root):
        raise VoiceDirectionError("Direction evidence escapes the run")
    prompt = (folder / "request.txt").read_bytes()
    response = (folder / "response.txt").read_bytes()
    expected = {
        "identity": identity,
        "attempt": attempt,
        "request_sha256": _sha256(prompt),
        "response_sha256": _sha256(response),
    }
    if generation_model is not None:
        receipt_path = provenance.get("transport_receipt_path")
        receipt_sha256 = provenance.get("transport_receipt_sha256")
        if (
            not isinstance(receipt_path, str)
            or not isinstance(receipt_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", receipt_sha256)
        ):
            raise VoiceDirectionError("Automated direction candidate is missing its transport receipt binding")
        request_sha256 = expected["request_sha256"]
        if not isinstance(request_sha256, str):
            raise VoiceDirectionError("Direction transport prompt digest is invalid")
        bound_path, bound_sha256 = _transport_receipt_binding(
            root,
            receipt_path,
            prompt_sha256=request_sha256,
            generation_model=generation_model,
            response=response.decode("utf-8"),
        )
        if (bound_path, bound_sha256) != (receipt_path, receipt_sha256):
            raise VoiceDirectionError("Direction transport receipt changed after candidate publication")
        expected.update(
            generation_model=generation_model,
            transport_receipt_path=receipt_path,
            transport_receipt_sha256=receipt_sha256,
        )
    elif "transport_receipt_path" in provenance or "transport_receipt_sha256" in provenance:
        raise VoiceDirectionError("Offline direction candidate cannot claim an automated transport receipt")
    if provenance != expected or prompt.decode("utf-8") != direction_prompt(
        root, generation_model=generation_model
    ):
        raise VoiceDirectionError("Direction response provenance does not match its exact request")
    if payload != _candidate(response.decode("utf-8"), script, identity, expected):
        raise VoiceDirectionError("Direction candidate differs from its validated response")
    return payload


def verify_direction_candidate(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    payload = json.loads((root / CANDIDATE_FILE).read_text(encoding="utf-8"))
    return _validate_candidate(root, payload)

def validate_accepted_direction(run_dir: str | Path, payload: Any) -> None:
    """Revalidate generated direction against current inputs and approved candidate bytes."""
    root = Path(run_dir).resolve()
    approval = payload.get("approval") if isinstance(payload, dict) else None
    candidate_path = root / CANDIDATE_FILE
    attempts_path = root / "direction_attempts"
    has_attempt_evidence = attempts_path.is_dir() and any(attempts_path.iterdir())
    generated = (
        isinstance(payload, dict)
        and (
            "provenance" in payload
            or (isinstance(approval, dict) and "candidate_sha256" in approval)
            or candidate_path.exists()
            or has_attempt_evidence
        )
    )
    if not generated:
        return

    if not isinstance(payload.get("provenance"), dict):
        raise VoiceDirectionError("Generated direction is missing candidate provenance")
    if not candidate_path.is_file():
        raise VoiceDirectionError("Generated direction candidate is missing")
    candidate_bytes = candidate_path.read_bytes()
    candidate_sha256 = _sha256(candidate_bytes)
    if not isinstance(approval, dict) or approval.get("candidate_sha256") != candidate_sha256:
        raise VoiceDirectionError("Accepted direction candidate hash does not match approval")

    candidate = verify_direction_candidate(root)
    accepted_content = {key: value for key, value in payload.items() if key != "approval"}
    if accepted_content != candidate:
        raise VoiceDirectionError("Accepted direction content differs from approved candidate")


def _publish_candidate(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    with publication_guard():
        _validate_candidate(root, payload)
        atomic_write_json(str(root / PUBLICATION_FILE), payload)
        atomic_write_json(str(root / CANDIDATE_FILE), payload)
        (root / PUBLICATION_FILE).unlink()
    return payload


def recover_direction_candidate(
    run_dir: str | Path, *, generation_model: str | None = None
) -> dict[str, Any] | None:
    """Validate a pending publication before promotion, including automated-model binding."""
    root = Path(run_dir).resolve()
    pending = root / PUBLICATION_FILE
    if not pending.is_file():
        return None
    payload = json.loads(pending.read_text(encoding="utf-8"))
    candidate = _validate_candidate(root, payload)
    if (
        generation_model is not None
        and candidate["provenance"].get("generation_model") != generation_model
    ):
        raise VoiceDirectionError(
            "Pending direction publication lacks matching automated generation provenance; preserve it"
        )
    return _publish_candidate(root, candidate)


def ensure_direction_candidate(
    run_dir: str | Path,
    ask: Callable[[str], str],
    *,
    generation_model: str | None = None,
    transport_receipt_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create one unapproved candidate; automated generation must bind a durable transport receipt."""
    root = Path(run_dir).resolve()
    generation_binding: tuple[str, Path] | None = None
    if generation_model is not None:
        assert_direction_generation_allowed(root)
        if not isinstance(transport_receipt_path, (str, Path)):
            raise VoiceDirectionError("Automated direction generation requires its transport receipt path")
        generation_binding = (
            generation_model,
            _contained_transport_receipt_path(root, transport_receipt_path),
        )
    script, identity = _context(root)
    pending = recover_direction_candidate(root, generation_model=generation_model)
    if pending is not None:
        return pending
    if (root / CANDIDATE_FILE).is_file():
        candidate = verify_direction_candidate(root)
        if (
            generation_model is not None
            and candidate["provenance"].get("generation_model") != generation_model
        ):
            raise VoiceDirectionError(
                "A current candidate exists without matching automated generation provenance; preserve it"
            )
        return candidate
    attempt = uuid.uuid4().hex
    folder = root / "direction_attempts" / attempt
    folder.mkdir(parents=True, exist_ok=False)
    prompt = direction_prompt(root, generation_model=generation_model)
    _evidence_text(folder / "request.txt", prompt)
    atomic_write_json(str(folder / "receipt.json"), {"state": "preparing", "identity": identity})
    try:
        response = ask(prompt)
        if not isinstance(response, str):
            raise VoiceDirectionError("Direction transport returned non-text output")
        _evidence_text(folder / "response.txt", response)
        provenance: dict[str, Any] = {
            "identity": identity,
            "attempt": attempt,
            "request_sha256": _sha256(prompt.encode("utf-8")),
            "response_sha256": _sha256(response.encode("utf-8")),
        }
        if generation_binding is not None:
            binding_model, binding_receipt_path = generation_binding
            request_sha256 = provenance["request_sha256"]
            if not isinstance(request_sha256, str):
                raise VoiceDirectionError("Direction transport prompt digest is invalid")
            receipt_path, receipt_sha256 = _transport_receipt_binding(
                root,
                binding_receipt_path,
                prompt_sha256=request_sha256,
                generation_model=binding_model,
                response=response,
            )
            provenance.update(
                generation_model=binding_model,
                transport_receipt_path=receipt_path,
                transport_receipt_sha256=receipt_sha256,
            )
        payload = _candidate(response, script, identity, provenance)
        result = _publish_candidate(root, payload)
    except BaseException as exc:
        atomic_write_json(
            str(folder / "receipt.json"),
            {
                "state": "rejected",
                "identity": identity,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        raise
    atomic_write_json(str(folder / "receipt.json"), {"state": "completed", "provenance": provenance})
    return result


def candidate_matches_response(run_dir: str | Path, response_file: str | Path) -> bool:
    payload = verify_direction_candidate(run_dir)
    response = Path(response_file).read_text(encoding="utf-8-sig")
    return bool(payload["provenance"]["response_sha256"] == _sha256(response.encode("utf-8")))


def accept_direction(run_dir: str | Path, *, reviewer: str, candidate_sha256: str) -> Path:
    """Approve exactly the current candidate without replacing accepted directions or takes."""
    root = Path(run_dir).resolve()
    if not reviewer.strip() or not re.fullmatch(r"[0-9a-f]{64}", candidate_sha256):
        raise VoiceDirectionError("Direction acceptance requires a reviewer and exact candidate SHA-256")
    with publication_guard():
        candidate = verify_direction_candidate(root)
        if _sha256((root / CANDIDATE_FILE).read_bytes()) != candidate_sha256:
            raise VoiceDirectionError("Direction acceptance candidate hash mismatch")
        accepted = dict(candidate)
        accepted["approval"] = {"approved_by": reviewer.strip(), "statement": "APPROVED",
                                "candidate_sha256": candidate_sha256}
        target = root / DIRECTION_FILE
        if target.exists():
            if json.loads(target.read_text(encoding="utf-8-sig")) != accepted:
                raise VoiceDirectionError("An accepted voice direction already exists; preserve it")
            return target
        if any((root / name).exists() for name in (
            "voice_generation_manifest.json", "audio_manifest.json", "full_episode_voice.wav",
        )) or any((root / folder).is_dir() and any((root / folder).iterdir()) for folder in (
            "voice_chapters", "polished_chapters", "audacity_voice",
        )):
            raise VoiceDirectionError("Existing voice takes or audio checkpoints block direction acceptance")
        script, identity = _context(root)
        validate_direction_payload(accepted, script, channel_id=identity["channel_id"])
        atomic_write_json(str(target), accepted)
    return target


def direction_acceptance_complete(run_dir: str | Path, *, reviewer: str, candidate_sha256: str) -> bool:
    root = Path(run_dir).resolve()
    candidate = verify_direction_candidate(root)
    if _sha256((root / CANDIDATE_FILE).read_bytes()) != candidate_sha256:
        return False
    candidate["approval"] = {"approved_by": reviewer.strip(), "statement": "APPROVED",
                             "candidate_sha256": candidate_sha256}
    return bool(json.loads((root / DIRECTION_FILE).read_text(encoding="utf-8-sig")) == candidate)
