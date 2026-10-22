"""Offline restart regressions for chapter-bound TTS spending and uncertain actions."""

import json
import os
import wave
from types import SimpleNamespace

import pytest

from youtube_automation.audio import tts_generator as tg
from youtube_automation.production import voice_direction as vd

FLASH = vd.FLASH_MODEL
FULL_ERROR = "Http response at 400 or 500 level, status code: 0"
PIECE_ERROR = "503 Service Unavailable, try again"
OTHER_ERROR = "504 Gateway Timeout, try again"
SPEECH = vd.SpeechText(
    clean_text="one two\n\nthree four\n\nfive six\n\nseven eight\n\nnine ten",
    directed_text="<sigh> one two\n\nthree four\n\nfive six\n\nseven eight\n\nnine ten",
    paragraph_count=5,
)


def _wav(path, seed):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(seed.to_bytes(2, "little", signed=True) * 2000)
    assert tg.is_valid_wav_file(str(path))


@pytest.fixture
def run_state(tmp_path, monkeypatch):
    monkeypatch.delenv("ADAPTIVE_TTS_PRO_FALLBACK", raising=False)
    monkeypatch.setattr(tg, "sync_audio_manifest", lambda *_a, **_k: None)
    run = tmp_path / "run"
    folder = run / "voice_chapters"
    folder.mkdir(parents=True)
    manifest = {
        "voice_config": {"model": FLASH, "voice": "Charon", "style": "Calm", "temperature": "1"},
        "chapters": [{"chapter_num": 1, "status": "PENDING", "text": " ".join(SPEECH.clean_text.split()),
                      "audio_file": str(folder / "Chapter_1.wav")}],
    }
    return str(run), str(folder), manifest


def _load(run):
    with open(tg.get_manifest_path(run), encoding="utf-8") as stream:
        return json.load(stream)


def _voice(run, folder, manifest, speech=SPEECH, sha="direction-1"):
    tg._adaptive_voice_chapters(
        object(), run, folder, manifest, SimpleNamespace(sha256=sha), {1: speech}, {}
    )


class Transport:
    """The fake provider boundary verifies that its reservation already reached disk."""

    def __init__(self, monkeypatch, run, steps):
        self.run, self.steps, self.calls, self.switches = run, list(steps), [], []
        monkeypatch.setattr(tg, "_adaptive_send_unit", self.send)
        monkeypatch.setattr(tg, "_adaptive_switch_model", lambda _p, opts: self.switches.append(opts["model"]))

    def send(self, _page, text, dest, options, _state, *, recover=False, on_sent=None):
        saved = _load(self.run)["chapters"][0]["tts_attempts"]
        active = [a for unit in saved["units"].values() for a in unit["attempts"]
                  if a["status"] == "IN_FLIGHT"]
        assert len(active) == 1
        self.calls.append((os.path.basename(dest), options["model"], text))
        step = self.steps.pop(0) if self.steps else "ok"
        if isinstance(step, BaseException):
            raise step
        if on_sent is not None:
            on_sent()
        if step != "ok":
            raise tg._adaptive_unit_failure(step, "unknown")
        _wav(dest, 100 + len(self.calls))


def _checkpoint_after_piece(monkeypatch, run, index=1):
    save = tg.save_manifest

    def checkpoint(latest_run, manifest):
        save(latest_run, manifest)
        records = manifest["chapters"][0].get("pieces", [])
        if any(p.get("index") == index and p.get("status") == "COMPLETED" for p in records):
            raise KeyboardInterrupt("after completed piece checkpoint")

    monkeypatch.setattr(tg, "save_manifest", checkpoint)
    return save


