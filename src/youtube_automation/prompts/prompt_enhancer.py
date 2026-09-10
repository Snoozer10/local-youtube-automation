"""Socratic Prompt Enhancer Module.

Operationalizes the 5 empirical NotebookLM Socratic prompt engineering rules:
1. Modular prompt scaffolding & single-generation inference pass
2. 1-2-3 shape hierarchy (primary silhouette, sub-structures, small accents)
3. Da Vinci Sfumato chiaroscuro lighting against desaturated negative space
4. 24mm wide-angle lens with f/1.8 optical framing
5. Strict negative latent suppression (~94% compliance filter)
6. English-only compliance (ADR 0003: zero raw Arabic characters in diffusion prompts)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from typing import Any, Optional

from youtube_automation.prompts.validator import (
    FrameItem,
    STRICT_NEGATIVE_PROMPT,
    VisualPrompt,
    flatten_visual_prompt_to_diffusion_text,
    purge_subtitle_phrases,
    transliterate_arabic_fallback,
    validate_english_only_prompt,
    verify_pipeline_integrity,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SOCRATIC_STYLE_DNA = (
    "2D graphic vector animation explainer style, crisp 3px black vector outlines, "
    "flat 2-step cel-shading, 1-2-3 shape hierarchy, 16:9 widescreen"
)

SOCRATIC_LIGHTING_DNA = (
    "Da Vinci Sfumato chiaroscuro lighting against desaturated negative space, "
    "warm amber keylight (#E09F3E)"
)

SOCRATIC_CAMERA_DNA = (
    "24mm wide-angle lens, f/1.8 shallow depth of field, balanced 16:9 widescreen framing"
)

SOCRATIC_NEGATIVE_PROMPT = (
    f"{STRICT_NEGATIVE_PROMPT}, no burned subtitles, no chalkboard clutter, "
    "no specular glare, no fake HDR, no 3D CGI, no photorealism, no blurry details, "
    "no visual noise, no text in lower-third"
)


def _ensure_english_text(text: str) -> str:
    """Ensures text has no raw Arabic script by applying transliteration (ADR 0003)."""
    if not text:
        return ""
    valid, _ = validate_english_only_prompt(text)
    if not valid:
        return transliterate_arabic_fallback(text)
    return text


def enhance_visual_prompt(vp: VisualPrompt | dict[str, Any]) -> VisualPrompt:
    """
    Elevates an 8-part VisualPrompt using the 5 empirical Socratic principles.
    Injects 1-2-3 shape hierarchy, Da Vinci Sfumato chiaroscuro, 24mm optics,
    and reinforced negative latent suppression.
    """
    if isinstance(vp, dict):
        data = dict(vp)
    else:
        data = vp.model_dump()

    # 1. English-Only Sanitization (ADR 0003)
    subject = _ensure_english_text(data.get("subject") or data.get("subject_details", "")).strip()
    action = _ensure_english_text(data.get("action") or data.get("subject_action_increment", "")).strip()
    setting = _ensure_english_text(data.get("setting") or data.get("environment_coordinates", "")).strip()
    mood = data.get("mood", "").strip()
    lighting = data.get("lighting", "").strip()
    composition = data.get("composition") or data.get("composition_layout", "").strip()
    style = data.get("style") or data.get("style_anchor", "").strip()
    user_negative = data.get("negative_prompt", "").strip()
    continuity_id = data.get("continuity_id", "").strip()

    # 2. Rule 2: 1-2-3 Shape Hierarchy Injection into Style
    if not style:
        style = SOCRATIC_STYLE_DNA
    else:
        if "1-2-3 shape hierarchy" not in style.lower():
            style = f"{style.rstrip('.')}, 1-2-3 shape hierarchy"
        if "3px" not in style.lower():
            style = f"{style.rstrip('.')}, crisp 3px black vector outlines"
        if "cel-shading" not in style.lower():
            style = f"{style.rstrip('.')}, flat 2-step cel-shading"

    # 3. Rule 3: Da Vinci Sfumato Chiaroscuro Lighting
    if not lighting:
        lighting = SOCRATIC_LIGHTING_DNA
    else:
        if "sfumato" not in lighting.lower() and "chiaroscuro" not in lighting.lower():
            lighting = f"{lighting.rstrip('.')}, Da Vinci Sfumato chiaroscuro lighting against desaturated negative space"

    # 4. Rule 4: 24mm Wide-Angle Optics Framing
    if not composition:
        composition = SOCRATIC_CAMERA_DNA
    else:
        if "24mm" not in composition.lower():
            composition = f"{composition.rstrip('.')}, 24mm wide-angle lens, f/1.8 shallow depth of field"

    # 5. Rule 5: Reinforced Negative Latent Suppression (~94% compliance)
    negative_tokens = set()
    if user_negative:
        for token in user_negative.split(","):
            cleaned = token.strip()
            if cleaned:
                negative_tokens.add(cleaned)
    for token in SOCRATIC_NEGATIVE_PROMPT.split(","):
        cleaned = token.strip()
        if cleaned:
            negative_tokens.add(cleaned)

    # Reassemble deterministic ordered negative prompt
    ordered_negative = ", ".join(sorted(negative_tokens))

    # Purge subtitle triggers across all fields
    subject = purge_subtitle_phrases(subject)
    action = purge_subtitle_phrases(action)
    setting = purge_subtitle_phrases(setting)
    composition = purge_subtitle_phrases(composition)

    return VisualPrompt(
        subject=subject or "Al-Daheeh cartoon host",
        action=action,
        setting=setting,
        mood=mood or "dramatic, focused, engaging",
        lighting=lighting,
        composition=composition,
        style=style,
        negative_prompt=ordered_negative,
        continuity_id=continuity_id,
        # Preserve legacy fields for backward compatibility
        subject_details=subject,
        subject_action_increment=action,
        environment_coordinates=setting,
        composition_layout=composition,
        style_anchor=style,
        text_overlay_arabic="NONE",
    )


def enhance_frame_item(item: FrameItem | dict[str, Any]) -> FrameItem:
    """Enhances a FrameItem payload with Socratic prompt engineering principles."""
    if isinstance(item, dict):
        raw = dict(item)
    else:
        raw = item.model_dump()

    vp_raw = raw.get("visual_prompt", {})
    enhanced_vp = enhance_visual_prompt(vp_raw)

    seq_meta = raw.get("sequence_metadata", {})
    if not isinstance(seq_meta, dict):
        seq_meta = {"set_id": "SET_01", "frame_index": 1, "total_frames_in_set": 1}

    return FrameItem(
        index=int(raw.get("index", 1)),
        timestamp=str(raw.get("timestamp", "")),
        sequence_type=str(raw.get("sequence_type", "STANDALONE")),
        layout_classification=str(raw.get("layout_classification", "")),
        sequence_metadata=seq_meta,
        visual_density=str(raw.get("visual_density", "MINIMALIST_MACRO")),
        visual_prompt=enhanced_vp,
    )


def enhance_diffusion_prompt(
    input_data: VisualPrompt | FrameItem | dict[str, Any] | str,
    sequence_type: str = "STANDALONE",
) -> str:
    """
    Transforms any prompt payload or raw string into an elevated, production-grade
    diffusion prompt conforming to the 5 Socratic principles.
    """
    if isinstance(input_data, str):
        # Raw string handling
        cleaned_str = _ensure_english_text(purge_subtitle_phrases(input_data))
        parts = [
            cleaned_str.rstrip(".") + ".",
            f"Composition: {SOCRATIC_CAMERA_DNA}.",
            f"Lighting: {SOCRATIC_LIGHTING_DNA}.",
            f"Art Style: {SOCRATIC_STYLE_DNA}.",
            f"Negative Prompt: {SOCRATIC_NEGATIVE_PROMPT}.",
        ]
        return " ".join(parts)

    if isinstance(input_data, FrameItem):
        enhanced_item = enhance_frame_item(input_data)
        return flatten_visual_prompt_to_diffusion_text(
            enhanced_item.visual_prompt.model_dump(), sequence_type=enhanced_item.sequence_type
        )

    if isinstance(input_data, VisualPrompt):
        enhanced_vp = enhance_visual_prompt(input_data)
        return flatten_visual_prompt_to_diffusion_text(
            enhanced_vp.model_dump(), sequence_type=sequence_type
        )

    if isinstance(input_data, dict):
        if "visual_prompt" in input_data and "index" in input_data:
            enhanced_item = enhance_frame_item(input_data)
            return flatten_visual_prompt_to_diffusion_text(
                enhanced_item.visual_prompt.model_dump(), sequence_type=enhanced_item.sequence_type
            )
        else:
            enhanced_vp = enhance_visual_prompt(input_data)
            return flatten_visual_prompt_to_diffusion_text(
                enhanced_vp.model_dump(), sequence_type=sequence_type
            )

    return str(input_data)


def transform_prompts_file(
    input_file: str,
    output_file: str,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Transforms flow_prompts.json into an elevated flow_prompts_socratic.json.
    Guarantees atomic disk writes and pipeline integrity verification.
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input prompts file does not exist: {input_file}")

    with open(input_file, encoding="utf-8") as f:
        raw_items = json.load(f)

    if not isinstance(raw_items, list):
        raise ValueError(f"Expected JSON array in {input_file}, got {type(raw_items)}")

    if limit is not None and limit > 0:
        raw_items = raw_items[:limit]

    enhanced_frames: list[FrameItem] = []
    for item in raw_items:
        enhanced_frames.append(enhance_frame_item(item))

    # Verify pipeline integrity
    payloads = [frame.model_dump() for frame in enhanced_frames]
    verify_pipeline_integrity(payloads, len(enhanced_frames))

    # Atomic write to output_file
    output_dir = os.path.dirname(os.path.abspath(output_file))
    os.makedirs(output_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output_dir, delete=False) as tf:
        json.dump(payloads, tf, ensure_ascii=False, indent=2)
        temp_name = tf.name

    os.replace(temp_name, output_file)
    return payloads


def transform_roadmap_jsonl(
    input_file: str,
    output_file: str,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Transforms master_roadmap.jsonl into master_roadmap_socratic.jsonl.
    Preserves all column semantics while injecting Socratic visual concepts.
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input roadmap file does not exist: {input_file}")

    rows: list[dict[str, Any]] = []
    with open(input_file, encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                row = json.loads(line_str)
                rows.append(row)
            except json.JSONDecodeError:
                continue

    if limit is not None and limit > 0:
        rows = rows[:limit]

    enhanced_rows: list[dict[str, Any]] = []
    for r in rows:
        concept = r.get("visual_concept", "")
        # Inject shape hierarchy and Sfumato lighting into concept
        if concept and "1-2-3 shape hierarchy" not in concept:
            concept = f"{concept.rstrip('.')}. 1-2-3 shape hierarchy with Da Vinci Sfumato chiaroscuro lighting."
        r["visual_concept"] = concept
        enhanced_rows.append(r)

    output_dir = os.path.dirname(os.path.abspath(output_file))
    os.makedirs(output_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output_dir, delete=False) as tf:
        for r in enhanced_rows:
            tf.write(json.dumps(r, ensure_ascii=False) + "\n")
        temp_name = tf.name

    os.replace(temp_name, output_file)
    return enhanced_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Socratic Prompt Enhancer CLI")
    parser.add_argument("--input", required=True, help="Path to input JSON or JSONL file")
    parser.add_argument("--output", required=True, help="Path to output enhanced file")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of frames to process")
    args = parser.parse_args()

    if args.input.endswith(".jsonl"):
        print(f"Transforming roadmap JSONL: {args.input} -> {args.output}")
        out = transform_roadmap_jsonl(args.input, args.output, limit=args.limit)
        print(f"Successfully transformed {len(out)} roadmap rows.")
    else:
        print(f"Transforming flow prompts JSON: {args.input} -> {args.output}")
        out = transform_prompts_file(args.input, args.output, limit=args.limit)
        print(f"Successfully transformed {len(out)} prompt items.")


if __name__ == "__main__":
    main()
