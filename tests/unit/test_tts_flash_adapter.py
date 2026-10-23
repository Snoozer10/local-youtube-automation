"""Offline tests for the adaptive Gemini 3.8 Flash TTS adapter and its tiered fallback."""

from __future__ import annotations

import json
import os
import wave
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from youtube_automation.audio import tts_generator as tg
from youtube_automation.production import contracts, narration, voice_direction, writing

FLASH = voice_direction.FLASH_MODEL
PRO = voice_direction.PRO_MODEL
SPEECH_URL = f"https://aistudio.google.com/generate-speech?model={FLASH}"
VOICE_CARD = "mat-dialog-container div.voice-card[data-voice-name='Charon']"
VOICE_OPTION = f"{VOICE_CARD} button.voice-card-content"
VOICE_SELECTED = "mat-dialog-container div.voice-card.selected[data-voice-name='Charon']"
RUN_SELECTOR = "button[type='submit'], button:has-text('Run')"


# --- fake Playwright surface ----------------------------------------------------------------------
class FakeElement:
    def __init__(self, page, name, *, text="", attrs=None, on_click=None, on_fill=None):
        self.page, self.name, self.text = page, name, text
        self.attrs = dict(attrs or {})
        self.on_click, self.on_fill, self.value = on_click, on_fill, ""

    def is_visible(self):
        return True

    def inner_text(self, timeout=None):
        return self.text

    def get_attribute(self, name, timeout=None):
        return self.attrs.get(name)

    def click(self, timeout=None):
        self.page.events.append(("click", self.name))
        if self.on_click:
            self.on_click()

    def fill(self, value, timeout=None):
        self.page.events.append(("fill", self.name, value))
        self.value = value
        if self.on_fill:
            self.on_fill(value)

    def wait_for(self, state=None, timeout=None):
        return None

    def input_value(self, timeout=None):
        return self.value

    def is_enabled(self, timeout=None):
        return self.attrs.get("enabled", True)


class _Missing:
    def is_visible(self):
        return False

    def wait_for(self, state=None, timeout=None):
        raise TimeoutError("missing")


class FakeLocator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    def _items(self):
        return list(self.page.elements.get(self.selector, []))

    def all(self):
        return self._items()

    def count(self):
        return len(self._items())

    def nth(self, index):
        return self._items()[index]

    @property
    def first(self):
        items = self._items()
        return items[0] if items else _Missing()

    def all_text_contents(self):
        return [item.text for item in self._items()]

    def is_visible(self):
        return bool(self._items())


class FakePage:
    def __init__(self, url=SPEECH_URL):
        self.url = url
        self.elements: dict[str, list[FakeElement]] = {}
        self.events: list[tuple] = []
        self.keyboard = SimpleNamespace(press=lambda key: self.events.append(("key", key)))

    def add(self, selector, name=None, **kwargs):
        element = FakeElement(self, name or selector, **kwargs)
        self.elements.setdefault(selector, []).append(element)
        return element

    def remove(self, selector):
        self.elements.pop(selector, None)

    def locator(self, selector):
        return FakeLocator(self, selector)

    def wait_for_timeout(self, ms):
        return None

    def bring_to_front(self):
        self.events.append(("front",))


def _fast_ui(monkeypatch):
    monkeypatch.setattr(tg, "_TTS_UI_WAIT_SEC", 1.0)
    monkeypatch.setattr(tg, "_TTS_VOICE_SEARCH_WAIT_SEC", 0.5)


def write_wav(path, seed):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(bytes([seed % 256, (seed * 7 + 3) % 256]) * 2000)


# --- editor readiness, voice search, Style --------------------------------------------------------
def test_flash_editor_is_ready_without_text_toggle(monkeypatch):
    _fast_ui(monkeypatch)
    page = FakePage()
    page.add(tg._TTS_FLASH_PROMPT_SELECTOR)
    page.add(tg._TTS_MODEL_CARD_SELECTOR, text=FLASH)
    tg._open_tts_editor(page, FLASH)  # returns: no Text toggle needed on Flash
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match="did not finish loading"):
        tg._open_tts_editor(page, PRO)


def test_pro_editor_readiness_still_needs_text_toggle(monkeypatch):
    _fast_ui(monkeypatch)
    page = FakePage(SPEECH_URL.replace(FLASH, PRO))
    page.add(tg._TTS_MODEL_CARD_SELECTOR, text=PRO)
    with pytest.raises(tg.TTSWorkspaceUnavailableError):
        tg._open_tts_editor(page, PRO)
    page.add(tg._TTS_TEXT_TOGGLE_SELECTOR, text="edit_note Text")
    tg._open_tts_editor(page, PRO)
    tg._open_tts_editor(page)


def test_voice_search_fills_name_when_card_is_hidden(monkeypatch):
    _fast_ui(monkeypatch)
    page = FakePage()
    name = page.add(tg._TTS_VOICE_NAME_SELECTOR, text="Fola")

    def close():
        page.remove(VOICE_SELECTED)
        name.text = "Charon"

    def search(value):
        if value == "Charon":
            page.add(VOICE_OPTION, on_click=lambda: page.add(VOICE_SELECTED))

    def open_dialog():
        page.add(tg._TTS_VOICE_SEARCH_SELECTOR, name="search", on_fill=search)
        page.add(tg._TTS_VOICE_CLOSE_SELECTOR, name="close", on_click=close)

    page.add(tg._TTS_VOICE_OPEN_SELECTOR, name="open", on_click=open_dialog)
    tg._select_tts_voice(page, "Charon", FLASH)
    assert ("fill", "search", "Charon") in page.events
    assert name.text == "Charon"


def test_pro_voice_selection_never_uses_the_search_box(monkeypatch):
    _fast_ui(monkeypatch)
    page = FakePage()
    page.add(tg._TTS_VOICE_NAME_SELECTOR, text="Fola")
    page.add(tg._TTS_VOICE_OPEN_SELECTOR, name="open", on_click=lambda: page.add(
        tg._TTS_VOICE_SEARCH_SELECTOR, name="search"
    ))
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match="did not offer voice"):
        tg._select_tts_voice(page, "Charon", PRO)
    assert not any(event[0] == "fill" for event in page.events)


