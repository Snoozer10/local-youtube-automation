"""Voice direction (Style + inline tags) never changes the spoken words of the accepted script."""

import json
import wave

import pytest

from youtube_automation.production import voice_direction as vd
from youtube_automation.production.narration import split_chapters

SCRIPT = (
    "In the Battle off Samar a patrol plane sighted twenty-three warships.\n\n"
    "Awaiting them was Taffy 3 with six escort carriers and three destroyers.\n\n"
    "Outmatched, the escorts laid smoke and launched torpedoes.\n\n"
    "Around 09:15 Admiral Kurita ordered a general recall.\n\n"
    "The withdrawal remains one of the most debated decisions of the war.\n"
)
DIRECTED = [
    "In the Battle off Samar <short pause> a patrol plane sighted twenty-three warships.",
    "Awaiting them was Taffy 3 with six escort carriers and three destroyers.",
    "<breath> Outmatched, the escorts laid smoke and launched torpedoes.",
    "Around 09:15 <long pause> Admiral Kurita ordered a general recall.",
    "The withdrawal remains one of the most debated decisions of the war. <sigh>",
]


def _write(tmp_path, *, script=SCRIPT, paragraphs=None, approved=True, **overrides):
    payload = vd.build_direction(
        script,
        channel_id="soldiers-ledger",
        style="Measured documentary narrator, grave and steady, unhurried pace",
        paragraphs=list(DIRECTED if paragraphs is None else paragraphs),
        approved_by="channel owner" if approved else None,
    )
    payload.update(overrides)
    (tmp_path / vd.DIRECTION_FILE).write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _load(tmp_path, script=SCRIPT):
    return vd.load_voice_direction(tmp_path, script, channel_id="soldiers-ledger")


def test_tag_library_is_the_forty_flash_chips_with_known_levels():
    library = vd.load_tag_library()
    assert len(library) == 40
    assert {"short pause", "long pause", "sigh", "gasp", "throat-clearing"} <= set(library)
    assert {entry["level"] for entry in library.values()} == {
        "recommended",
        "casual",
        "dramatic",
        "avoid",
    }


def test_strip_tags_replaces_known_tags_with_a_space():
    assert vd.strip_tags("Yamato.<sigh> Then <short pause> silence") == "Yamato. Then silence"
    assert vd.strip_tags("word<sigh>word") == "word word"
    assert vd.strip_tags("keep <unknown> as is") == "keep <unknown> as is"


def test_missing_direction_file_returns_none(tmp_path):
    assert _load(tmp_path) is None


def test_approved_direction_loads_and_binds_the_file_bytes(tmp_path):
    _write(tmp_path)
    direction = _load(tmp_path)
    assert direction.model == vd.FLASH_MODEL
    assert direction.style.startswith("Measured documentary")
    assert direction.paragraphs[2].startswith("<breath>")
    raw = (tmp_path / vd.DIRECTION_FILE).read_bytes()
    assert direction.sha256 == vd.hashlib.sha256(raw).hexdigest()


def test_crlf_script_matches_its_lf_direction(tmp_path):
    _write(tmp_path)
    assert _load(tmp_path, SCRIPT.replace("\n", "\r\n")) is not None


def test_trailing_newline_never_changes_the_script_binding(tmp_path):
    _write(tmp_path)  # SCRIPT ends with a newline; the voice stage loads the stripped text
    assert _load(tmp_path, SCRIPT.strip()) is not None
    _write(tmp_path, script=SCRIPT.strip())
    assert _load(tmp_path, SCRIPT + "\n") is not None


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"approved": False}, "not approved"),
        ({"style": "   "}, "Style is required"),
        ({"style": "calm <sigh>"}, "plain text"),
        ({"channel_id": "other"}, "another channel"),
        ({"model": vd.PRO_MODEL}, "must target"),
        ({"script_sha256": "0" * 64}, "different script"),
        ({"version": 2}, "unsupported version"),
    ],
)
def test_invalid_direction_files_fail_closed(tmp_path, kwargs, message):
    approved = kwargs.pop("approved", True)
    _write(tmp_path, approved=approved, **kwargs)
    with pytest.raises(vd.VoiceDirectionError, match=message):
        _load(tmp_path)


def test_a_changed_word_is_rejected_with_its_position(tmp_path):
    changed = list(DIRECTED)
    changed[1] = changed[1].replace("six", "seven")
    _write(tmp_path, paragraphs=changed)
    with pytest.raises(vd.VoiceDirectionError, match="Paragraph 2: .* at word 7"):
        _load(tmp_path)


def test_a_tag_inside_a_word_splits_it_and_is_rejected(tmp_path):
    glued = list(DIRECTED)
    glued[1] = glued[1].replace("Taffy", "Taf<sigh>fy")
    _write(tmp_path, paragraphs=glued)
    with pytest.raises(vd.VoiceDirectionError, match="Paragraph 2: spoken words differ"):
        _load(tmp_path)


def test_a_tag_between_words_without_spaces_is_allowed(tmp_path):
    spaced = list(DIRECTED)
    spaced[1] = spaced[1].replace("escort carriers", "escort<sigh>carriers")
    _write(tmp_path, paragraphs=spaced)
    assert "escort<sigh>carriers" in _load(tmp_path).paragraphs[1]


def test_paragraph_count_must_match(tmp_path):
    _write(tmp_path, paragraphs=DIRECTED[:4])
    with pytest.raises(vd.VoiceDirectionError, match="4 paragraphs, the script has 5"):
        _load(tmp_path)


