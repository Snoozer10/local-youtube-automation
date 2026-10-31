"""Automated verification suite for channel profiles and contract invariants."""

import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from youtube_automation.production.contracts import Channel, load_channel

CHANNELS_DIR = Path("channels")
CHANNEL_PATHS = sorted(CHANNELS_DIR.glob("*.json"))

CHANNEL_POLICIES = {
    "professor-yashrah": {
        "min_version": 3,
        "voice": "Achird",
        "language": "Arabic",
        "asr_language": "ar",
        "host_mode": "NONE",
    },
    "soldiers-ledger": {
        "min_version": 3,
        "voice": "Charon",
        "language": "English",
        "asr_language": "en",
        "host_mode": "NONE",
    },
    "snoozer-anime": {
        "min_version": 2,
        "voice": None,
        "language": "Arabic",
        "asr_language": "ar",
        "host_mode": "NONE",
    },
}


def _format_pydantic_error(exc: ValidationError, file_path: Path) -> str:
    lines = [f"\nChannel validation failed for '{file_path}':"]
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err["loc"]) or "root"
        lines.append(f"  - Field '{field}': {err['msg']} (input={err.get('input')!r})")
    return "\n".join(lines)


@pytest.mark.unit
def test_channel_directory_discovered():
    assert CHANNELS_DIR.is_dir(), f"Missing directory: {CHANNELS_DIR}"
    assert len(CHANNEL_PATHS) >= 3, f"Expected at least 3 channels, found {len(CHANNEL_PATHS)}"


@pytest.mark.unit
@pytest.mark.parametrize("path", CHANNEL_PATHS, ids=lambda p: p.stem)
def test_channel_file_validity(path: Path):
    try:
        channel = load_channel(path)
    except json.JSONDecodeError as exc:
        pytest.fail(f"Malformed JSON in '{path}': {exc}", pytrace=False)
    except ValidationError as exc:
        pytest.fail(_format_pydantic_error(exc, path), pytrace=False)

    assert channel.channel_id == path.stem, (
        f"File name '{path.name}' must match channel_id '{channel.channel_id}'"
    )


@pytest.mark.unit
@pytest.mark.parametrize("channel_id,policy", CHANNEL_POLICIES.items())
def test_channel_policy_invariants(channel_id: str, policy: dict):
    path = CHANNELS_DIR / f"{channel_id}.json"
    assert path.is_file(), f"Missing required channel profile: {path}"

    channel = load_channel(path)
    assert channel.version >= policy["min_version"]
    assert channel.voice == policy["voice"]
    assert channel.language == policy["language"]
    assert channel.asr_language == policy["asr_language"]
    assert channel.host_mode == policy["host_mode"]


@pytest.mark.unit
@pytest.mark.parametrize("path", CHANNEL_PATHS, ids=lambda p: p.stem)
def test_channel_v2_v3_directive_rigor(path: Path):
    channel = load_channel(path)
    if channel.version >= 2:
        assert 1 <= len(channel.visual_directives) <= 30
        assert 1 <= len(channel.forbidden_motifs) <= 30
        # Casefold uniqueness
        assert len({x.casefold() for x in channel.visual_directives}) == len(channel.visual_directives)
        assert len({x.casefold() for x in channel.forbidden_motifs}) == len(channel.forbidden_motifs)


# Negative Contract Enforcement Tests

@pytest.fixture
def base_channel_payload() -> dict:
    return {
        "version": 1,
        "channel_id": "test-channel",
        "name": "Test Channel",
        "audience": "Audience",
        "language": "English",
        "dialect": "Standard",
        "tone": "Neutral",
        "style": "Clean",
        "allowed_treatments": ["subject_scene"],
        "max_zoom": 1.05,
    }


@pytest.mark.unit
def test_contract_rejects_duplicate_directives_case_insensitive(base_channel_payload):
    base_channel_payload.update({
        "version": 2,
        "visual_directives": ["Tactical Map Vector", "tactical map vector"],
        "forbidden_motifs": ["generic explosion"],
    })
    with pytest.raises(ValidationError, match="Duplicate visual directives"):
        Channel.model_validate(base_channel_payload)


@pytest.mark.unit
def test_contract_rejects_out_of_bounds_zoom(base_channel_payload):
    base_channel_payload["max_zoom"] = 1.25
    with pytest.raises(ValidationError, match="less than or equal to 1.15"):
        Channel.model_validate(base_channel_payload)

    base_channel_payload["max_zoom"] = 0.95
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        Channel.model_validate(base_channel_payload)


@pytest.mark.unit
def test_contract_rejects_invalid_treatment_enum(base_channel_payload):
    base_channel_payload["allowed_treatments"] = ["invalid_treatment_type"]
    with pytest.raises(ValidationError):
        Channel.model_validate(base_channel_payload)


@pytest.mark.unit
def test_contract_rejects_host_treatment_without_custom_avatar(base_channel_payload):
    base_channel_payload["host_mode"] = "NONE"
    base_channel_payload["allowed_treatments"] = ["host"]
    with pytest.raises(ValidationError, match="Host treatment requires CUSTOM_AVATAR"):
        Channel.model_validate(base_channel_payload)


@pytest.mark.unit
def test_contract_rejects_v2_without_directives_or_motifs(base_channel_payload):
    base_channel_payload["version"] = 2
    base_channel_payload["visual_directives"] = []
    base_channel_payload["forbidden_motifs"] = []
    with pytest.raises(ValidationError, match=r"Version 2\+ channels require visual directives and forbidden motifs"):
        Channel.model_validate(base_channel_payload)
