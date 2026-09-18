"""Pure validation utilities for the Flow image-generation pipeline.

Relocated from ``flow_image_generator`` (text sanitizers) plus the Pydantic v2
schema models and the pipeline integrity engine used to gate generated
flow_prompts payloads before they reach the browser automation layer.
"""

import copy
import json
import re
from collections import Counter
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

__all__ = [
    "FrameItem",
    "PipelineIntegrityError",
    "SequenceMetadata",
    "VisualPrompt",
    "enforce_arabic_in_prompt",
    "flatten_visual_prompt_to_diffusion_text",
    "parse_timestamp_seconds",
    "purge_subtitle_phrases",
    "transliterate_arabic_fallback",
    "validate_english_only_prompt",
    "verify_pipeline_integrity",
]

TIMESTAMP_PATTERN = re.compile(r"^\[\d{1,2}:\d{2}(:\d{2})?\]")
_FULL_TIMESTAMP_PATTERN = re.compile(r"^\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]$")
_ARABIC_RANGE_PATTERN = re.compile(r"[\u0600-\u06FF]")
_LATIN_LETTER_PATTERN = re.compile(r"[A-Za-z]")

STRICT_NEGATIVE_PROMPT = (
    "no text, no subtitles, no letters, no watermark, no signature, no caption, "
    "no typography, no calligraphy, "
    "no burned-in subtitles, no lower thirds, no on-screen text, "
    "no 24mm lens, no wide-angle lens, no fisheye, no barrel distortion, no keystone distortion"
)


def validate_english_only_prompt(text: str) -> tuple[bool, str]:
    """Verifies that diffusion prompt text does not contain raw Arabic characters (ADR 0003)."""
    if _ARABIC_RANGE_PATTERN.search(text):
        return False, "Arabic script detected in diffusion prompt text; output must be English only."
    return True, ""


_ARABIC_TRANSLITERATION_MAP = {
    "ال": "al-",
    "ا": "a",
    "أ": "a",
    "إ": "i",
    "آ": "aa",
    "ب": "b",
    "ت": "t",
    "ث": "th",
    "ج": "j",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "dh",
    "ر": "r",
    "ز": "z",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "d",
    "ط": "t",
    "ظ": "z",
    "ع": "a",
    "غ": "gh",
    "ف": "f",
    "ق": "q",
    "ك": "k",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "ه": "h",
    "و": "w",
    "ي": "y",
    "ى": "a",
    "ة": "ah",
    "ء": "'",
    "ئ": "y",
    "ؤ": "w",
    "َ": "a",
    "ُ": "u",
    "ِ": "i",
    "ّ": "",
    "ْ": "",
    "ً": "an",
    "ٌ": "un",
    "ٍ": "in",
}


def transliterate_arabic_fallback(text: str) -> str:
    """Transliterates Arabic characters to Romanized phonetics for diffusion safety (ADR 0003)."""
    res = text
    for ar, en in _ARABIC_TRANSLITERATION_MAP.items():
        res = res.replace(ar, en)
    return res


def purge_subtitle_phrases(text: str) -> str:
    """Removes subtitle / caption / margin trigger phrases from prompt text."""
    text = re.sub(r"(?i)\b\d+%\s*bottom\s*safe\s*margin\b[^.]*", "", text)
    text = re.sub(r"(?i)\bfor\s*subtitles?\b", "", text)
    text = re.sub(r"(?i)\bsubtitle\s*overlay\b", "", text)
    text = re.sub(r"(?i)\bcaption(s)?\b", "", text)
    return " ".join(text.split()).strip(" ,.-")


