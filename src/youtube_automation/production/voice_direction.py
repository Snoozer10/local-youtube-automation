"""Voice direction for Gemini 3.8 Flash TTS: a per-run Style plus validated inline <tags>.

`voice_direction.json` in the run directory binds one approved direction to the exact narration:
removing the tags must give back the script word for word, paragraph for paragraph. Tags come from
`voice_tags.json` (the AI Studio "+ Expression" chips, identical to Google's documented list).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .contracts import fingerprint

FLASH_MODEL = "gemini-3.8-flash-tts"
PRO_MODEL = "gemini-2.5-pro-preview-tts"
DIRECTION_FILE = "voice_direction.json"
MAX_STYLE_CHARS = 600
MAX_TAGS_PER_PARAGRAPH = 4
WORDS_PER_TAG = 8
MAX_CONSECUTIVE_TAGS = 2
_TAG = re.compile(r"<([^<>\n]{1,40})>")
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")


class VoiceDirectionError(ValueError):
    """The voice direction is missing, stale or would change the spoken words."""


@dataclass(frozen=True)
class VoiceDirection:
    model: str
    style: str
    paragraphs: tuple[str, ...]
    sha256: str


@dataclass(frozen=True)
class SpeechText:
    clean_text: str
    directed_text: str
    paragraph_count: int


@lru_cache(maxsize=1)
def load_tag_library() -> dict[str, dict[str, str]]:
    data = json.loads((Path(__file__).with_name("voice_tags.json")).read_text(encoding="utf-8"))
    return dict(data["tags"])


def adaptive_tts_model() -> str:
    model = os.environ.get("ADAPTIVE_TTS_MODEL", FLASH_MODEL).strip() or FLASH_MODEL
    if model not in (FLASH_MODEL, PRO_MODEL):
        raise VoiceDirectionError(f"ADAPTIVE_TTS_MODEL must be {FLASH_MODEL} or {PRO_MODEL}")
    return model


def pro_fallback_enabled() -> bool:
    return os.environ.get("ADAPTIVE_TTS_PRO_FALLBACK", "").strip() == "1"


def find_tags(text: str) -> list[str]:
    return [match.group(1) for match in _TAG.finditer(text)]


def strip_tags(text: str) -> str:
    """Replace each known tag with a space, so a tag can never glue two words together."""
    library = load_tag_library()
    stripped = _TAG.sub(lambda m: " " if m.group(1) in library else m.group(0), text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in stripped.split("\n")]
    return "\n".join(lines)


def _paragraphs(script: str) -> list[str]:
    text = script.replace("\r\n", "\n").replace("\r", "\n")
    return [part.strip() for part in _PARAGRAPH_BREAK.split(text) if part.strip()]


def _check_paragraph(index: int, directed: str, clean: str, allow: set[str]) -> None:
    library = load_tag_library()
    tags = find_tags(directed)
    for tag in tags:
        if tag not in library:
            raise VoiceDirectionError(f"Paragraph {index + 1}: unknown tag <{tag}>")
        if library[tag]["level"] == "avoid" and tag not in allow:
            raise VoiceDirectionError(f"Paragraph {index + 1}: <{tag}> is not for narrators")
    if "<" in strip_tags(directed) or ">" in strip_tags(directed):
        raise VoiceDirectionError(f"Paragraph {index + 1}: stray angle bracket")
    spoken, expected = strip_tags(directed).split(), clean.split()
    if spoken != expected:
        at = next(
            (i for i, pair in enumerate(zip(spoken, expected, strict=False)) if pair[0] != pair[1]),
            min(len(spoken), len(expected)),
        )
        raise VoiceDirectionError(
            f"Paragraph {index + 1}: spoken words differ from the script at word {at + 1}"
        )
    limit = min(MAX_TAGS_PER_PARAGRAPH, max(1, len(expected) // WORDS_PER_TAG))
    if len(tags) > limit:
        raise VoiceDirectionError(f"Paragraph {index + 1}: {len(tags)} tags exceeds {limit}")
    run = 0
    for token in _tokens(directed):
        run = run + 1 if _TAG.fullmatch(token) else 0
        if run > MAX_CONSECUTIVE_TAGS:
            raise VoiceDirectionError(f"Paragraph {index + 1}: too many consecutive tags")


def _normalized_script(script: str) -> str:
    """LF endings, trimmed: a trailing newline never changes the script binding."""
    return script.replace("\r\n", "\n").replace("\r", "\n").strip()


def build_direction(
    script: str,
    *,
    channel_id: str,
    style: str,
    paragraphs: list[str],
    approved_by: str | None = None,
    allow_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Return a direction payload; it loads only once `approval` is present."""
    payload: dict[str, Any] = {
        "version": 1,
        "kind": "voice_direction",
        "channel_id": channel_id,
        "model": FLASH_MODEL,
        "script_sha256": fingerprint(_normalized_script(script)),
        "style": style,
        "paragraphs": paragraphs,
    }
    if allow_tags:
        payload["allow_tags"] = allow_tags
    if approved_by:
        payload["approval"] = {"approved_by": approved_by, "statement": "APPROVED"}
    return payload