def test_unknown_and_narrator_unsafe_tags_are_rejected(tmp_path):
    unknown = list(DIRECTED)
    unknown[1] = "<applause> " + unknown[1]
    _write(tmp_path, paragraphs=unknown)
    with pytest.raises(vd.VoiceDirectionError, match="unknown tag <applause>"):
        _load(tmp_path)
    unsafe = list(DIRECTED)
    unsafe[1] = "<cough> " + unsafe[1]
    _write(tmp_path, paragraphs=unsafe)
    with pytest.raises(vd.VoiceDirectionError, match="not for narrators"):
        _load(tmp_path)
    _write(tmp_path, paragraphs=unsafe, allow_tags=["cough"])
    assert _load(tmp_path).paragraphs[1].startswith("<cough>")


def test_tag_density_and_consecutive_caps(tmp_path):
    dense = list(DIRECTED)
    dense[2] = (
        "<breath> Outmatched, <sigh> the escorts <short pause> laid smoke and launched torpedoes."
    )
    _write(tmp_path, paragraphs=dense)
    with pytest.raises(vd.VoiceDirectionError, match="exceeds 1"):
        _load(tmp_path)


def test_chapter_speech_keeps_paragraphs_and_attaches_tags_to_words(tmp_path):
    _write(tmp_path)
    direction = _load(tmp_path)
    chapters = split_chapters(tmp_path, SCRIPT)
    speech = vd.chapter_speech(SCRIPT, chapters, direction)[1]
    assert speech.paragraph_count == 5
    assert speech.clean_text.split() == chapters[0]["text"].split()
    assert vd.strip_tags(speech.directed_text).split() == chapters[0]["text"].split()
    assert speech.directed_text.split("\n\n")[0].startswith(
        "In the Battle off Samar <short pause> a"
    )
    assert speech.directed_text.endswith("of the war. <sigh>")
    plain = vd.chapter_speech(SCRIPT, chapters, None)[1]
    assert plain.directed_text == plain.clean_text


def test_chapter_boundaries_inside_a_paragraph_keep_every_word_once(tmp_path):
    _write(tmp_path)
    direction = _load(tmp_path)
    chapters = split_chapters(tmp_path, SCRIPT, max_words=17)
    speech = vd.chapter_speech(SCRIPT, chapters, direction)
    assert len(speech) == len(chapters) > 2
    joined = " ".join(vd.strip_tags(s.directed_text) for s in speech.values()).split()
    assert joined == SCRIPT.split()


def test_chapter_text_that_drifted_from_the_script_is_rejected(tmp_path):
    chapters = split_chapters(tmp_path, SCRIPT)
    chapters[0]["text"] = chapters[0]["text"].replace("Samar", "Leyte")
    with pytest.raises(vd.VoiceDirectionError, match="Chapter 1 differs"):
        vd.chapter_speech(SCRIPT, chapters, None)


def test_split_pieces_groups_two_paragraphs(tmp_path):
    _write(tmp_path)
    speech = vd.chapter_speech(SCRIPT, split_chapters(tmp_path, SCRIPT), _load(tmp_path))[1]
    pieces = vd.split_pieces(speech, 2)
    assert [p.paragraph_count for p in pieces] == [2, 2, 1]
    assert "\n\n".join(p.directed_text for p in pieces) == speech.directed_text
    three = vd.SpeechText("a\n\nb\n\nc", "a\n\nb\n\nc", 3)
    assert [p.clean_text for p in vd.split_pieces(three)] == ["a\n\nb", "c"]


def _wav(path, frames, rate=24000, width=2):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(b"\x01\x02" * frames if width == 2 else b"\x05" * frames)


def test_concat_wavs_joins_in_order_with_a_paragraph_gap(tmp_path):
    _wav(tmp_path / "a.wav", 100)
    _wav(tmp_path / "b.wav", 50)
    vd.concat_wavs([tmp_path / "a.wav", tmp_path / "b.wav"], tmp_path / "out.wav", gap_sec=0.01)
    with wave.open(str(tmp_path / "out.wav"), "rb") as audio:
        assert audio.getnframes() == 100 + 240 + 50
        data = audio.readframes(audio.getnframes())
    assert data[:4] == b"\x01\x02\x01\x02" and data[200:204] == b"\x00\x00\x00\x00"
    assert not (tmp_path / "out.wav.tmp").exists()


def test_concat_wavs_rejects_mismatched_parameters(tmp_path):
    _wav(tmp_path / "a.wav", 10)
    _wav(tmp_path / "b.wav", 10, rate=48000)
    with pytest.raises(vd.VoiceDirectionError, match="different WAV parameters"):
        vd.concat_wavs([tmp_path / "a.wav", tmp_path / "b.wav"], tmp_path / "out.wav")
    assert not (tmp_path / "out.wav").exists()


def test_model_and_pro_fallback_switches(monkeypatch):
    monkeypatch.delenv("ADAPTIVE_TTS_MODEL", raising=False)
    monkeypatch.delenv("ADAPTIVE_TTS_PRO_FALLBACK", raising=False)
    assert vd.adaptive_tts_model() == vd.FLASH_MODEL
    assert vd.pro_fallback_enabled() is False
    monkeypatch.setenv("ADAPTIVE_TTS_MODEL", vd.PRO_MODEL)
    monkeypatch.setenv("ADAPTIVE_TTS_PRO_FALLBACK", "1")
    assert vd.adaptive_tts_model() == vd.PRO_MODEL
    assert vd.pro_fallback_enabled() is True
    monkeypatch.setenv("ADAPTIVE_TTS_MODEL", "gemini-9-tts")
    with pytest.raises(vd.VoiceDirectionError, match="ADAPTIVE_TTS_MODEL"):
        vd.adaptive_tts_model()