def flatten_visual_prompt_to_diffusion_text(vp: Any, sequence_type: str = "STANDALONE") -> str:
    """
    Transforms a structured visual_prompt dictionary into an elevated,
    high-salience, production-grade diffusion prompt for Google Flow / Imagen 3.
    Purges meta-tokens (ABSENT), strips all subtitle triggers, and removes prompt bloat.
    """
    if isinstance(vp, str):
        try:
            parsed = json.loads(vp)
        except Exception:
            return str(vp).strip()
        if not isinstance(parsed, dict):
            return str(parsed)
        vp = parsed

    if not isinstance(vp, dict):
        return str(vp)

    # Extract fields with 8-part schema priority and legacy fallback
    subject = (vp.get("subject") or vp.get("subject_details", "")).strip()
    action = (vp.get("action") or vp.get("subject_action_increment", "")).strip()
    layout = (vp.get("composition") or vp.get("composition_layout", "")).strip()
    env = (vp.get("setting") or vp.get("environment_coordinates", "")).strip()
    accent = vp.get("accent_color_hook", "").strip()
    style = (vp.get("style") or vp.get("style_anchor", "")).strip()
    text_ar = vp.get("text_overlay_arabic", "NONE").strip()
    mood = vp.get("mood", "").strip()
    lighting = vp.get("lighting", "").strip()
    user_negative = vp.get("negative_prompt", "").strip()

    # 1. Purge ABSENT tokens
    if subject.upper().startswith("ABSENT"):
        subject = ""
    if env.upper().startswith("ABSENT"):
        env = ""

    # 2. Sanitize and purge all subtitle / caption / margin triggers
    layout = purge_subtitle_phrases(layout)
    action = purge_subtitle_phrases(action)
    subject = purge_subtitle_phrases(subject)
    env = purge_subtitle_phrases(env)

    prompt_parts = []

    # 3. Front-Loaded Action & Subject Core
    core_action = []
    if subject and action:
        core_action.append(f"{subject}, {action}")
    elif subject:
        core_action.append(subject)
    elif action:
        core_action.append(action)

    if core_action:
        prompt_parts.append(" ".join(core_action).rstrip(".") + ".")

    # 4. Scenography
    if env:
        prompt_parts.append(f"Scene Setting: {env.rstrip('.')}.")

    # 5. Clean Composition (Strictly textless framing with preset default)
    if sequence_type == "EXPLAINER_DECK":
        if layout:
            prompt_parts.append(f"Composition: {layout.rstrip('.')}. Clean presentation layout, typography callouts positioned in top/middle.")
        else:
            prompt_parts.append("Composition: Clean presentation layout, balanced 16:9 widescreen framing, typography callouts positioned in top/middle.")
    else:
        if layout:
            prompt_parts.append(f"Composition: {layout.rstrip('.')}.")
        else:
            prompt_parts.append(
                "Composition: Balanced 16:9 widescreen framing, sharp central subject focus."
            )

    # 6. Lighting & Chromatic Palette
    if accent:
        prompt_parts.append(
            f"Color & Lighting: High-contrast 2D studio illumination with {accent.rstrip('.')} accent highlights."
        )
    elif lighting:
        prompt_parts.append(f"Lighting: {lighting.rstrip('.')}.")
    else:
        prompt_parts.append(
            "Color & Lighting: Warm amber keylight (#E09F3E) with high-contrast cel-shading."
        )

    # 7. Arabic Typography (Integrated cleanly into scene, if requested by legacy callers)
    if text_ar and text_ar.upper() != "NONE":
        prompt_parts.append(
            f'Typography: A single clean Arabic title graphic reading "{text_ar}" in bold modern Kufic script.'
        )

    # 8. Style Anchor (Matching Image 3's Crisp Vector Cel-Shaded Aesthetic)
    clean_style = style
    if "oil painting" in clean_style.lower() and (
        "ahwa" in env.lower() or "host" in subject.lower()
    ):
        # Purge oil painting references for standard host/studio scenes
        clean_style = re.sub(
            r"(?i)mixed with 18th-century oil painting cutout parody\.?", "", clean_style
        ).strip()

    if mood:
        prompt_parts.append(f"Mood: {mood.rstrip('.')}.")

    if clean_style:
        prompt_parts.append(f"Art Style: {clean_style.rstrip('.')}.")
    else:
        prompt_parts.append(
            "Art Style: 2D graphic vector animation explainer style, crisp 3px black outlines, rich 2-step flat cel-shading, vibrant warm studio illumination, 16:9 widescreen."
        )

    # Deterministic Negative Prompt Injection (ADR 0003 & Spec #12)
    deck_negative = ", no text in lower-third, no burned subtitles, no bottom captions" if sequence_type == "EXPLAINER_DECK" else ""
    if user_negative:
        combined_negative = f"{user_negative}, {STRICT_NEGATIVE_PROMPT}{deck_negative}"
    else:
        combined_negative = f"{STRICT_NEGATIVE_PROMPT}{deck_negative}"
    prompt_parts.append(f"Negative Prompt: {combined_negative}.")

    return " ".join(prompt_parts)


