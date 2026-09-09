"""Drill 01.01: AI Studio TTS Paragraph Parsing & Filename Sequencing (Reference Solution).

Directly leverages the production audio pipeline logic from:
- src.youtube_automation.audio.tts_generator
- src.youtube_automation.audio.chapter_stitcher
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from src.youtube_automation.audio.chapter_stitcher import scan_sequential_chapters
from src.youtube_automation.audio.tts_generator import sanitize_script_text


def sanitize_tts_script(raw_text: str) -> str:
    """Sanitizes raw script text using the canonical pipeline sanitizer."""
    return sanitize_script_text(raw_text)


def extract_tts_blocks(script_text: str) -> list[dict[str, Any]]:
    """Splits sanitized script into sequential chapter block dictionaries."""
    clean = sanitize_tts_script(script_text)
    if not clean:
        return []

    # Check for structured block headers: e.g. "TTS BLOCK 1 of 8" or "## Chapter 1"
    header_pattern = re.compile(
        r"(?:(?:TTS\s*BLOCK|BLOCK|CHAPTER|الجزء)\s*\[?\d+\]?\s*(?:of|OF|من|\/)?\s*\[?\d*\]?|##\s*Chapter\s*\d+)",
        re.IGNORECASE,
    )

    # Split on double newlines or headers
    raw_splits = header_pattern.split(clean)
    blocks: list[str] = []

    for chunk in raw_splits:
        # If no headers were matched, raw_splits has length 1.
        # Check if multiple paragraphs exist
        paragraphs = [p.strip() for p in chunk.split("\n\n") if p.strip()]
        blocks.extend(paragraphs)

    # Filter out empty blocks and build 1-based indexed manifest items
    result: list[dict[str, Any]] = []
    idx = 1
    for b in blocks:
        stripped = b.strip()
        if not stripped:
            continue
        result.append(
            {
                "chapter_num": idx,
                "text": stripped,
                "audio_file": f"Chapter_{idx}.wav",
                "status": "PENDING",
            }
        )
        idx += 1

    return result


def verify_chapter_sequence(chapter_files: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Analyzes a list of chapter filenames and identifies contiguous prefix, gaps, and orphans."""
    if not chapter_files:
        return [], [], []

    # Map indices to basenames
    present_indices: dict[int, str] = {}
    for path_str in chapter_files:
        fname = os.path.basename(path_str)
        match = re.match(r"^Chapter_(\d+)\.wav$", fname, re.IGNORECASE)
        if match:
            idx = int(match.group(1))
            present_indices[idx] = fname

    if not present_indices:
        return [], [], []

    max_idx = max(present_indices.keys())
    contiguous_prefix: list[str] = []
    missing_files: list[str] = []
    orphan_files: list[str] = []
    gap_found = False

    for i in range(1, max_idx + 1):
        if i in present_indices:
            if gap_found:
                orphan_files.append(present_indices[i])
            else:
                contiguous_prefix.append(present_indices[i])
        else:
            missing_files.append(f"Chapter_{i}.wav")
            gap_found = True

    return contiguous_prefix, missing_files, orphan_files


def scan_directory_for_chapters(target_dir: str | Path) -> tuple[list[str], list[str]]:
    """Wraps production scan_sequential_chapters from chapter_stitcher."""
    return scan_sequential_chapters(str(target_dir))