def _style_page(readback=None):
    page = FakePage()
    button = page.add(tg._TTS_STYLE_BUTTON_SELECTOR, name="style", attrs={"title": "Style"})
    label = page.add(tg._TTS_STYLE_LABEL_SELECTOR, text="Style")

    def close():
        page.remove(tg._TTS_OVERLAY_BACKDROP_SELECTOR)
        page.remove(tg._TTS_STYLE_TEXTAREA_SELECTOR)
        shown = readback if readback is not None else box.value
        button.attrs["title"] = shown
        label.text = shown

    def open_menu():
        nonlocal box
        box = page.add(tg._TTS_STYLE_TEXTAREA_SELECTOR, name="style-box")
        page.add(tg._TTS_OVERLAY_BACKDROP_SELECTOR, name="backdrop", on_click=close)

    box = None
    button.on_click = open_menu
    return page, button


def test_style_is_filled_closed_by_backdrop_and_read_back(monkeypatch):
    _fast_ui(monkeypatch)
    page, button = _style_page()
    tg._set_tts_style(page, "Calm, warm documentary narrator")
    assert page.events == [
        ("click", "style"),
        ("fill", "style-box", "Calm, warm documentary narrator"),
        ("click", "backdrop"),
    ]
    assert not any(event[0] == "key" for event in page.events)
    tg._require_tts_style_title(page, "Calm, warm documentary narrator")
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match="Style is not verified"):
        tg._require_tts_style_title(page, "Another style")


def test_style_mismatch_and_empty_style_fail_closed(monkeypatch):
    _fast_ui(monkeypatch)
    page, _button = _style_page(readback="Calm, warm docu…")
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match="Style is not verified"):
        tg._set_tts_style(page, "Calm, warm documentary narrator")
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match="nonempty Style"):
        tg._set_tts_style(FakePage(), "  ")


