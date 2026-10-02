"""Dynamic Multi-Channel Prompt & Turn Template Loader.

Parses and strips metadata headers (<<<PROMPT_META_START/END>>>), compiles
fragments and channel configs safely, protects against template injection,
and provides multi-niche channel adaptability without hardcoding single personas.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR: Path = ROOT / "prompts"
FRAGMENTS_DIR: Path = PROMPTS_DIR / "fragments"
TURNS_DIR: Path = PROMPTS_DIR / "turns"
CONFIG_PATH: Path = ROOT / "daheeh_config.json"

_META_START = "<<<PROMPT_META_START>>>"
_META_END = "<<<PROMPT_META_END>>>"

REQUIRED_KEYS = {
    "name",
    "version",
    "role",
    "ack_tokens",
    "xml_tags",
    "calibration",
    "output_schema",
}


class PromptError(ValueError):
    """Raised when a prompt or placeholder resolution fails."""
    pass


@dataclass
class Prompt:
    name: str
    version: str
    role: str
    ack_tokens: list[str] = field(default_factory=list)
    xml_tags: list[str] = field(default_factory=list)
    calibration: str = ""
    output_schema: str = ""
    header: dict[str, str] = field(default_factory=dict)
    body: str = ""


def _resolve_channel_dict(channel: Any | None = None) -> dict[str, Any]:
    if channel is None:
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                return raw.get("al_daheeh_master_pipeline_config", {})
            except Exception:
                return {}
        return {}
    if hasattr(channel, "model_dump"):
        return channel.model_dump()
    if isinstance(channel, dict):
        return channel
    return {}


def config_value(key: str, channel: Any | None = None) -> str:
    cfg = _resolve_channel_dict(channel)
    dp = cfg.get("dialect_profile", {})

    if key == "ratios":
        fusha = round(float(dp.get("fusha_academic_ratio", 0.3)) * 100)
        amiya = round(float(dp.get("cairo_amiya_ratio", 0.7)) * 100)
        return f"{fusha}% Academic Fusha : {amiya}% Cairene Amiya"
    if key == "tashkeel":
        lexicon = dp.get("tashkeel_lexicon", {})
        return "، ".join(lexicon.values())
    raise PromptError(f"Unknown config placeholder: config:{key}")


def fragment(slug: str) -> str:
    path = FRAGMENTS_DIR / f"{slug}.txt"
    if not path.exists():
        raise PromptError(f"Fragment not found: {slug} ({path})")
    return path.read_text(encoding="utf-8").strip()


def fragment_lines(slug: str) -> list[str]:
    return [line.strip() for line in fragment(slug).splitlines() if line.strip()]


def slang_terms(slug: str = "slang_categories") -> list[str]:
    """Flat, whitespace-trimmed slang-term list excluding English category titles."""
    text = fragment(slug)
    terms: list[str] = []
    for group in re.findall(r":\s*\(([^)]+)\)", text):
        terms.extend(t.strip() for t in re.split(r"[،,]", group) if t.strip())
    return terms


def _apply(text: str, vars_: dict[str, Any], channel: Any | None = None) -> str:
    # 1. Resolve fragments first so fragments can contain config directives
    text = re.sub(r"\{fragment:([a-z0-9_]+)\}", lambda m: fragment(m.group(1)), text)

    # 2. Resolve channel-driven config directives
    text = re.sub(r"\{config:([a-z0-9_]+)\}", lambda m: config_value(m.group(1), channel=channel), text)

    # 3. Safe single-pass substitution for vars_ to avoid cascading injection
    if vars_:
        pattern = re.compile(r"\{([a-zA-Z0-9_]+)\}")
        def repl(match: re.Match) -> str:
            k = match.group(1)
            return str(vars_[k]) if k in vars_ else match.group(0)
        text = pattern.sub(repl, text)

    return text


NAME_ALIASES: dict[str, str] = {
    "prompt": "phase1",
    "prompt_phase3": "phase3",
    "refine_prompt": "refine",
    "TTS_PROMPT": "tts",
    "tts_prompt": "tts",
}


def load(name: str) -> Prompt:
    canonical_name = NAME_ALIASES.get(name, name)
    path = PROMPTS_DIR / f"{canonical_name}.txt"
    if not path.exists():
        raise PromptError(f"Prompt file not found: {name} ({path})")
    raw = path.read_text(encoding="utf-8")
    start = raw.find(_META_START)
    end = raw.find(_META_END)
    if start == -1 or end == -1:
        raise PromptError(f"Prompt missing META block: {path.name}")

    header: dict[str, str] = {}
    for line in raw[start + len(_META_START) : end].strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            header[k.strip()] = v.strip()

    missing = REQUIRED_KEYS - header.keys()
    if missing:
        raise PromptError(f"Prompt missing META keys {sorted(missing)}: {path.name}")

    body = raw[end + len(_META_END) :].strip()
    return Prompt(
        name=header["name"],
        version=header["version"],
        role=header["role"],
        ack_tokens=[v.strip() for v in header["ack_tokens"].split("|") if v.strip()],
        xml_tags=[v.strip() for v in header["xml_tags"].split("|") if v.strip()],
        calibration=header["calibration"],
        output_schema=header["output_schema"],
        header=header,
        body=body,
    )


def render(name: str, channel: Any | None = None, **vars_: Any) -> str:
    return _apply(load(name).body, vars_, channel=channel)


def turn(name: str, turn_name: str, channel: Any | None = None, **vars_: Any) -> str:
    canonical_name = NAME_ALIASES.get(name, name)
    path = TURNS_DIR / f"{canonical_name}_{turn_name}.txt"
    if not path.exists():
        raise PromptError(f"Turn template not found: {canonical_name}_{turn_name} ({path})")
    raw = path.read_text(encoding="utf-8").strip()
    start = raw.find(_META_START)
    end = raw.find(_META_END)
    if start != -1 and end != -1:
        raw = raw[end + len(_META_END) :].strip()
    return _apply(raw, vars_, channel=channel)


def ack_tokens(name: str) -> list[str]:
    return load(name).ack_tokens