def validate_direction_payload(
    data: Any,
    script: str,
    *,
    channel_id: str,
    require_approval: bool = True,
) -> None:
    """Validate spoken words and settings without reading or approving a file."""
    if (
        not isinstance(data, dict)
        or data.get("version") != 1
        or data.get("kind") != "voice_direction"
    ):
        raise VoiceDirectionError(f"{DIRECTION_FILE} has an unsupported version or kind")
    if data.get("channel_id") != channel_id:
        raise VoiceDirectionError(f"{DIRECTION_FILE} belongs to another channel")
    if data.get("model") != FLASH_MODEL:
        raise VoiceDirectionError(f"{DIRECTION_FILE} must target {FLASH_MODEL}")
    normalized = _normalized_script(script)
    if not normalized:
        raise VoiceDirectionError("The narration script is empty")
    if data.get("script_sha256") != fingerprint(normalized):
        raise VoiceDirectionError(f"{DIRECTION_FILE} was written for a different script")
    approval = data.get("approval")
    if require_approval and not (
        isinstance(approval, dict)
        and isinstance(approval.get("approved_by"), str)
        and approval["approved_by"].strip()
        and approval.get("statement") == "APPROVED"
    ):
        raise VoiceDirectionError(f"{DIRECTION_FILE} is not approved")
    style = data.get("style")
    if not isinstance(style, str) or not style.strip():
        raise VoiceDirectionError("A Style is required on every Flash voice run")
    if len(style) > MAX_STYLE_CHARS or "<" in style or ">" in style:
        raise VoiceDirectionError(f"Style must be plain text up to {MAX_STYLE_CHARS} characters")
    if "<" in normalized or ">" in normalized:
        raise VoiceDirectionError(
            "The script itself contains angle brackets; tags would be ambiguous"
        )
    allow = data.get("allow_tags", [])
    library = load_tag_library()
    if not isinstance(allow, list) or any(
        not isinstance(tag, str) or tag not in library for tag in allow
    ):
        raise VoiceDirectionError("allow_tags must list known tags")
    directed = data.get("paragraphs")
    clean = _paragraphs(normalized)
    if not isinstance(directed, list) or not all(isinstance(p, str) for p in directed):
        raise VoiceDirectionError("paragraphs must be a list of strings")
    if len(directed) != len(clean):
        raise VoiceDirectionError(
            f"Direction has {len(directed)} paragraphs, the script has {len(clean)}"
        )
    for index, (directed_paragraph, clean_paragraph) in enumerate(
        zip(directed, clean, strict=True)
    ):
        _check_paragraph(index, directed_paragraph, clean_paragraph, set(allow))