# --- one adaptive send: ordering, quota, banner ---------------------------------------------------
def _send_page(tmp_path, monkeypatch, *, stop_ok=True, banner=None):
    page = FakePage()
    events = page.events
    page.add(RUN_SELECTOR, name="run")
    page.add(tg._ADAPTIVE_DOWNLOAD_SELECTOR, name="download")
    page.add(tg._TTS_TEMPERATURE_SELECTOR, name="temperature").value = "1"

    def wait_for_selector(selector, timeout=None):
        if "Stop" in selector and not stop_ok:
            raise TimeoutError("no stop")

    @contextmanager
    def expect_download(timeout=None):
        holder = SimpleNamespace()
        yield holder
        holder.value = SimpleNamespace(save_as=lambda dest: write_wav(dest, 11))

    page.wait_for_selector = wait_for_selector
    page.expect_download = expect_download
    page.reload = lambda **_k: events.append(("reload",))

    def reapply(p, options):
        events.append(("reapply", options.get("style")))
        p.add(tg._tts_prompt_selector(options["model"]), name="prompt")

    monkeypatch.setattr(tg, "reapply_speech_settings", reapply)
    monkeypatch.setattr(tg, "_require_speech_workspace", lambda *_a, **_k: None)
    monkeypatch.setattr(
        tg.network_health, "require_healthy", lambda *_a, **_k: events.append(("network",))
    )
    monkeypatch.setattr(
        tg,
        "_require_current_tts_settings",
        lambda _p, model, voice, *, style=None: events.append(("verify", model, voice, style)),
    )
    def type_text(_p, box, text):
        events.append(("type", box.name, text))
        box.value = text
        return True

    monkeypatch.setattr(tg, "humanize_text_input", type_text)

    monkeypatch.setattr(tg.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(
        tg, "check_ai_studio_errors", lambda _p: (banner is not None, banner or "")
    )
    return page


def test_settings_precede_typing_and_run_is_the_only_click_after_typing(tmp_path, monkeypatch):
    page = _send_page(tmp_path, monkeypatch)
    dest = str(tmp_path / "Chapter_1.wav")
    options = {"model": FLASH, "voice": "Charon", "style": "Calm", "temperature": "1"}
    tg._adaptive_send_unit(page, "<sigh> Hello there.", dest, options, {"is_403": False})
    names = [event[0] for event in page.events]
    typed = names.index("type")
    run = page.events.index(("click", "run"))
    assert names.index("reapply") < names.index("network") < names.index("verify") < typed
    assert names.index("front") < typed
    assert all(name == "verify" for name in names[typed + 1 : run])
    assert page.events[typed] == ("type", "prompt", "<sigh> Hello there.")
    assert ("verify", FLASH, "Charon", "Calm") in page.events
    assert not any(event[0] == "key" for event in page.events)  # never Control+Enter
    assert tg.is_valid_wav_file(dest)


def test_full_chapter_banner_is_a_unit_failure_and_quota_stops(tmp_path, monkeypatch):
    options = {"model": FLASH, "voice": "Charon", "style": "Calm", "temperature": "1"}
    banner = "Failed to generate content: Http response at 400 or 500 level, status code: 0"
    page = _send_page(tmp_path, monkeypatch, stop_ok=False, banner=banner)
    with pytest.raises(tg._TTSUnitFailure) as failure:
        tg._adaptive_send_unit(page, "text", str(tmp_path / "a.wav"), options, {})
    assert failure.value.kind == "transient"

    page = _send_page(tmp_path, monkeypatch, stop_ok=False, banner="Quota exceeded for model")
    with pytest.raises(tg.TTSProviderError, match="quota"):
        tg._adaptive_send_unit(page, "text", str(tmp_path / "b.wav"), options, {})
    assert [event for event in page.events if event[0] == "type"] == [("type", "prompt", "text")]


# --- chapter tiers --------------------------------------------------------------------------------
SPEECH = voice_direction.SpeechText(
    clean_text="one two\n\nthree four\n\nfive six",
    directed_text="<sigh> one two\n\nthree four\n\nfive <laugh> six",
    paragraph_count=3,
)


def _chapter_run(tmp_path, model=FLASH, **chapter):
    run = tmp_path / "run"
    voice_folder = run / "voice_chapters"
    voice_folder.mkdir(parents=True)
    chap = {
        "chapter_num": 1,
        "text": "one two three four five six",
        "audio_file": str(voice_folder / "Chapter_1.wav"),
        "status": "PENDING",
        **chapter,
    }
    config = {"voice": "Charon", "model": model, "temperature": "1"}
    if model == FLASH:
        config["style"] = "Calm"
    manifest = {"voice_config": config, "chapters": [chap]}
    return str(run), str(voice_folder), manifest


class ScriptedSends:
    """Replaces one browser send: each step is "ok", an error string, or an exception."""

    def __init__(self, monkeypatch, steps):
        self.steps, self.calls, self.seed = list(steps), [], 100
        monkeypatch.setattr(tg, "_adaptive_send_unit", self)
        monkeypatch.setattr(tg, "_adaptive_switch_model", self.switch)
        self.switches = []

    def switch(self, _page, options):
        self.switches.append(options["model"])

    def __call__(self, _page, text, dest, options, _state, *, recover=False, on_sent=None):
        self.calls.append((text, os.path.basename(dest), options["model"], options.get("style")))
        if on_sent is not None:
            on_sent()  # the real send calls it right after the Run click returns
        step = self.steps.pop(0) if self.steps else "ok"
        if isinstance(step, BaseException):
            raise step
        if step != "ok":
            raise tg._adaptive_unit_failure(step, "unknown")
        self.seed += 1
        write_wav(dest, self.seed)


def _voice(run, voice_folder, manifest, direction_sha="sha-1"):
    direction = SimpleNamespace(sha256=direction_sha) if direction_sha else None
    tg._adaptive_voice_chapters(
        FakePage(), run, voice_folder, manifest, direction, {1: SPEECH}, {"is_403": False}
    )


def test_flash_full_send_types_directed_text_and_records_metadata(tmp_path, monkeypatch):
    run, voice_folder, manifest = _chapter_run(tmp_path)
    sends = ScriptedSends(monkeypatch, ["ok"])
    _voice(run, voice_folder, manifest)
    assert sends.calls == [(SPEECH.directed_text, "Chapter_1.wav", FLASH, "Calm")]
    chap = manifest["chapters"][0]
    assert chap["status"] == "COMPLETED" and len(chap["md5"]) == 32
    assert (chap["voice_model"], chap["voice_direction_sha256"], chap["voice_tier"]) == (
        FLASH, "sha-1", "flash_full"
    )


def test_pro_send_types_clean_text_without_style(tmp_path, monkeypatch):
    run, voice_folder, manifest = _chapter_run(tmp_path, model=PRO)
    sends = ScriptedSends(monkeypatch, ["ok"])
    _voice(run, voice_folder, manifest, direction_sha=None)
    assert sends.calls == [(SPEECH.clean_text, "Chapter_1.wav", PRO, None)]
    assert manifest["chapters"][0]["voice_tier"] == "pro_full"


BANNER = "Http response at 400 or 500 level, status code: 0"


def test_full_chapter_failure_splits_without_resending_full(tmp_path, monkeypatch):
    run, voice_folder, manifest = _chapter_run(tmp_path)
    sends = ScriptedSends(monkeypatch, [BANNER, "ok", "ok"])
    _voice(run, voice_folder, manifest)
    pieces = voice_direction.split_pieces(SPEECH, 2)
    assert [call[:2] for call in sends.calls] == [
        (SPEECH.directed_text, "Chapter_1.wav"),
        (pieces[0].directed_text, "Chapter_1_part_1.wav"),
        (pieces[1].directed_text, "Chapter_1_part_2.wav"),
    ]
    chap = manifest["chapters"][0]
    assert chap["status"] == "COMPLETED" and chap["voice_tier"] == "flash_split"
    assert [(p["index"], p["status"]) for p in chap["pieces"]] == [(1, "COMPLETED"), (2, "COMPLETED")]
    assert chap["pieces"][0]["audio_file"] == "voice_chapters/parts/Chapter_1_part_1.wav"
    assert tg.is_valid_wav_file(os.path.join(voice_folder, "Chapter_1.wav"))
    saved = json.loads(open(tg.get_manifest_path(run), encoding="utf-8").read())
    assert saved["chapters"][0]["status"] == "COMPLETED"


def test_resume_never_resends_a_completed_piece(tmp_path, monkeypatch):
    run, voice_folder, manifest = _chapter_run(tmp_path)
    part = os.path.join(voice_folder, "parts", "Chapter_1_part_1.wav")
    write_wav(part, 7)
    manifest["chapters"][0].update(
        voice_tier="flash_split", voice_model=FLASH, voice_direction_sha256="sha-1",
        pieces=[{"index": 1, "audio_file": "voice_chapters/parts/Chapter_1_part_1.wav",
                 "md5": tg.get_file_md5(part), "status": "COMPLETED"}],
    )
    sends = ScriptedSends(monkeypatch, ["ok"])
    # Historical incomplete sends have no provable retry entitlement; preserve the take.
    before = open(part, "rb").read()
    with pytest.raises(ValueError, match="incomplete legacy sends"):
        _voice(run, voice_folder, manifest)
    assert sends.calls == []
    assert open(part, "rb").read() == before
    assert manifest["chapters"][0]["status"] == "PENDING"


def test_changed_completed_piece_fails_closed(tmp_path, monkeypatch):
    run, voice_folder, manifest = _chapter_run(tmp_path)
    manifest["chapters"][0].update(
        voice_tier="flash_split", voice_model=FLASH, voice_direction_sha256="sha-1",
        pieces=[{"index": 1, "audio_file": "x", "md5": "0" * 32, "status": "COMPLETED"}],
    )
    sends = ScriptedSends(monkeypatch, [])
    with pytest.raises(ValueError, match="incomplete legacy sends"):
        _voice(run, voice_folder, manifest)
    assert sends.calls == []


def test_same_piece_error_twice_stops_when_pro_fallback_is_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("ADAPTIVE_TTS_PRO_FALLBACK", raising=False)
    run, voice_folder, manifest = _chapter_run(tmp_path)
    sends = ScriptedSends(monkeypatch, [BANNER, BANNER, BANNER])
    with pytest.raises(tg.TTSProviderError, match="Pro fallback disabled"):
        _voice(run, voice_folder, manifest)
    # The full send's error repeats on piece 1: systematic, so exactly two sends.
    assert [call[1] for call in sends.calls] == ["Chapter_1.wav", "Chapter_1_part_1.wav"]
    assert manifest["chapters"][0]["status"] == "PENDING"


def test_different_transient_errors_retry_the_same_piece(tmp_path, monkeypatch):
    run, voice_folder, manifest = _chapter_run(tmp_path)
    sends = ScriptedSends(monkeypatch, [BANNER, "503 Service Unavailable, try again", "ok", "ok"])
    _voice(run, voice_folder, manifest)
    assert [call[1] for call in sends.calls] == [
        "Chapter_1.wav", "Chapter_1_part_1.wav", "Chapter_1_part_1.wav", "Chapter_1_part_2.wav",
    ]


def test_retry_budget_is_one_per_chapter(tmp_path, monkeypatch):
    monkeypatch.delenv("ADAPTIVE_TTS_PRO_FALLBACK", raising=False)
    run, voice_folder, manifest = _chapter_run(tmp_path)
    sends = ScriptedSends(monkeypatch, [BANNER, "503 Service Unavailable, try again", "ok", BANNER])
    with pytest.raises(tg.TTSProviderError, match="Pro fallback disabled"):
        _voice(run, voice_folder, manifest)
    assert [call[1] for call in sends.calls] == [
        "Chapter_1.wav", "Chapter_1_part_1.wav", "Chapter_1_part_1.wav", "Chapter_1_part_2.wav",
    ]
    assert tg._TTS_UNIT_ATTEMPT_LIMIT == 2


def _speech(paragraphs):
    words = [f"w{i} v{i}" for i in range(paragraphs)]
    return voice_direction.SpeechText(
        clean_text="\n\n".join(words),
        directed_text="\n\n".join(f"<sigh> {w}" for w in words),
        paragraph_count=paragraphs,
    )


@pytest.mark.parametrize(("paragraphs", "cap"), [(5, 5), (3, 4)])
def test_worst_case_sends_per_chapter_stay_within_the_cap(tmp_path, monkeypatch, paragraphs, cap):
    """Every outcome sequence (ok / two transient errors / one other error) stays in the cap."""
    import itertools

    monkeypatch.delenv("ADAPTIVE_TTS_PRO_FALLBACK", raising=False)
    monkeypatch.setattr(tg, "save_manifest", lambda *_a: None)
    monkeypatch.setattr(tg, "sync_audio_manifest", lambda *_a, **_k: None)
    outcomes = ["ok", BANNER, "503 Service Unavailable, try again", "Something odd"]
    speech = _speech(paragraphs)
    worst = 0
    # Steps past the list default to "ok", so any send beyond the cap is still counted.
    for index, steps in enumerate(itertools.product(outcomes, repeat=cap)):
        run, voice_folder, manifest = _chapter_run(tmp_path / str(index))
        sends = ScriptedSends(monkeypatch, list(steps))
        try:
            tg._adaptive_voice_chapters(
                FakePage(), run, voice_folder, manifest, SimpleNamespace(sha256="sha-1"),
                {1: speech}, {"is_403": False},
            )
        except tg.TTSProviderError:
            pass
        worst = max(worst, len(sends.calls))
        assert len(sends.calls) <= cap, steps
    assert worst == cap


def test_systematic_piece_failure_uses_pro_split_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ADAPTIVE_TTS_PRO_FALLBACK", "1")
    run, voice_folder, manifest = _chapter_run(tmp_path)
    sends = ScriptedSends(monkeypatch, [BANNER, BANNER, BANNER, "ok", "ok"])
    _voice(run, voice_folder, manifest)
    pieces = voice_direction.split_pieces(SPEECH, 2)
    assert sends.calls[-2:] == [
        (pieces[0].clean_text, "Chapter_1_pro_part_1.wav", PRO, None),
        (pieces[1].clean_text, "Chapter_1_pro_part_2.wav", PRO, None),
    ]
    assert sends.switches == [PRO]
    chap = manifest["chapters"][0]
    assert (chap["voice_tier"], chap["voice_model"], chap["status"]) == (
        "pro_split", PRO, "COMPLETED"
    )


def test_quota_error_stops_immediately_without_escalation(tmp_path, monkeypatch):
    run, voice_folder, manifest = _chapter_run(tmp_path)
    sends = ScriptedSends(monkeypatch, ["You exceeded your current quota (429)"])
    with pytest.raises(tg.TTSProviderError, match="quota"):
        _voice(run, voice_folder, manifest)
    assert len(sends.calls) == 1
    assert "pieces" not in manifest["chapters"][0]


def test_duplicate_piece_audio_is_a_failure(tmp_path, monkeypatch):
    dest = tmp_path / "parts" / "p.wav"
    session = {"page_model": FLASH, "dirty": False, "sends": 0}

    def send(_page, _text, path, _options, _state, *, recover=False):
        write_wav(path, 5)

    monkeypatch.setattr(tg, "_adaptive_send_unit", send)
    write_wav(tmp_path / "earlier.wav", 5)
    earlier = tg.get_file_md5(str(tmp_path / "earlier.wav"))
    with pytest.raises(tg._TTSUnitFailure, match="duplicate"):
        tg._adaptive_attempt(None, "t", str(dest), {"model": FLASH}, {}, {earlier}, session)
    assert not dest.exists()


# --- model/direction gates before any browser work ------------------------------------------------
def test_completed_chapter_metadata_mismatch_fails_closed():
    chapters = [
        {"chapter_num": 1, "status": "COMPLETED"},  # legacy: no metadata, accepted
        {"chapter_num": 2, "status": "COMPLETED", "voice_model": FLASH,
         "voice_direction_sha256": "sha-1", "voice_tier": "flash_full"},
        {"chapter_num": 3, "status": "COMPLETED", "voice_model": PRO,
         "voice_direction_sha256": "sha-1", "voice_tier": "pro_split"},
    ]
    tagged = chapters[1:]
    tg._require_adaptive_voice_metadata({"chapters": tagged}, FLASH, "sha-1", PRO)
    with pytest.raises(ValueError, match="synthesized with"):
        tg._require_adaptive_voice_metadata({"chapters": tagged}, FLASH, "sha-2", PRO)
    with pytest.raises(ValueError, match="synthesized with"):
        tg._require_adaptive_voice_metadata({"chapters": tagged}, PRO, "sha-1", PRO)
    # Legacy (no metadata) audio is Pro audio: accepted on a Pro run, never stitched into Flash.
    tg._require_adaptive_voice_metadata({"chapters": chapters[:1]}, PRO, None, PRO)
    with pytest.raises(ValueError, match="without voice_model metadata"):
        tg._require_adaptive_voice_metadata({"chapters": chapters}, FLASH, "sha-1", PRO)
    pending = [{"chapter_num": 1, "status": "PENDING"}]
    tg._require_adaptive_voice_metadata({"chapters": pending}, FLASH, "sha-1", PRO)


SCRIPT = "First paragraph words here.\n\nSecond paragraph words here."


def _adaptive_run(tmp_path, monkeypatch, manifest_chapters=None):
    run = tmp_path / "run"
    run.mkdir()
    (run / "episode_brief.json").write_text("{}", encoding="utf-8")
    (run / "refined_script.txt").write_text(SCRIPT, encoding="utf-8")
    brief = SimpleNamespace(channel=SimpleNamespace(voice="Charon", channel_id="chan"))
    monkeypatch.setattr(tg.sys, "argv", ["generate_voice.py", str(run)])
    monkeypatch.setattr(writing, "verify_written_episode", lambda *_a: None)
    monkeypatch.setattr(contracts, "load_brief", lambda *_a: brief)
    monkeypatch.setattr(narration, "require_unpolished_run", lambda *_a: None)

    def prepare(run_dir, manifest, _brief, script):
        updated = dict(manifest)
        updated["chapters"] = manifest_chapters or narration.split_chapters(run_dir, script)
        updated["gemini_completed"] = True
        return updated

    monkeypatch.setattr(narration, "prepare_manifest", prepare)
    monkeypatch.setattr(
        tg, "read_voice_options", lambda: {"model": PRO, "temperature": "1", "voice": "Achird"}
    )

    def no_browser():
        raise AssertionError("browser work started")

    monkeypatch.setattr(tg, "sync_playwright", no_browser)
    return run


def test_flash_without_direction_raises_before_browser_work(tmp_path, monkeypatch):
    monkeypatch.delenv("ADAPTIVE_TTS_MODEL", raising=False)
    _adaptive_run(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="requires an approved voice_direction.json"):
        tg._run_voice_generation()


def test_flash_direction_sets_model_and_style_before_browser_work(tmp_path, monkeypatch):
    monkeypatch.delenv("ADAPTIVE_TTS_MODEL", raising=False)
    run = _adaptive_run(tmp_path, monkeypatch)
    payload = voice_direction.build_direction(
        SCRIPT,
        channel_id="chan",
        style="Calm documentary narrator",
        paragraphs=["<sigh> First paragraph words here.", "Second paragraph words here."],
        approved_by="tester",
    )
    (run / voice_direction.DIRECTION_FILE).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AssertionError, match="browser work started"):
        tg._run_voice_generation()
    saved = json.loads((run / tg.MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
    assert saved["voice_config"]["model"] == FLASH
    assert saved["voice_config"]["style"] == "Calm documentary narrator"


def test_completed_chapter_from_another_model_raises_before_browser_work(tmp_path, monkeypatch):
    monkeypatch.setenv("ADAPTIVE_TTS_MODEL", PRO)
    chapters = [
        {"chapter_num": 1, "text": " ".join(SCRIPT.split()), "audio_file": "x.wav",
         "status": "COMPLETED", "voice_model": FLASH, "voice_direction_sha256": "old",
         "voice_tier": "flash_full"},
    ]
    _adaptive_run(tmp_path, monkeypatch, manifest_chapters=chapters)
    with pytest.raises(ValueError, match="synthesized with"):
        tg._run_voice_generation()


def test_flash_brief_without_channel_id_raises_value_error_before_loading(tmp_path, monkeypatch):
    monkeypatch.delenv("ADAPTIVE_TTS_MODEL", raising=False)
    for channel in (SimpleNamespace(voice="Charon"), None, SimpleNamespace(channel_id="  ")):
        with pytest.raises(ValueError, match="channel id"):
            tg._prepare_adaptive_voice(
                str(tmp_path), {"chapters": []}, SimpleNamespace(channel=channel), SCRIPT
            )


# --- Flash-path safety guards through the real read-only gates ------------------------------------
FLASH_OPTIONS = {"model": FLASH, "voice": "Charon", "style": "Calm", "temperature": "1"}


def _guarded_flash_page(monkeypatch, *, on_type=None, on_run=None):
    """Flash speech page for the real _adaptive_send_unit gates; only typing and clicks are fakes."""
    page = FakePage()
    page.add("ms-run-settings")
    page.add(tg._TTS_MODEL_CARD_SELECTOR, name="card", text=FLASH)
    page.add(tg._TTS_VOICE_NAME_SELECTOR, name="voice", text="Charon")
    page.add(tg._TTS_STYLE_BUTTON_SELECTOR, name="style", attrs={"title": "Calm"})
    page.add(tg._TTS_FLASH_PROMPT_SELECTOR, name="prompt")
    page.add(RUN_SELECTOR, name="run")
    page.add(tg._TTS_TEMPERATURE_SELECTOR, name="temperature").value = "1"
    page.reload = lambda **_k: page.events.append(("reload",))

    def no_wait(*_args, **_kwargs):
        raise AssertionError("Run was clicked")

    page.wait_for_selector = no_wait
    monkeypatch.setattr(tg, "reapply_speech_settings", lambda *_a: pytest.fail("no reapply"))
    monkeypatch.setattr(tg.network_health, "require_healthy", lambda *_a, **_k: None)
    monkeypatch.setattr(tg.time, "sleep", lambda *_a: None)

    def type_text(p, box, text):
        p.events.append(("type", box.name, text))
        box.value = text
        result = on_type(p) if on_type else None
        return True if result is None else result

    monkeypatch.setattr(tg, "humanize_text_input", type_text)
    if on_run:
        page.elements[RUN_SELECTOR][0].on_click = lambda: on_run(page)
    return page


def _typed(page):
    return [event for event in page.events if event[0] == "type"]


def _runs(page):
    return [event for event in page.events if event == ("click", "run")]


def _no_keys(page):
    return not any(event[0] == "key" for event in page.events)


@pytest.mark.parametrize(
    "url",
    [
        "https://aistudio.google.com/prompts/abc",
        f"https://evil.example/generate-speech?model={FLASH}",
        f"https://aistudio.google.com/generate-speech-old?model={FLASH}",
    ],
)
def test_flash_send_on_a_non_speech_page_never_types_or_runs(tmp_path, monkeypatch, url):
    page = _guarded_flash_page(monkeypatch)
    page.url = url
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match="Speech Playground is unavailable"):
        tg._adaptive_send_unit(page, "<sigh> hi", str(tmp_path / "a.wav"), FLASH_OPTIONS, {})
    assert _typed(page) == [] and _runs(page) == [] and _no_keys(page)


@pytest.mark.parametrize("phase", ["before_fill", "after_fill"])
@pytest.mark.parametrize("cards", [[PRO], ["gemini-3.8-flash"], [FLASH, FLASH], []])
def test_flash_model_card_mismatch_blocks_fill_or_run(tmp_path, monkeypatch, phase, cards):
    def switch(p):
        p.remove(tg._TTS_MODEL_CARD_SELECTOR)
        for name in cards:
            p.add(tg._TTS_MODEL_CARD_SELECTOR, name="card", text=name)

    page = _guarded_flash_page(monkeypatch, on_type=switch if phase == "after_fill" else None)
    if phase == "before_fill":
        switch(page)
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match="model"):
        tg._adaptive_send_unit(page, "<sigh> hi", str(tmp_path / "a.wav"), FLASH_OPTIONS, {})
    assert len(_typed(page)) == int(phase == "after_fill")
    assert _runs(page) == [] and _no_keys(page)


