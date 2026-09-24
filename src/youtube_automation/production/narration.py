"""Deterministic, content-bound narration chapters for adaptive channels."""

from __future__ import annotations

import hashlib
import wave
from pathlib import Path
from typing import Any

from .contracts import Brief, fingerprint, narration_fingerprint


def require_unpolished_run(run_dir: str | Path) -> None:
    """Prevent a voice rerun from replacing physical polished offsets with raw timings."""
    root = Path(run_dir)
    polished = root / "polished_chapters"
    if (root / "full_episode_voice.wav").exists() or (
        polished.exists() and any(polished.glob("Chapter_*.wav"))
    ):
        raise ValueError("Adaptive voice run already has polished or stitched audio; use a fresh run")


def split_chapters(run_dir: str | Path, script: str, *, max_words: int = 220) -> list[dict[str, Any]]:
    """Partition source words without asking another model to rewrite the script."""
    if max_words <= 0 or not script.strip():
        raise ValueError("Narration needs a nonempty script and positive chapter budget")
    paragraphs = [paragraph.split() for paragraph in script.split("\n\n")]
    chapters: list[list[str]] = []
    current: list[str] = []
    for paragraph in paragraphs:
        while paragraph:
            available = max_words - len(current)
            if not available:
                chapters.append(current)
                current = []
                available = max_words
            current.extend(paragraph[:available])
            paragraph = paragraph[available:]
            if paragraph:
                chapters.append(current)
                current = []
    if current:
        chapters.append(current)
    result: list[dict[str, Any]] = []
    for index, words in enumerate(chapters, 1):
        path = Path(run_dir).resolve() / "voice_chapters" / f"Chapter_{index}.wav"
        result.append({"chapter_num": index, "text": " ".join(words), "audio_file": str(path), "status": "PENDING"})
    if " ".join(" ".join(chapter["text"].split()) for chapter in result) != " ".join(script.split()):
        raise ValueError("Narration chapter coverage differs from the source script")
    return result


def prepare_manifest(run_dir: str | Path, manifest: dict[str, Any], brief: Brief, script: str) -> dict[str, Any]:
    """Resume only chapters from this exact script, channel and voice."""
    expected = split_chapters(run_dir, script)
    recipe = fingerprint(
        {
            "version": 1,
            "script": script,
            "brief": narration_fingerprint(brief),
            "voice": brief.channel.voice,
        }
    )
    existing = manifest.get("chapters", [])
    marker = manifest.get("adaptive_voice_recipe")
    if existing:
        if marker != recipe or len(existing) != len(expected):
            raise ValueError("Existing voice chapters have no matching adaptive recipe")
        for prior, planned in zip(existing, expected, strict=True):
            for key in ("chapter_num", "text"):
                if prior.get(key) != planned[key]:
                    raise ValueError(f"Voice chapter changed since approval: {key}")
            prior_path = Path(prior.get("audio_file", ""))
            if not prior_path.is_absolute():
                prior_path = Path(run_dir) / prior_path
            if prior_path.resolve() != Path(planned["audio_file"]):
                raise ValueError("Voice chapter output path changed since approval")
            if prior.get("status") == "COMPLETED":
                digest = prior.get("md5")
                if not isinstance(digest, str) or len(digest) != 32 or not prior_path.is_file():
                    raise ValueError("Completed voice chapter is missing its audio or digest")
                digestor = hashlib.md5()
                with prior_path.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        digestor.update(block)
                actual = digestor.hexdigest()
                if actual != digest:
                    raise ValueError("Completed voice chapter audio changed since synthesis")
                try:
                    with wave.open(str(prior_path), "rb") as audio:
                        if audio.getnframes() <= 0 or audio.getframerate() <= 0:
                            raise ValueError("Completed voice chapter is empty")
                except wave.Error as error:
                    raise ValueError("Completed voice chapter is not valid WAV audio") from error
    elif marker and marker != recipe:
        raise ValueError("Existing voice recipe uses a different script or channel")
    if manifest.get("voice_config", {}).get("voice") != brief.channel.voice:
        raise ValueError("Saved voice differs from selected channel")
    updated = dict(manifest)
    updated["chapters"] = existing or expected
    updated["adaptive_voice_recipe"] = recipe
    updated["gemini_completed"] = True
    return updated