def load_voice_direction(
    run_dir: str | Path, script: str, *, channel_id: str
) -> VoiceDirection | None:
    path = Path(run_dir) / DIRECTION_FILE
    if not path.is_file():
        return None
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VoiceDirectionError(f"{DIRECTION_FILE} is not valid UTF-8 JSON") from exc
    validate_direction_payload(data, script, channel_id=channel_id)
    from .direction_stage import validate_accepted_direction

    validate_accepted_direction(run_dir, data)
    return VoiceDirection(
        model=FLASH_MODEL,
        style=data["style"].strip(),
        paragraphs=tuple(p.strip() for p in data["paragraphs"]),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def _tokens(directed: str) -> list[str]:
    return re.findall(r"<[^<>\n]{1,40}>|[^\s<]+", directed)


def _units(directed: str) -> list[str]:
    """One unit per spoken word; tags join the next word (or the last word at the end)."""
    units: list[str] = []
    pending: list[str] = []
    for token in _tokens(directed):
        if _TAG.fullmatch(token):
            pending.append(token)
            continue
        units.append(" ".join([*pending, token]))
        pending = []
    if pending:
        if not units:
            raise VoiceDirectionError("A directed paragraph has tags but no words")
        units[-1] = " ".join([units[-1], *pending])
    return units


def chapter_speech(
    script: str, chapters: list[dict[str, Any]], direction: VoiceDirection | None
) -> dict[int, SpeechText]:
    """Map each manifest chapter to its paragraphs, clean and directed, without changing words."""
    clean_paragraphs = _paragraphs(script)
    words = [paragraph.split() for paragraph in clean_paragraphs]
    if direction is None:
        units = words
    else:
        if len(direction.paragraphs) != len(clean_paragraphs):
            raise VoiceDirectionError("Direction paragraphs no longer match the script")
        units = [_units(paragraph) for paragraph in direction.paragraphs]
        if [len(u) for u in units] != [len(w) for w in words]:
            raise VoiceDirectionError("Direction words no longer match the script")
    stream = [(p, w) for p, paragraph in enumerate(words) for w in range(len(paragraph))]
    cursor = 0
    result: dict[int, SpeechText] = {}
    for chapter in chapters:
        chapter_words = str(chapter.get("text", "")).split()
        span = stream[cursor : cursor + len(chapter_words)]
        if not chapter_words or [words[p][w] for p, w in span] != chapter_words:
            raise VoiceDirectionError(
                f"Chapter {chapter.get('chapter_num')} differs from the script"
            )
        cursor += len(chapter_words)
        clean_parts: dict[int, list[str]] = {}
        directed_parts: dict[int, list[str]] = {}
        for p, w in span:
            clean_parts.setdefault(p, []).append(words[p][w])
            directed_parts.setdefault(p, []).append(units[p][w])
        clean = [" ".join(clean_parts[p]) for p in clean_parts]
        directed = [" ".join(directed_parts[p]) for p in directed_parts]
        result[int(chapter["chapter_num"])] = SpeechText(
            clean_text="\n\n".join(clean),
            directed_text="\n\n".join(directed),
            paragraph_count=len(clean),
        )
    if cursor != len(stream):
        raise VoiceDirectionError("Voice chapters do not cover the whole script")
    return result


def split_pieces(speech: SpeechText, max_paragraphs: int = 2) -> list[SpeechText]:
    if max_paragraphs <= 0:
        raise VoiceDirectionError("max_paragraphs must be positive")
    clean = speech.clean_text.split("\n\n")
    directed = speech.directed_text.split("\n\n")
    if len(clean) != len(directed) or len(clean) != speech.paragraph_count:
        raise VoiceDirectionError("Clean and directed paragraphs are misaligned")
    return [
        SpeechText(
            clean_text="\n\n".join(clean[i : i + max_paragraphs]),
            directed_text="\n\n".join(directed[i : i + max_paragraphs]),
            paragraph_count=len(clean[i : i + max_paragraphs]),
        )
        for i in range(0, len(clean), max_paragraphs)
    ]


def concat_wavs(parts: list[str | Path], dest: str | Path, *, gap_sec: float = 0.45) -> None:
    """Join piece WAVs in order with a paragraph gap; parameters must match exactly."""
    if not parts:
        raise VoiceDirectionError("No audio pieces to join")
    frames: list[bytes] = []
    params = None
    for part in parts:
        try:
            with wave.open(str(part), "rb") as audio:
                current = (audio.getnchannels(), audio.getsampwidth(), audio.getframerate())
                if audio.getcomptype() != "NONE" or audio.getnframes() <= 0:
                    raise VoiceDirectionError(f"{Path(part).name} is empty or compressed")
                if params is not None and current != params:
                    raise VoiceDirectionError(f"{Path(part).name} has different WAV parameters")
                params = current
                frames.append(audio.readframes(audio.getnframes()))
        except wave.Error as exc:
            raise VoiceDirectionError(f"{Path(part).name} is not valid WAV audio") from exc
    assert params is not None
    channels, width, rate = params
    silence = (b"\x80" if width == 1 else b"\x00" * width) * channels * round(gap_sec * rate)
    target = Path(dest)
    temp = target.with_name(target.name + ".tmp")
    with wave.open(str(temp), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(silence.join(frames))
    os.replace(temp, target)