@pytest.mark.parametrize("phase", ["before_fill", "after_fill"])
@pytest.mark.parametrize("field", ["voice", "Style"])
def test_flash_voice_or_style_drift_blocks_fill_or_run(tmp_path, monkeypatch, phase, field):
    def drift(p):
        if field == "voice":
            p.elements[tg._TTS_VOICE_NAME_SELECTOR][0].text = "Fola"
        else:
            p.elements[tg._TTS_STYLE_BUTTON_SELECTOR][0].attrs["title"] = "Shouting"

    page = _guarded_flash_page(monkeypatch, on_type=drift if phase == "after_fill" else None)
    if phase == "before_fill":
        drift(page)
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match=f"TTS {field} "):
        tg._adaptive_send_unit(page, "<sigh> hi", str(tmp_path / "a.wav"), FLASH_OPTIONS, {})
    assert len(_typed(page)) == int(phase == "after_fill")
    assert _runs(page) == [] and _no_keys(page)


@pytest.mark.parametrize("phase", ["typing", "run_click", "gate_after_typing"])
def test_flash_guard_error_propagates_without_split_or_fallback(tmp_path, monkeypatch, phase):
    monkeypatch.setenv("ADAPTIVE_TTS_PRO_FALLBACK", "1")  # no fallback even when it is enabled

    def ceiling(_page):
        raise RuntimeError("TTS attempt ceiling reached")

    def switch_model(p):
        p.elements[tg._TTS_MODEL_CARD_SELECTOR][0].text = PRO

    hooks = {
        "typing": {"on_type": ceiling},
        "run_click": {"on_run": ceiling},
        "gate_after_typing": {"on_type": switch_model},
    }[phase]
    page = _guarded_flash_page(monkeypatch, **hooks)
    monkeypatch.setattr(tg, "_adaptive_switch_model", lambda *_a: pytest.fail("no Pro fallback"))
    run, voice_folder, manifest = _chapter_run(tmp_path)
    error = tg.TTSWorkspaceUnavailableError if phase == "gate_after_typing" else RuntimeError
    with pytest.raises(error):
        tg._adaptive_voice_chapters(
            page, run, voice_folder, manifest, SimpleNamespace(sha256="sha-1"), {1: SPEECH},
            {"is_403": False},
        )
    assert _typed(page) == [("type", "prompt", SPEECH.directed_text)]
    assert len(_runs(page)) == int(phase == "run_click") and _no_keys(page)
    chap = manifest["chapters"][0]
    assert chap["status"] == "PENDING" and "voice_tier" not in chap and "pieces" not in chap