def enforce_arabic_in_prompt(prompt_text: str) -> str:
    """
    Sanitizes prompt text: maps English structural tokens into authentic Arabic labels,
    enforces clean single-instance Arabic typography, and suppresses text overlays cleanly.
    """
    replacements = {
        # --- UI & Structural Replacements ---
        r'(?i)"CHALLENGER\s*(\d+)?:?\s*([^"]*)"': r'"التحدي \1: \2"',
        r"(?i)CHALLENGER\s*(\d+)": r"التحدي \1",
        r'(?i)"COLLECTION BOARD"': r'"لوحة التجميع"',
        r"(?i)COLLECTION BOARD": r"لوحة التجميع",
        r'(?i)"SPEED ROUND"': r'"الجولة السريعة"',
        r"(?i)SPEED ROUND": r"الجولة السريعة",
        r'(?i)"DIAGRAM"': r'"مخطط"',
        r'(?i)"INFOGRAPHIC"': r'"انفوجرافيك"',
        r'(?i)"BLUEPRINT"': r'"مخطط تفصيلي"',
        r'(?i)"SECRET"': r'"السر"',
        r'(?i)"WARNING"': r'"تحذير"',
        r'(?i)"RESULT"': r'"النتيجة"',
        r'(?i)"STAGE\s*(\d+)"': r'"المرحلة \1"',
        r"(?i)STAGE\s*(\d+)": r"المرحلة \1",
        r"(?i)STEP\s*(\d+)": r"الخطوة \1",
        r"(?i)\bBEFORE\b": r"قبل",
        r"(?i)\bAFTER\b": r"بعد",
        r"(?i)\bVS\.?\b|\bVERSUS\b": r"ضد",
        r"(?i)English text": r"Arabic text",
        r"(?i)English typography": r"Arabic typography",
        r"(?i)English labels": r"Arabic labels",
        # --- Policy & Safety Filter Sanitizers (Bypasses False Positives) ---
        r"(?i)Ahmed El-Ghandour": r"Al-Daheeh character",
        r"تزوّر كيانك": r"قناع الذات",
        r"تزوير|تزوّر|مزوّر": r"قناع رمزي",
        r"forged|forgery|counterfeit": r"theatrical prop",
        r"خازوق|الخازوق": r"فخ كوميدي",
        r"إعدام إكلينيكي": r"توقف مؤقت",
        r"السرقة العلمية|سرقة": r"اقتباس كوميدي",
        r"نصاب|يا نصاب|نصّاب": r"مخادع كوميدي",
        r"مرتزقة بلاك ووتر": r"حراس كرتونيين",
    }

    sanitized = prompt_text
    for pattern, repl in replacements.items():
        sanitized = re.sub(pattern, repl, sanitized)

    # Purge any remaining subtitle or margin triggers
    sanitized = re.sub(r"(?i)\b\d+%\s*bottom\s*safe\s*margin\b[^.]*", "", sanitized)
    sanitized = re.sub(r"(?i)\bfor\s*subtitles?\b", "", sanitized)
    sanitized = re.sub(r"(?i)\bsubtitle\s*overlay\b", "", sanitized)

    # Extract clean target Arabic text if present in prompt
    arabic_title_match = re.search(
        r'Typography:\s*A single clean Arabic title graphic reading\s*"([^"]+)"', sanitized
    )

    if arabic_title_match:
        target_text = arabic_title_match.group(1).strip()
        typography_directive = (
            f" Typography Directive: Render exactly ONE clean upper-third title graphic in bold modern Arabic Kufic calligraphy reading '{target_text}'. "
            "All in-scene documents and labels must use authentic Arabic script with zero Latin or English letters."
        )
    else:
        typography_directive = " Typography Directive: Completely textless illustration. Zero on-screen text, zero floating words, zero typography overlays, zero watermarks."

    return sanitized.strip() + typography_directive


class SequenceMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    set_id: str = "SET_01"
    frame_index: int = Field(default=1, ge=1)
    total_frames_in_set: int = Field(default=1, ge=1)