def test_full_failure_and_completed_piece_survive_process_reload(run_state, monkeypatch):
    run, folder, manifest = run_state
    transport = Transport(monkeypatch, run, [FULL_ERROR, "ok"])
    save = _checkpoint_after_piece(monkeypatch, run)
    with pytest.raises(KeyboardInterrupt, match="completed piece"):
        _voice(run, folder, manifest)
    first = _load(run)["chapters"][0]["pieces"][0]
    first_bytes = open(os.path.join(run, first["audio_file"]), "rb").read()
    monkeypatch.setattr(tg, "save_manifest", save)
    resumed = _load(run)
    _voice(run, folder, resumed)
    assert [c[0] for c in transport.calls] == [
        "Chapter_1.wav", "Chapter_1_part_1.wav", "Chapter_1_part_2.wav", "Chapter_1_part_3.wav",
    ]
    assert resumed["chapters"][0]["status"] == "COMPLETED"
    assert open(os.path.join(run, first["audio_file"]), "rb").read() == first_bytes
    assert resumed["chapters"][0]["tts_attempts"]["retries_left"] == 1


def test_systematic_signature_survives_restart_without_fresh_attempt(run_state, monkeypatch):
    run, folder, manifest = run_state
    transport = Transport(monkeypatch, run, [FULL_ERROR, FULL_ERROR])
    with pytest.raises(tg.TTSProviderError, match="Pro fallback disabled"):
        _voice(run, folder, manifest)
    state = _load(run)["chapters"][0]["tts_attempts"]
    assert state["retries_left"] == 1  # systematic failure still forbids another action
    assert state["units"]["part_1"]["attempts"][-1]["retry_allowed"] is False
    calls = list(transport.calls)
    with pytest.raises(tg.TTSProviderError, match="Pro fallback disabled"):
        _voice(run, folder, _load(run))
    assert transport.calls == calls


def test_exhausted_retry_persists_and_is_shared_across_pieces(run_state, monkeypatch):
    run, folder, manifest = run_state
    transport = Transport(monkeypatch, run, [FULL_ERROR, PIECE_ERROR, "ok", OTHER_ERROR])
    with pytest.raises(tg.TTSProviderError, match="Pro fallback disabled"):
        _voice(run, folder, manifest)
    state = _load(run)["chapters"][0]["tts_attempts"]
    assert state["retries_left"] == 0
    assert len(state["units"]["part_1"]["attempts"]) == 2
    assert len(state["units"]["part_2"]["attempts"]) == 1
    calls = list(transport.calls)
    with pytest.raises(tg.TTSProviderError, match="Pro fallback disabled"):
        _voice(run, folder, _load(run))
    assert transport.calls == calls


@pytest.mark.parametrize("unit", ["full", "part_1"])
def test_uncertain_reservation_blocks_all_new_browser_actions(run_state, monkeypatch, unit):
    run, folder, manifest = run_state
    steps = [KeyboardInterrupt("interrupted click")] if unit == "full" else [FULL_ERROR, KeyboardInterrupt("interrupted click")]
    transport = Transport(monkeypatch, run, steps)
    with pytest.raises(KeyboardInterrupt, match="interrupted click"):
        _voice(run, folder, manifest)
    saved = _load(run)
    attempt = saved["chapters"][0]["tts_attempts"]["units"][unit]["attempts"][-1]
    assert attempt["status"] == "IN_FLIGHT"
    if unit == "full":
        assert "full_sent" not in saved["chapters"][0]
    calls = list(transport.calls)
    with pytest.raises(tg.TTSProviderError, match="uncertain"):
        _voice(run, folder, saved)
    assert transport.calls == calls and transport.switches == []