ONE_PIECE = voice_direction.SpeechText(
    clean_text="one two", directed_text="<sigh> one two", paragraph_count=1
)


@pytest.mark.parametrize("model", [FLASH, PRO])
@pytest.mark.parametrize(("error", "kind"), [(BANNER, "transient"), ("Something odd", "unknown")])
def test_one_piece_chapter_failure_is_never_resent_unchanged(
    tmp_path, monkeypatch, model, error, kind
):
    monkeypatch.delenv("ADAPTIVE_TTS_PRO_FALLBACK", raising=False)
    run, voice_folder, manifest = _chapter_run(tmp_path, model=model)
    sends = ScriptedSends(monkeypatch, [error, "ok", "ok"])
    direction = SimpleNamespace(sha256="sha-1") if model == FLASH else None
    with pytest.raises(tg.TTSProviderError, match=f"^{kind}: .*would resend it unchanged"):
        tg._adaptive_voice_chapters(
            FakePage(), run, voice_folder, manifest, direction, {1: ONE_PIECE}, {"is_403": False}
        )
    assert len(sends.calls) == 1 and sends.switches == []
    chap = manifest["chapters"][0]
    assert chap["status"] == "PENDING" and "pieces" not in chap


def test_one_piece_flash_failure_uses_pro_split_only_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ADAPTIVE_TTS_PRO_FALLBACK", "1")
    run, voice_folder, manifest = _chapter_run(tmp_path)
    sends = ScriptedSends(monkeypatch, [BANNER, "ok"])
    tg._adaptive_voice_chapters(
        FakePage(), run, voice_folder, manifest, SimpleNamespace(sha256="sha-1"),
        {1: ONE_PIECE}, {"is_403": False},
    )
    assert sends.calls == [
        (ONE_PIECE.directed_text, "Chapter_1.wav", FLASH, "Calm"),
        (ONE_PIECE.clean_text, "Chapter_1_pro_part_1.wav", PRO, None),
    ]
    chap = manifest["chapters"][0]
    assert (chap["voice_tier"], chap["voice_model"], chap["status"]) == (
        "pro_split", PRO, "COMPLETED"
    )