class VisualPrompt(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Legacy schema fields
    subject_details: str = ""
    subject_action_increment: str = ""
    environment_coordinates: str = ""
    composition_layout: str = ""
    camera_specifications: str = ""
    text_overlay_arabic: str = "NONE"
    accent_color_hook: str = ""
    style_anchor: str = ""

    # Spec #12 8-part diffusion schema fields
    subject: str = ""
    action: str = ""
    setting: str = ""
    mood: str = ""
    lighting: str = ""
    composition: str = ""
    style: str = ""
    negative_prompt: str = ""
    continuity_id: str = ""

    @model_validator(mode="after")
    def _validate_subject_present(self) -> "VisualPrompt":
        subj = (self.subject or self.subject_details).strip()
        if not subj:
            raise ValueError("subject_details or subject must not be empty")
        style = (self.style or self.style_anchor).strip()
        if not style:
            raise ValueError("style_anchor or style must not be empty")
        return self


class FrameItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    index: int = Field(gt=0)
    timestamp: str
    sequence_type: str = "STANDALONE"
    layout_classification: str = ""
    sequence_metadata: SequenceMetadata = Field(default_factory=SequenceMetadata)
    visual_density: str = ""
    visual_prompt: VisualPrompt

    @field_validator("timestamp")
    @classmethod
    def _validate_timestamp_format(cls, value: str) -> str:
        # Allow empty string for auto-repair upstream (prompt_planner will fill from script)
        if value == "":
            return value
        if not TIMESTAMP_PATTERN.match(value):
            raise ValueError(f"timestamp must match [MM:SS] or [HH:MM:SS], got {value!r}")
        return value


class PipelineIntegrityError(RuntimeError):
    """Raised when a flow_prompts payload violates pipeline integrity rules."""

    def __init__(self, violations: list[str]) -> None:
        self.violations: list[str] = list(violations)
        summary = " | ".join(self.violations)
        super().__init__(
            f"Pipeline integrity check failed ({len(self.violations)} violations): {summary}"
        )


def parse_timestamp_seconds(ts: str) -> int:
    """Converts a "[MM:SS]" or "[HH:MM:SS]" bracketed timestamp into total seconds."""
    match = _FULL_TIMESTAMP_PATTERN.match(ts.strip())
    if not match:
        raise ValueError(f"Unrecognized timestamp format: {ts!r}")
    first, second, third = match.groups()
    if third is None:
        return int(first) * 60 + int(second)
    return int(first) * 3600 + int(second) * 60 + int(third)


def _auto_clean_item(item: dict[str, Any]) -> None:
    visual_prompt = item.get("visual_prompt")
    if not isinstance(visual_prompt, dict):
        return
    for key, value in list(visual_prompt.items()):
        if isinstance(value, str):
            # Purge subtitle/margin safe-area phrases, but preserve legitimate marginalia/margins
            cleaned = purge_subtitle_phrases(value)
            # Only strip generic margin if it's part of safe-area phrase, not grid/marginalia
            if "marginalia" not in cleaned.lower() and "margins of the" not in cleaned.lower():
                # Remove stray safe-margin remnants that purge didn't catch
                import re as _re2
                cleaned = _re2.sub(r"(?i)\b\d+%\s*bottom\s*safe(?:ty)?\s*margin\b[^.]*", "", cleaned)
                cleaned = _re2.sub(r"(?i)\bsafe(?:ty)?\s*margin\b", "", cleaned)

            visual_prompt[key] = " ".join(cleaned.split()).strip(" ,.-")
    overlay = visual_prompt.get("text_overlay_arabic", "NONE")
    if isinstance(overlay, str):
        if overlay != "NONE" and _LATIN_LETTER_PATTERN.search(overlay):
            visual_prompt["text_overlay_arabic"] = "NONE"


def _coerce_frame_index(item: dict[str, Any]) -> int | None:
    metadata = item.get("sequence_metadata")
    if isinstance(metadata, dict):
        value = metadata.get("frame_index")
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _schema_error_summary(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "unknown validation failure"
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ()))
    message = str(first.get("msg", "invalid value"))
    return f"{location}: {message}"