def test_crash_before_provider_boundary_keeps_uncertain_reservation(run_state, monkeypatch):
    run, folder, manifest = run_state
    transport = Transport(monkeypatch, run, [])
    attempt = tg._adaptive_attempt
    monkeypatch.setattr(tg, "_adaptive_attempt", lambda *_a, **_k: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        _voice(run, folder, manifest)
    assert transport.calls == []
    monkeypatch.setattr(tg, "_adaptive_attempt", attempt)
    with pytest.raises(tg.TTSProviderError, match="uncertain"):
        _voice(run, folder, _load(run))
    assert transport.calls == []


def test_reservation_write_failure_stops_before_provider_boundary(run_state, monkeypatch):
    run, folder, manifest = run_state
    transport = Transport(monkeypatch, run, [])
    save = tg.save_manifest

    def cannot_reserve(latest_run, current):
        if current["chapters"][0]["tts_attempts"]["units"]:
            raise OSError("cannot reserve")
        save(latest_run, current)

    monkeypatch.setattr(tg, "save_manifest", cannot_reserve)
    with pytest.raises(OSError, match="cannot reserve"):
        _voice(run, folder, manifest)
    assert transport.calls == []


@pytest.mark.parametrize("change", ["speech", "voice", "temperature", "style", "direction"])
def test_recipe_change_cannot_reset_spending(run_state, monkeypatch, change):
    run, folder, manifest = run_state
    transport = Transport(monkeypatch, run, [FULL_ERROR, "ok"])
    save = _checkpoint_after_piece(monkeypatch, run)
    with pytest.raises(KeyboardInterrupt):
        _voice(run, folder, manifest)
    monkeypatch.setattr(tg, "save_manifest", save)
    saved = _load(run)
    speech, sha = SPEECH, "direction-1"
    if change == "speech":
        speech = vd.SpeechText(clean_text=SPEECH.clean_text + " changed", directed_text=SPEECH.directed_text + " changed", paragraph_count=5)
    elif change == "direction":
        sha = "direction-2"
    else:
        saved["voice_config"][change] = "changed"
    calls = list(transport.calls)
    with pytest.raises(ValueError, match="recipe changed"):
        _voice(run, folder, saved, speech=speech, sha=sha)
    assert transport.calls == calls


@pytest.mark.parametrize("change", ["version", "counter", "signature", "status"])
def test_malformed_accounting_fails_closed(run_state, monkeypatch, change):
    run, folder, manifest = run_state
    transport = Transport(monkeypatch, run, [FULL_ERROR, PIECE_ERROR, "ok", OTHER_ERROR])
    with pytest.raises(tg.TTSProviderError):
        _voice(run, folder, manifest)
    saved = _load(run)
    state = saved["chapters"][0]["tts_attempts"]
    if change == "version":
        state["version"] = 2
    elif change == "counter":
        state["retries_left"] = 1
    elif change == "signature":
        state["previous_failure"] = None
    else:
        state["units"]["part_2"]["attempts"][-1]["status"] = "READY"
    calls = list(transport.calls)
    with pytest.raises(ValueError):
        _voice(run, folder, saved)
    assert transport.calls == calls


def test_opted_in_pro_keeps_spent_retry_and_completed_flash_take(run_state, monkeypatch):
    run, folder, manifest = run_state
    transport = Transport(monkeypatch, run, [FULL_ERROR, PIECE_ERROR, "ok", OTHER_ERROR])
    with pytest.raises(tg.TTSProviderError):
        _voice(run, folder, manifest)
    saved = _load(run)
    first = saved["chapters"][0]["pieces"][0]
    first_bytes = open(os.path.join(run, first["audio_file"]), "rb").read()
    monkeypatch.setenv("ADAPTIVE_TTS_PRO_FALLBACK", "1")
    transport.steps = [PIECE_ERROR]
    with pytest.raises(tg.TTSProviderError, match="Pro split failed"):
        _voice(run, folder, saved)
    current = _load(run)["chapters"][0]
    assert current["tts_attempts"]["retries_left"] == 0
    assert len(current["tts_attempts"]["units"]["pro_part_1"]["attempts"]) == 1
    assert first in current["pieces"]
    assert open(os.path.join(run, first["audio_file"]), "rb").read() == first_bytes
    assert transport.switches == [vd.PRO_MODEL]


def test_completed_legacy_take_is_unchanged_and_never_sent(run_state, monkeypatch):
    run, folder, manifest = run_state
    chap = manifest["chapters"][0]
    _wav(chap["audio_file"], 7)
    chap.update(status="COMPLETED", md5=tg.get_file_md5(chap["audio_file"]),
                voice_model=FLASH, voice_direction_sha256="direction-1", voice_tier="flash_full")
    before = json.dumps(manifest, sort_keys=True)
    transport = Transport(monkeypatch, run, [])
    _voice(run, folder, manifest)
    assert json.dumps(manifest, sort_keys=True) == before and transport.calls == []
    assert "tts_attempts" not in chap