# --- S1: typed text, Run control and type-to-Run timing are verified read-only ---------------------
class _Clicked(BaseException):
    """Raised from the fake Run click so a test can stop right after it."""


def _clicked(_page):
    raise _Clicked()


def _send(page, tmp_path, options=FLASH_OPTIONS, text="<sigh> hi  there"):
    tg._adaptive_send_unit(page, text, str(tmp_path / "a.wav"), dict(options), {})


def test_matching_typed_text_and_one_enabled_run_reach_the_click(tmp_path, monkeypatch):
    def respace(p):
        p.elements[tg._TTS_FLASH_PROMPT_SELECTOR][0].value = "<sigh>\nhi there "

    page = _guarded_flash_page(monkeypatch, on_type=respace, on_run=_clicked)
    with pytest.raises(_Clicked):
        _send(page, tmp_path)
    assert len(_runs(page)) == 1 and _no_keys(page)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("typing_false", "did not complete"),
        ("text_mismatch", "does not match"),
        ("no_run", "exactly one visible control, found 0"),
        ("two_runs", "exactly one visible control, found 2"),
        ("run_disabled", "Run control is disabled"),
        ("run_aria_disabled", "Run control is disabled"),
        ("too_slow", "since typing"),
    ],
)
def test_unverified_typing_or_run_control_never_clicks(tmp_path, monkeypatch, case, message):
    def on_type(p):
        run = p.elements[RUN_SELECTOR]
        if case == "typing_false":
            return False
        if case == "text_mismatch":
            p.elements[tg._TTS_FLASH_PROMPT_SELECTOR][0].value = "<sigh> hi"
        elif case == "no_run":
            p.remove(RUN_SELECTOR)
        elif case == "two_runs":
            p.add(RUN_SELECTOR, name="run")
        elif case == "run_disabled":
            run[0].attrs["enabled"] = False
        elif case == "run_aria_disabled":
            run[0].attrs["aria-disabled"] = "true"
        return None

    page = _guarded_flash_page(monkeypatch, on_type=on_type, on_run=_clicked)
    if case == "too_slow":
        clock = iter([100.0, 100.0 + tg._TTS_TYPE_TO_RUN_MAX_SEC])
        monkeypatch.setattr(tg.time, "monotonic", lambda: next(clock))
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match=message):
        _send(page, tmp_path)
    assert len(_typed(page)) == 1
    assert _runs(page) == [] and _no_keys(page)


