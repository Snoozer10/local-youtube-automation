"""Import a bounded excerpt of an existing narration without rewriting its words."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

from youtube_automation.core.utils import atomic_write_json

from .contracts import fingerprint, load_brief, narration_fingerprint
from .ledger import publication_guard
from .writing import atomic_text, verify_written_episode

_DOWNSTREAM_ARTIFACTS = (
    "adaptive_writing_receipt.json",
    "refined_script.txt",
    "final_output.txt",
    "timeline.json",
    "shot_plan.json",
    "full_episode_voice.wav",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_recipe(
    brief_sha256: str,
    raw: str,
    media_sha256: str,
    start_seconds: float,
    end_seconds: float,
) -> str:
    return fingerprint(
        {
            "version": 1,
            "brief": brief_sha256,
            "raw": fingerprint(raw),
            "media": media_sha256,
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
        }
    )


def _journal_path(root: Path, recipe: str) -> Path:
    return root / ".publication_journal" / "source_audio" / f"{recipe}.json"


def _remove_journal(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _recover_pending_source(root: Path, recipe: str) -> dict[str, Any] | None:
    journal = _journal_path(root, recipe)
    try:
        pending = json.loads(journal.read_text(encoding="utf-8"))
        source_receipt = pending["source_receipt"]
        writing_receipt = pending["writing_receipt"]
        outputs = pending["outputs"]
        accepted = (root / pending["accepted_path"]).resolve()
        if (
            pending.get("version") != 1
            or pending.get("kind") != "source_audio"
            or pending.get("recipe") != recipe
            or not accepted.is_relative_to((root / "source_audio").resolve())
            or not accepted.is_file()
            or _sha256(accepted) != source_receipt.get("audio_sha256")
            or source_receipt.get("recipe") != recipe
            or source_receipt.get("brief_sha256") != narration_fingerprint(load_brief(root))
            or writing_receipt.get("brief_sha256") != source_receipt.get("brief_sha256")
            or writing_receipt.get("outputs")
            != {name: fingerprint(value) for name, value in outputs.items()}
        ):
            return None
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    receipt_path = root / "source_audio_receipt.json"
    if receipt_path.exists():
        existing = verify_source_narration(root)
        if existing != source_receipt:
            raise ValueError("A different source narration appeared during import")
        _remove_journal(journal)
        return existing
    with publication_guard():
        if source_receipt.get("brief_sha256") != narration_fingerprint(load_brief(root)):
            raise ValueError("Source narration inputs changed before publication recovery")
        audio = root / "full_episode_voice.wav"
        if audio.exists() and _sha256(audio) != source_receipt["audio_sha256"]:
            raise ValueError("Source narration appeared during import; refusing to replace it")
        if not audio.exists():
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(dir=root, suffix=".wav", delete=False) as handle:
                    temporary = Path(handle.name)
                    with accepted.open("rb") as source:
                        shutil.copyfileobj(source, handle)
                    handle.flush()
                    os.fsync(handle.fileno())
                if _sha256(temporary) != source_receipt["audio_sha256"]:
                    raise ValueError("Accepted source narration changed during activation")
                os.replace(temporary, audio)
                temporary = None
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        for name, value in outputs.items():
            target = root / name
            if target.exists() and target.read_text(encoding="utf-8") != value:
                raise ValueError("Source narration text appeared during import; refusing to replace it")
            atomic_text(target, value)
        writing_path = root / "adaptive_writing_receipt.json"
        if writing_path.exists() and json.loads(writing_path.read_text(encoding="utf-8")) != writing_receipt:
            raise ValueError("Source narration writing receipt appeared during import")
        atomic_write_json(str(writing_path), writing_receipt)
        atomic_write_json(str(receipt_path), source_receipt)
    _remove_journal(journal)
    verify_written_episode(root)
    return verify_source_narration(root)


def verify_source_narration(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir)
    receipt: dict[str, Any] = json.loads(
        (root / "source_audio_receipt.json").read_text(encoding="utf-8")
    )
    audio = root / "full_episode_voice.wav"
    if (
        receipt.get("version") != 1
        or receipt.get("brief_sha256") != narration_fingerprint(load_brief(root))
        or not audio.is_file()
        or _sha256(audio) != receipt.get("audio_sha256")
    ):
        raise ValueError("Source narration receipt or WAV no longer matches the selected run")
    return receipt


def import_source_narration(
    run_dir: str | Path, media_file: str | Path, *, start_seconds: float, end_seconds: float
) -> dict[str, Any]:
    """Accept local owner media; receipt is published only after WAV and text verify."""
    root = Path(run_dir).resolve()
    media = Path(media_file).resolve()
    if not root.is_dir() or not media.is_file() or not (0 <= start_seconds < end_seconds):
        raise ValueError("Run, local media and positive excerpt boundaries are required")
    brief = load_brief(root)
    raw = (root / "raw_transcript.txt").read_text(encoding="utf-8-sig")
    if not raw.strip():
        raise ValueError("Source transcript is empty")
    provenance_path = root / "pilot_source.json"
    if provenance_path.exists():
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if (
            provenance.get("channel_id") != brief.channel.channel_id
            or provenance.get("raw_transcript_sha256") != hashlib.sha256(raw.encode()).hexdigest()
            or abs(float(provenance["start_seconds"]) - start_seconds) > 0.001
            or abs(float(provenance["end_seconds"]) - end_seconds) > 0.001
        ):
            raise ValueError("Audio excerpt does not match the selected caption provenance")
    media_sha256 = _sha256(media)
    brief_sha256 = narration_fingerprint(brief)
    source_recipe = _source_recipe(
        brief_sha256, raw, media_sha256, start_seconds, end_seconds
    )
    recovered = _recover_pending_source(root, source_recipe)
    if recovered is not None:
        return recovered
    receipt_path = root / "source_audio_receipt.json"
    if receipt_path.exists():
        existing = verify_source_narration(root)
        verify_written_episode(root)
        if (
            existing.get("media_sha256") == media_sha256
            and existing.get("start_seconds") == start_seconds
            and existing.get("end_seconds") == end_seconds
        ):
            return existing
        raise ValueError("A different source narration is already published; use a fresh run")
    if any((root / name).exists() for name in _DOWNSTREAM_ARTIFACTS):
        raise ValueError("Existing downstream artifacts prevent source narration import")
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(media),
        ],
        capture_output=True, text=True, check=True, timeout=60,
    )
    source_duration = float(probe.stdout.strip())
    if end_seconds > source_duration + 0.05:
        raise ValueError("Requested excerpt extends beyond source media")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=root, suffix=".wav", delete=False) as handle:
            temporary = Path(handle.name)
        result = subprocess.run(
            [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(media), "-ss", str(start_seconds), "-t", str(end_seconds - start_seconds),
                "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "48000",
                "-c:a", "pcm_s16le", str(temporary),
            ],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode:
            raise RuntimeError(f"FFmpeg narration import failed: {result.stderr[-800:]}")
        with wave.open(str(temporary), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getframerate() != 48000 or wav.getsampwidth() != 2:
                raise ValueError("Imported narration is not mono 48 kHz 16-bit PCM")
            duration = wav.getnframes() / wav.getframerate()
        if abs(duration - (end_seconds - start_seconds)) > 0.05:
            raise ValueError("Imported narration duration does not match the requested excerpt")
        if load_brief(root) != brief or _sha256(media) != media_sha256:
            raise ValueError("Source inputs changed during narration import")
        text = raw.strip() + "\n"
        outputs = {
            "breaked_paragraphs.txt": text,
            "final_output.txt": text,
            "refined_script.txt": text,
        }
        source_receipt: dict[str, Any] = {
            "version": 1,
            "mode": "source_preserved",
            "recipe": source_recipe,
            "brief_sha256": brief_sha256,
            "media_name": media.name,
            "media_sha256": media_sha256,
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
            "audio_sha256": _sha256(temporary),
            "audio_duration_seconds": duration,
        }
        writing_receipt = {
            "version": 1,
            "mode": "source_preserved",
            "brief_sha256": narration_fingerprint(brief),
            "outputs": {name: fingerprint(value) for name, value in outputs.items()},
        }
        accepted_dir = root / "source_audio"
        accepted_dir.mkdir(exist_ok=True)
        accepted = accepted_dir / f"{source_receipt['audio_sha256']}.wav"
        journal = _journal_path(root, source_recipe)
        journal.parent.mkdir(parents=True, exist_ok=True)
        with publication_guard():
            if receipt_path.exists() or any((root / name).exists() for name in _DOWNSTREAM_ARTIFACTS):
                raise ValueError("Source narration appeared during import; refusing to replace it")
            atomic_write_json(
                str(journal),
                {
                    "version": 1,
                    "kind": "source_audio",
                    "recipe": source_recipe,
                    "accepted_path": accepted.relative_to(root).as_posix(),
                    "source_receipt": source_receipt,
                    "writing_receipt": writing_receipt,
                    "outputs": outputs,
                },
            )
            if accepted.exists():
                if _sha256(accepted) != source_receipt["audio_sha256"]:
                    raise ValueError("Accepted source narration digest collision")
                temporary.unlink()
            else:
                os.replace(temporary, accepted)
            temporary = None
        recovered = _recover_pending_source(root, source_recipe)
        if recovered is None:
            raise RuntimeError("Complete source narration publication could not be recovered")
        return recovered
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
