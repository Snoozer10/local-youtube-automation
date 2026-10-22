import json

from youtube_automation.production.briefs import ensure_brief
from youtube_automation.production.contracts import Channel, fingerprint, narration_fingerprint
from youtube_automation.production.narration import prepare_manifest, split_chapters

LF_SCRIPT = "Alpha beta gamma.\n\nDelta epsilon.\n\nZeta eta theta iota."


def _brief(tmp_path):
    channel = Channel(
        channel_id="newline-test",
        name="Newline Test",
        audience="adults",
        language="English",
        dialect="neutral",
        voice="Charon",
        tone="serious",
        style="illustration",
        humor="none",
        allowed_treatments=["subject_scene"],
    )
    (tmp_path / "raw_transcript.txt").write_bytes(LF_SCRIPT.encode("utf-8"))
    analysis = {
        "topics": ["history"],
        "claim_basis": "factual",
        "form": "chronology",
        "proposition": "A journey",
        "narrative_strategy": "Follow events",
        "treatments": ["subject_scene"],
        "rationale": "Chronology",
    }
    return ensure_brief(tmp_path, channel, lambda _: json.dumps(analysis))


def test_lf_recipe_formula_is_unchanged(tmp_path):
    brief = _brief(tmp_path)
    manifest = prepare_manifest(tmp_path, {"voice_config": {"voice": "Charon"}}, brief, LF_SCRIPT)
    assert manifest["adaptive_voice_recipe"] == fingerprint(
        {
            "version": 1,
            "script": LF_SCRIPT,
            "brief": narration_fingerprint(brief),
            "voice": brief.channel.voice,
        }
    )


def test_crlf_script_gives_same_recipe_and_chapters(tmp_path):
    brief = _brief(tmp_path)
    base = {"voice_config": {"voice": "Charon"}}
    lf = prepare_manifest(tmp_path, base, brief, LF_SCRIPT)
    crlf_script = LF_SCRIPT.replace("\n", "\r\n")
    crlf = prepare_manifest(tmp_path, base, brief, crlf_script)
    assert crlf["adaptive_voice_recipe"] == lf["adaptive_voice_recipe"]
    assert crlf["chapters"] == lf["chapters"]


def test_split_chapters_splits_crlf_paragraphs_like_lf(tmp_path):
    lf = split_chapters(tmp_path, LF_SCRIPT, max_words=4)
    crlf = split_chapters(tmp_path, LF_SCRIPT.replace("\n", "\r\n"), max_words=4)
    cr = split_chapters(tmp_path, LF_SCRIPT.replace("\n", "\r"), max_words=4)
    assert len(lf) > 1
    assert crlf == lf
    assert cr == lf