def test_adaptive_cooldown_stays_inside_the_run_window(tmp_path, monkeypatch):
    sleeps = []
    page = _guarded_flash_page(monkeypatch, on_run=_clicked)
    monkeypatch.setattr(tg.time, "sleep", sleeps.append)
    with pytest.raises(_Clicked):
        _send(page, tmp_path, text="word " * 20000)
    assert max(sleeps) <= tg._TTS_ADAPTIVE_COOLDOWN_MAX_SEC < tg._TTS_TYPE_TO_RUN_MAX_SEC


# --- S2: a sent full chapter is recorded durably and never resent ----------------------------------
def _saved_chapter(run):
    return json.loads(open(tg.get_manifest_path(run), encoding="utf-8").read())["chapters"][0]


def test_full_sent_is_saved_only_after_the_run_click_returns(tmp_path, monkeypatch):
    page = _guarded_flash_page(monkeypatch)

    def stop_after_click(*_args, **_kwargs):
        raise _Clicked()

    page.wait_for_selector = stop_after_click  # first call after the Run click returned
    run, voice_folder, manifest = _chapter_run(tmp_path)
    with pytest.raises(_Clicked):
        tg._adaptive_voice_chapters(
            page, run, voice_folder, manifest, SimpleNamespace(sha256="sha-1"), {1: SPEECH},
            {"is_403": False},
        )
    assert len(_runs(page)) == 1
    saved = _saved_chapter(run)
    assert saved["full_sent"] is True and saved["status"] == "PENDING"


def test_exception_inside_the_run_click_persists_possible_send_before_dispatch(tmp_path, monkeypatch):
    def run_click_raises_exception(_page):
        raise RuntimeError("CDP acknowledgement lost after Run dispatch")

    page = _guarded_flash_page(monkeypatch, on_run=run_click_raises_exception)
    run, voice_folder, manifest = _chapter_run(tmp_path)
    with pytest.raises(tg.TTSProviderError, match="uncertain: adaptive Run"):
        tg._adaptive_voice_chapters(
            page, run, voice_folder, manifest, SimpleNamespace(sha256="sha-1"), {1: SPEECH},
            {"is_403": False},
        )
    assert manifest["chapters"][0]["full_sent"] is True
    assert _saved_chapter(run)["full_sent"] is True


def test_full_sent_chapter_resumes_in_the_split_tier_without_a_full_resend(tmp_path, monkeypatch):
    run, voice_folder, manifest = _chapter_run(tmp_path, full_sent=True)
    sends = ScriptedSends(monkeypatch, ["ok", "ok"])
    # Missing pre-send reservations leave the old click's outcome uncertain.
    with pytest.raises(ValueError, match="incomplete legacy sends"):
        _voice(run, voice_folder, manifest)
    assert sends.calls == []
    assert manifest["chapters"][0]["full_sent"] is True
    assert manifest["chapters"][0]["status"] == "PENDING"


def test_full_sent_one_piece_chapter_stops_without_any_send(tmp_path, monkeypatch):
    monkeypatch.delenv("ADAPTIVE_TTS_PRO_FALLBACK", raising=False)
    run, voice_folder, manifest = _chapter_run(tmp_path, full_sent=True)
    sends = ScriptedSends(monkeypatch, [])
    with pytest.raises(ValueError, match="incomplete legacy sends"):
        tg._adaptive_voice_chapters(
            FakePage(), run, voice_folder, manifest, SimpleNamespace(sha256="sha-1"),
            {1: ONE_PIECE}, {"is_403": False},
        )
    assert sends.calls == []