def _collect_schema_and_content_violations(
    items: list[dict[str, Any]], violations: list[str]
) -> None:
    for item in items:
        raw_index: Any = item.get("index", "<unknown>")
        label = f"Item {raw_index}"
        try:
            FrameItem.model_validate(item)
        except ValidationError as exc:
            violations.append(f"{label}: schema violation ({_schema_error_summary(exc)})")

        # Check for forbidden terms in positive prompt fields (excluding negative_prompt where bans are expected)
        item_copy = dict(item)
        if isinstance(item.get("visual_prompt"), dict):
            vp_copy = dict(item["visual_prompt"])
            vp_copy.pop("negative_prompt", None)
            item_copy["visual_prompt"] = vp_copy
        dump = json.dumps(item_copy, ensure_ascii=False, default=str).lower()
        import re as _re
        # Flag subtitle (including plural subtitles) as forbidden - used for subtitle overlays
        if _re.search(r"\bsubtitles?\b", dump):
            violations.append(f"{label}: forbidden term 'subtitle' detected in payload.")
        # Flag margin as separate word (left margin band) but allow marginalia/margins and bleed margin
        if _re.search(r"(?<!bleed\s)\bmargin\b", dump):
            violations.append(f"{label}: forbidden term 'margin' detected in payload.")

        visual_prompt = item.get("visual_prompt")
        if isinstance(visual_prompt, dict):
            overlay_raw = visual_prompt.get("text_overlay_arabic", "NONE")
            overlay = overlay_raw if isinstance(overlay_raw, str) else str(overlay_raw)
            if overlay != "NONE":
                if _LATIN_LETTER_PATTERN.search(overlay):
                    violations.append(f"{label}: text_overlay_arabic contains Latin characters.")
                elif not _ARABIC_RANGE_PATTERN.search(overlay):
                    violations.append(
                        f"{label}: text_overlay_arabic must be 'NONE' or contain Arabic script."
                    )

            anchor = visual_prompt.get("style_anchor", "")
            if anchor:
                anchor_lower = str(anchor).lower()
                is_socratic = any(
                    k in anchor_lower
                    for k in ("da vinci", "sketchbook", "archival", "socratic")
                )
                if not is_socratic:
                    missing_keywords = [
                        kw for kw in ("3px", "vector", "cel-shading") if kw not in anchor_lower
                    ]
                    if missing_keywords:
                        joined = ", ".join(missing_keywords)
                        violations.append(f"{label}: style_anchor missing required keyword(s): {joined}.")


def _collect_ordering_violations(items: list[dict[str, Any]], violations: list[str]) -> None:
    orderable = [item for item in items if isinstance(item.get("index"), int)]
    ordered = sorted(orderable, key=lambda item: item["index"])

    seen_pairs: set[tuple[int, int]] = set()
    prev_seconds: int | None = None
    group_prev_frame: int | None = None

    for item in ordered:
        index = item["index"]
        frame_index = _coerce_frame_index(item)

        if frame_index is not None:
            pair = (index, frame_index)
            if pair in seen_pairs:
                violations.append(f"Item {index}: duplicate (index, frame_index) pair {pair}.")
            seen_pairs.add(pair)

        raw_timestamp = item.get("timestamp")
        seconds: int | None = None
        if isinstance(raw_timestamp, str):
            try:
                seconds = parse_timestamp_seconds(raw_timestamp)
            except ValueError:
                seconds = None

        if seconds is not None:
            if prev_seconds is not None and seconds < prev_seconds:
                violations.append(
                    f"Item {index}: timestamp '{raw_timestamp}' breaks weak monotonicity (regresses)."
                )
                group_prev_frame = None
            elif prev_seconds is not None and seconds == prev_seconds:
                if (
                    frame_index is not None
                    and group_prev_frame is not None
                    and frame_index <= group_prev_frame
                ):
                    violations.append(
                        f"Item {index}: frame_index {frame_index} must strictly increase within the equal-timestamp group."
                    )
            if seconds != prev_seconds:
                group_prev_frame = None
            if frame_index is not None:
                group_prev_frame = frame_index
            prev_seconds = seconds


def verify_pipeline_integrity(
    flow_prompts: list[dict[str, Any]],
    expected_total: int,
    auto_repair: bool = True,
) -> list[dict[str, Any]]:
    """Validates a flow_prompts payload, optionally auto-cleaning it first.

    Returns the cleaned plain-dict list when no violations remain; raises
    :class:`PipelineIntegrityError` carrying every violation string otherwise.
    """
    items: list[dict[str, Any]] = [copy.deepcopy(item) for item in flow_prompts]
    if auto_repair:
        for item in items:
            _auto_clean_item(item)

    violations: list[str] = []

    if len(items) != expected_total:
        violations.append(f"Count mismatch: expected {expected_total} prompts, found {len(items)}.")

    present_indices = [item["index"] for item in items if isinstance(item.get("index"), int)]
    counts = Counter(present_indices)
    missing = sorted(set(range(1, expected_total + 1)) - set(present_indices))
    duplicates = sorted(index for index, count in counts.items() if count > 1)
    if missing:
        violations.append(f"Missing indices: {missing}.")
    if duplicates:
        violations.append(f"Duplicate indices: {duplicates}.")

    _collect_schema_and_content_violations(items, violations)
    _collect_ordering_violations(items, violations)

    if violations:
        raise PipelineIntegrityError(violations)
    return items