# --- Optional temperature readback -----------------------------------------------------------------
@pytest.mark.parametrize(
    ("shown", "expected", "ok"),
    [("1", "1", True), ("1.005", "1", True), ("1.02", "1", False), ("abc", "1", False),
     ("1", "", False), ("1", None, False)],
)
def test_temperature_gate_requires_the_configured_value(shown, expected, ok):
    page = FakePage()
    page.add(tg._TTS_TEMPERATURE_SELECTOR).value = shown
    if ok:
        tg._require_tts_temperature(page, expected)
    else:
        with pytest.raises(tg.TTSWorkspaceUnavailableError, match="temperature"):
            tg._require_tts_temperature(page, expected)


def test_temperature_gate_needs_exactly_one_visible_input():
    page = FakePage()
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match="exactly one visible input"):
        tg._require_tts_temperature(page, "1")
    page.add(tg._TTS_TEMPERATURE_SELECTOR).value = "1"
    page.add(tg._TTS_TEMPERATURE_SELECTOR).value = "1"
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match="exactly one visible input"):
        tg._require_tts_temperature(page, "1")


@pytest.mark.parametrize("state", ["wrong_value", "missing_config", "missing_input"])
def test_optional_temperature_readback_gap_warns_without_weakening_voice_gate(state, capsys):
    page = FakePage()
    page.add("ms-run-settings")
    page.add(tg._TTS_MODEL_CARD_SELECTOR, name="card", text=FLASH)
    page.add(tg._TTS_VOICE_NAME_SELECTOR, name="voice", text="Charon")
    page.add(tg._TTS_STYLE_BUTTON_SELECTOR, name="style", attrs={"title": "Calm"})
    if state != "missing_input":
        page.add(tg._TTS_TEMPERATURE_SELECTOR, name="temperature").value = (
            "1.3" if state == "wrong_value" else "1"
        )
    expected = "" if state == "missing_config" else "1"

    tg._verify_tts_settings(page, FLASH, "Charon", "Calm", expected)
    assert "Warning: Could not verify optional TTS temperature" in capsys.readouterr().out

    page.elements[tg._TTS_VOICE_NAME_SELECTOR][0].text = "Fola"
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match="voice is not verified"):
        tg._verify_tts_settings(page, FLASH, "Charon", "Calm", expected)


@pytest.mark.parametrize("adaptive", [True, False])
def test_reapply_temperature_setter_failure_does_not_block_required_settings(monkeypatch, adaptive):
    verified = []
    for name in (
        "_cancel_switch_model_dialog", "_open_tts_editor", "_ensure_run_settings_open",
        "_require_active_tts_model", "_select_tts_voice", "_set_tts_style",
    ):
        monkeypatch.setattr(tg, name, lambda *_a, **_k: None)
    monkeypatch.setattr(tg, "_set_tts_temperature", lambda *_a: False)
    monkeypatch.setattr(tg, "_verify_tts_settings", lambda *args: verified.append(args[-1]))
    page = FakePage()
    page.add(tg._TTS_FLASH_PROMPT_SELECTOR)
    options = {"model": FLASH, "voice": "Charon", "temperature": "1", "style": "Calm"}
    if adaptive:
        options["adaptive"] = True
    tg.reapply_speech_settings(page, options)
    assert verified == ["1" if adaptive else None]
    assert tg._adaptive_unit_options({"temperature": "1"}, FLASH)["adaptive"] is True


@pytest.mark.parametrize("click_result", ["ack_lost_after_dispatch", "false_without_dispatch"])
def test_adaptive_run_click_is_single_and_durably_reserved_before_action(
    tmp_path, monkeypatch, click_result
):
    page = _guarded_flash_page(monkeypatch)
    run_button = page.elements[RUN_SELECTOR][0]
    events = []
    monkeypatch.setattr(
        tg,
        "human_hover_and_click",
        lambda *_args: pytest.fail("adaptive Run must use one semantic click"),
    )

    def click(*, timeout=None):
        if click_result == "ack_lost_after_dispatch":
            events.append("dispatched")
            raise RuntimeError("CDP acknowledgement lost")
        return False

    run_button.click = click
    with pytest.raises(tg.TTSProviderError, match="uncertain:.*Run"):
        tg._adaptive_send_unit(
            page,
            "spoken text",
            str(tmp_path / "audio.wav"),
            FLASH_OPTIONS,
            {"is_403": False},
            on_sent=lambda: events.append("reserved"),
        )

    assert events.count("reserved") == 1
    assert events == (["reserved", "dispatched"] if click_result == "ack_lost_after_dispatch" else ["reserved"])


def test_type_to_run_deadline_is_rechecked_after_durable_reservation(tmp_path, monkeypatch):
    page = _guarded_flash_page(monkeypatch)
    calls = []
    page.elements[RUN_SELECTOR][0].click = lambda **kwargs: calls.append(kwargs)
    now = iter([100.0, 144.9, 145.1])
    monkeypatch.setattr(tg.time, "monotonic", lambda: next(now))
    events = []

    with pytest.raises(tg.TTSProviderError, match="uncertain:.*deadline"):
        tg._adaptive_send_unit(
            page,
            "spoken text",
            str(tmp_path / "audio.wav"),
            FLASH_OPTIONS,
            {"is_403": False},
            on_sent=lambda: events.append("reserved"),
        )

    assert events == ["reserved"]
    assert calls == []


def test_run_click_timeout_is_clipped_to_remaining_type_to_run_budget(tmp_path, monkeypatch):
    page = _guarded_flash_page(monkeypatch)
    calls = []

    def click(*, timeout):
        calls.append(timeout)
        raise _Clicked()

    page.elements[RUN_SELECTOR][0].click = click
    now = iter([100.0, 144.0, 144.5])
    monkeypatch.setattr(tg.time, "monotonic", lambda: next(now))

    with pytest.raises(_Clicked):
        tg._adaptive_send_unit(
            page,
            "spoken text",
            str(tmp_path / "audio.wav"),
            FLASH_OPTIONS,
            {"is_403": False},
            on_sent=lambda: None,
        )

    assert calls == [500]
