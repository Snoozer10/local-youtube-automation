"""Offline fail-closed checks for AI Studio TTS when the speech workspace is unavailable."""

import contextlib
from types import SimpleNamespace

import pytest

from youtube_automation.audio import tts_generator
from youtube_automation.production import contracts, narration, writing

MODEL = "gemini-2.5-pro-preview-tts"
SPEECH_URL = f"https://aistudio.google.com/generate-speech?model={MODEL}"
PROMPTS_URL = "https://aistudio.google.com/prompts/abc"
SPEECH_NO_MODEL_URL = "https://aistudio.google.com/generate-speech"
SPLASH = "text='Turn text into natural-sounding speech...'"
TEXTAREA = "textarea[aria-label='Enter a prompt']"
CARD = "ms-run-settings button.model-selector-card [data-test-id='model-name']"
VOICE = "ms-voice-settings .voice-display-name"
TEMPERATURE = "ms-run-settings input.slider-number-input"
RUN = "button[type='submit'], button:has-text('Run')"


class _Runaway(BaseException):
    """Escapes the outer `except Exception` so an unbounded loop fails instead of hanging."""


class _Sent(BaseException):
    """Stops the run right after the first Run click so the test can count one real send."""


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector
        self.index = 0

    def count(self):
        if self.selector in (CARD, VOICE):
            return len(self.all_text_contents())
        if self.selector == "ms-run-settings":
            return self.page.panel_count if self.selector in self.page.visible else 0
        return int(self.is_visible())

    def nth(self, index):
        element = FakeLocator(self.page, self.selector)
        element.index = index
        return element

    def all(self):
        return [self.nth(i) for i in range(self.count())]

    def inner_text(self, **_kwargs):
        return self.all_text_contents()[self.index]

    @property
    def first(self):
        return self

    def is_visible(self):
        if self.page.locator_error:
            raise RuntimeError("locator detached")
        if self.selector in (CARD, VOICE):
            return "ms-run-settings" in self.page.visible and self.selector not in self.page.hidden_values
        if self.selector == TEXTAREA:
            return self.page.textarea_visible
        if self.selector in (TEMPERATURE, RUN) and self.page.adaptive_controls:
            # Read-only adaptive gates: one Temperature input and one enabled Run control.
            return "ms-run-settings" in self.page.visible
        return self.selector in self.page.visible

    def click(self, *args, **kwargs):
        if self.selector == RUN:
            handler = getattr(self.page, "run_click_handler", None)
            if handler is not None:
                handler(self.page, self)
        return None

    def input_value(self, **_kwargs):
        return "1.1" if self.selector == TEMPERATURE else self.page.typed_text

    def is_enabled(self, **_kwargs):
        return True

    def get_attribute(self, _name, **_kwargs):
        return None

    def all_text_contents(self):
        if self.selector == VOICE:
            if self.page.voice_error:
                raise RuntimeError("voice detached")
            return list(self.page.voice_names) if "ms-run-settings" in self.page.visible else []
        if self.selector != CARD:
            return []
        if self.page.card_error:
            raise RuntimeError("card detached")
        if "ms-run-settings" not in self.page.visible:
            return []  # closing the run-settings panel removes the model card from the DOM
        return list(self.page.card_names)


class FakeKeyboard:
    def __init__(self):
        self.presses = []

    def press(self, key):
        self.presses.append(key)

    def type(self, _text):
        return None


class FakePage:
    def __init__(self, url="about:blank", landing_url=PROMPTS_URL, visible=(), textarea=True):
        self.url = url
        self.landing_url = landing_url
        self.visible = set(visible)
        self.textarea_visible = textarea
        self.locator_error = False
        self.card_names = [MODEL]
        self.card_error = False
        self.voice_names = ["Achird"]
        self.voice_error = False
        self.panel_count = 1
        self.hidden_values = set()
        self.gotos = []
        self.wait_timeouts = []
        self.keyboard = FakeKeyboard()
        self.adaptive_controls = False
        self.typed_text = ""

    def goto(self, url, **_kwargs):
        self.gotos.append(url)
        if len(self.gotos) > 20:
            raise _Runaway("unbounded navigation")
        self.url = self.landing_url

    def redirect_away(self):
        self.url = PROMPTS_URL
        self.landing_url = PROMPTS_URL
        self.visible.clear()

    def locator(self, selector):
        return FakeLocator(self, selector)

    def bring_to_front(self):
        return None

    def reload(self, **_kwargs):
        return None

    def on(self, *_args):
        return None

    def add_init_script(self, *_args):
        return None

    def close(self):
        return None

    def wait_for_timeout(self, milliseconds):
        self.wait_timeouts.append(milliseconds)

    def wait_for_selector(self, selector, **_kwargs):
        raise TimeoutError(f"{selector} never appeared")


def speech_page(**kwargs):
    return FakePage(url=SPEECH_URL, landing_url=SPEECH_URL, visible={"ms-run-settings"}, **kwargs)


class Harness:
    def __init__(self, monkeypatch, tmp_path, page, *, adaptive):
        self.page = page
        self.typed = 0
        self.run_clicks = 0
        self.downloads = 0
        self.reapply_states = []
        self.on_type = None
        self.on_click = None
        self.on_reapply = None

        (tmp_path / "refined_script.txt").write_text("مرحبا بالعالم", encoding="utf-8")
        voice = {"model": MODEL, "temperature": "1.1", "voice": "Achird"}
        self.manifest = manifest = {
            "voice_config": dict(voice),
            "gemini_completed": True,
            "chapters": [
                {
                    "chapter_num": 1,
                    "text": "مرحبا بالعالم",
                    "audio_file": str(tmp_path / "voice_chapters" / "Chapter_1.wav"),
                    "status": "PENDING",
                }
            ],
        }
        if adaptive:
            (tmp_path / "episode_brief.json").write_text("{}", encoding="utf-8")
            brief = SimpleNamespace(channel=SimpleNamespace(voice="Achird"))
            # This harness drives the Pro path; Flash coverage is in test_tts_flash_adapter.py.
            monkeypatch.setenv("ADAPTIVE_TTS_MODEL", MODEL)
            page.adaptive_controls = True
            monkeypatch.setattr(writing, "verify_written_episode", lambda _run: None)
            monkeypatch.setattr(contracts, "load_brief", lambda _run: brief)
            monkeypatch.setattr(narration, "require_unpolished_run", lambda _run: None)
            monkeypatch.setattr(narration, "prepare_manifest", lambda _r, m, _b, _t: m)

        context = SimpleNamespace(
            pages=[page],
            new_page=lambda: page,
            grant_permissions=lambda *_a: None,
            add_init_script=lambda *_a: None,
        )
        browser = SimpleNamespace(contexts=[context])
        tts = tts_generator
        monkeypatch.setattr(tts.sys, "argv", ["generate_voice.py", str(tmp_path)])
        monkeypatch.setattr(tts.time, "sleep", lambda *_a: None)
        monkeypatch.setattr(tts, "read_voice_options", lambda: dict(voice))
        monkeypatch.setattr(tts, "load_or_create_manifest", lambda *_a: manifest)
        monkeypatch.setattr(tts, "save_manifest", lambda *_a: None)
        monkeypatch.setattr(tts, "sync_audio_manifest", lambda *_a, **_k: {})
        monkeypatch.setattr(tts, "calculate_script_coverage", lambda *_a: 1.0)
        monkeypatch.setattr(tts.loader, "render", lambda *_a, **_k: "")
        monkeypatch.setattr(tts, "get_config_value", lambda _key, default=None: default)
        monkeypatch.setattr(
            tts,
            "get_runtime_state",
            lambda key, default=None: "false" if key == "SWITCH_ACCOUNTS_ENABLED" else default,
        )
        monkeypatch.setattr(tts, "rotate_profile_index", lambda: pytest.fail("no rotation"))
        monkeypatch.setattr(tts, "kill_cdp_chrome", lambda *_a: pytest.fail("no kill"))
        monkeypatch.setattr(tts, "sync_playwright", lambda: contextlib.nullcontext(object()))
        monkeypatch.setattr(tts, "connect_tts_browser", lambda *_a, **_k: browser)
        monkeypatch.setattr(tts, "check_ai_studio_errors", lambda _p: (False, ""))
        monkeypatch.setattr(tts, "human_click", lambda *_a: True)
        monkeypatch.setattr(tts, "reapply_speech_settings", self._reapply)
        monkeypatch.setattr(tts, "humanize_text_input", self._type)
        if adaptive:
            page.run_click_handler = self._click
            monkeypatch.setattr(
                tts,
                "human_hover_and_click",
                lambda _page, locator: self._click(_page, locator)
                if "Download" in getattr(locator, "selector", "")
                else pytest.fail("adaptive Run must use the semantic locator"),
            )
        else:
            monkeypatch.setattr(tts, "human_hover_and_click", self._click)

    def _reapply(self, page, _options):
        self.reapply_states.append(tts_generator._is_speech_workspace(page, MODEL))
        if len(self.reapply_states) > 50:
            raise _Runaway("unbounded settings reapply")
        if self.on_reapply:
            self.on_reapply(page)

    def _type(self, page, _textbox, _text):
        self.typed += 1
        page.typed_text = _text
        if self.on_type:
            self.on_type(page)
        return True

    def _click(self, page, locator):
        if "Download" in getattr(locator, "selector", ""):
            self.downloads += 1
            return True
        self.run_clicks += 1
        if self.run_clicks > 20:
            raise _Runaway("unbounded Run clicks")
        if self.on_click:
            self.on_click(page)
        return True

    def run(self):
        return tts_generator._run_voice_generation()


def test_tab_selection_skips_unapproved_speech_origin():
    spoof = FakePage(url=f"https://evil.example/generate-speech?model={MODEL}")
    approved = FakePage(url=SPEECH_URL)
    context = SimpleNamespace(
        pages=[spoof, approved],
        new_page=lambda: pytest.fail("existing approved tab should be selected"),
    )
    assert tts_generator.ensure_speech_playground_tab(context, MODEL) is approved
    assert spoof.gotos == []
    assert approved.gotos == []


def test_ensure_tab_raises_after_bounded_navigation_to_prompts_page():
    page = FakePage()
    context = SimpleNamespace(pages=[], new_page=lambda: pytest.fail("owned page given"))
    with pytest.raises(tts_generator.TTSWorkspaceUnavailableError, match="/prompts/abc"):
        tts_generator.ensure_speech_playground_tab(context, MODEL, owned_page=page)
    assert 1 <= len(page.gotos) <= tts_generator._TTS_NAV_RETRY_LIMIT


def test_url_guard_redirect_is_bounded_and_never_types(monkeypatch, tmp_path):
    page = speech_page()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=False)
    harness.on_reapply = lambda p: p.redirect_away()
    with pytest.raises(tts_generator.TTSWorkspaceUnavailableError):
        harness.run()
    assert len(page.gotos) <= tts_generator._TTS_NAV_RETRY_LIMIT
    assert harness.typed == 0
    assert harness.run_clicks == 0
    assert all(harness.reapply_states)


def test_hidden_textarea_path_is_bounded(monkeypatch, tmp_path):
    page = speech_page(textarea=False)
    harness = Harness(monkeypatch, tmp_path, page, adaptive=True)
    with pytest.raises(tts_generator.TTSWorkspaceUnavailableError):
        harness.run()
    assert len(harness.reapply_states) <= 2 * (tts_generator._TTS_NAV_RETRY_LIMIT + 1) + 1
    assert harness.typed == 0
    assert harness.run_clicks == 0


def test_non_speech_page_gets_no_typing_and_no_run_click(monkeypatch, tmp_path):
    page = FakePage(landing_url=PROMPTS_URL, textarea=True)
    harness = Harness(monkeypatch, tmp_path, page, adaptive=True)
    with pytest.raises(tts_generator.TTSWorkspaceUnavailableError):
        harness.run()
    assert harness.typed == 0
    assert harness.run_clicks == 0
    assert "Control+Enter" not in page.keyboard.presses


def test_redirect_between_typing_and_run_blocks_the_run_click(monkeypatch, tmp_path):
    page = FakePage(landing_url=SPEECH_URL, visible={"ms-run-settings"})
    harness = Harness(monkeypatch, tmp_path, page, adaptive=True)
    harness.on_type = lambda p: p.redirect_away()
    with pytest.raises(tts_generator.TTSWorkspaceUnavailableError):
        harness.run()
    assert harness.typed == 1
    assert harness.run_clicks == 0
    assert "Control+Enter" not in page.keyboard.presses


def test_adaptive_click_guard_error_propagates_without_retry_or_fallback(monkeypatch, tmp_path):
    page = FakePage(landing_url=SPEECH_URL, visible={"ms-run-settings"})
    harness = Harness(monkeypatch, tmp_path, page, adaptive=True)

    def guard(_page):
        raise RuntimeError("send guard blocked")

    harness.on_click = guard
    with pytest.raises(tts_generator.TTSProviderError, match="uncertain: adaptive Run"):
        harness.run()
    assert harness.typed == 1
    assert harness.run_clicks == 1
    assert "Control+Enter" not in page.keyboard.presses


def test_settings_are_not_reapplied_before_workspace_check_passes(monkeypatch, tmp_path):
    page = FakePage(landing_url=SPEECH_URL, visible=(), textarea=False)
    harness = Harness(monkeypatch, tmp_path, page, adaptive=True)
    with pytest.raises(tts_generator.TTSWorkspaceUnavailableError):
        harness.run()
    assert harness.reapply_states == []
    assert harness.typed == 0


@pytest.mark.parametrize(
    "url",
    [
        f"http://aistudio.google.com/generate-speech?model={MODEL}",
        f"https://evil.example/generate-speech?model={MODEL}",
        f"https://user:pass@aistudio.google.com/generate-speech?model={MODEL}",
        f"https://aistudio.google.com:8443/generate-speech?model={MODEL}",
    ],
)
def test_current_settings_guard_rejects_unapproved_speech_origins(url):
    page = FakePage(url=url, landing_url=url, visible={"ms-run-settings"})
    with pytest.raises(tts_generator.TTSWorkspaceUnavailableError):
        tts_generator._require_current_tts_settings(page, MODEL, "Achird")


def test_true_speech_workspace_passes_detection():
    assert tts_generator._is_speech_workspace(speech_page(), MODEL) is True
    assert tts_generator._is_speech_workspace(speech_page(), None) is True


@pytest.mark.parametrize(
    "page",
    [
        FakePage(url=PROMPTS_URL, visible={"ms-run-settings"}),
        FakePage(url=SPEECH_URL, visible=(), textarea=False),
        FakePage(
            url="https://aistudio.google.com/generate-speech?model=other",
            visible={"ms-run-settings"},
        ),
    ],
)
def test_non_speech_workspace_fails_detection(page):
    assert tts_generator._is_speech_workspace(page, MODEL) is False


def test_detection_treats_locator_errors_as_unavailable():
    page = speech_page()
    page.locator_error = True
    assert tts_generator._is_speech_workspace(page, MODEL) is False


def test_legacy_outer_loop_still_retries_generic_failures(monkeypatch, tmp_path):
    page = speech_page()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=False)

    def broken_typing(_page):
        raise RuntimeError("transient browser crash")

    harness.on_type = broken_typing
    with pytest.raises(RuntimeError, match="DEADLOCK CIRCUIT BREAKER"):
        harness.run()
    assert harness.typed == 10


def test_legacy_run_click_failure_keeps_control_enter_fallback(monkeypatch, tmp_path):
    page = speech_page()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=False)

    def broken_click(_page):
        raise RuntimeError("click failed")

    harness.on_click = broken_click
    with pytest.raises(SystemExit):
        harness.run()
    assert "Control+Enter" in page.keyboard.presses


def realistic_speech_page(url=SPEECH_URL):
    """Splash and run-settings sidebar visible at load; the prompt box is hidden under the splash."""
    return FakePage(url=url, landing_url=url, visible={SPLASH, "ms-run-settings"}, textarea=False)


def close_splash_and_sidebar(page):
    """What the real reapply_speech_settings does: click the splash away, close run settings."""
    page.visible.clear()
    page.textarea_visible = True


def close_splash_keep_panel(page):
    """Splash gone and prompt box shown, but the run-settings panel (and model card) stays open."""
    page.visible.discard(SPLASH)
    page.visible.add("ms-run-settings")
    page.textarea_visible = True


def stop_after_first_send(_page):
    raise _Sent("first Run click")


@pytest.mark.parametrize("adaptive", [True, False])
def test_real_speech_page_with_sidebar_closed_fails_closed_before_typing(
    monkeypatch, tmp_path, adaptive
):
    """2026-10-07 probe: closing the run-settings panel removes the model card, so the gate blocks."""
    page = realistic_speech_page()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    harness.on_reapply = close_splash_and_sidebar
    harness.on_click = stop_after_first_send
    with pytest.raises(tts_generator.TTSWorkspaceUnavailableError):
        harness.run()
    assert harness.reapply_states == [True]
    assert harness.typed == 0
    assert harness.run_clicks == 0
    assert page.gotos == []


@pytest.mark.parametrize("adaptive", [True, False])
def test_real_speech_page_with_panel_open_types_and_runs_once(monkeypatch, tmp_path, adaptive):
    page = realistic_speech_page()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    harness.on_reapply = close_splash_keep_panel
    harness.on_click = stop_after_first_send
    with pytest.raises(_Sent):
        harness.run()
    assert harness.reapply_states == [True]
    assert harness.typed == 1
    assert harness.run_clicks == 1
    assert page.gotos == []


@pytest.mark.parametrize("phase", ["entry", "after_settings"])
def test_prompts_page_with_same_textarea_never_types_or_runs(monkeypatch, tmp_path, phase):
    if phase == "entry":
        page = FakePage(landing_url=PROMPTS_URL, visible=(), textarea=True)
    else:
        page = realistic_speech_page()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=True)

    def land_on_prompts(p):
        close_splash_and_sidebar(p)
        p.url = p.landing_url = PROMPTS_URL

    harness.on_reapply = land_on_prompts
    with pytest.raises(tts_generator.TTSWorkspaceUnavailableError):
        harness.run()
    assert harness.typed == 0
    assert harness.run_clicks == 0
    assert "Control+Enter" not in page.keyboard.presses


def test_adaptive_guard_error_during_typing_is_not_retried(monkeypatch, tmp_path):
    page = realistic_speech_page()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=True)
    harness.on_reapply = close_splash_keep_panel

    def ceiling(_page):
        raise RuntimeError("TTS attempt ceiling reached")

    harness.on_type = ceiling
    with pytest.raises(RuntimeError, match="TTS attempt ceiling reached"):
        harness.run()
    assert harness.typed == 1
    assert harness.run_clicks == 0
    assert "Control+Enter" not in page.keyboard.presses


class _DownloadingPage(FakePage):
    """Synthesis starts and finishes, and every download yields the same (duplicate) audio."""

    def wait_for_selector(self, selector, **_kwargs):
        return None

    def locator(self, selector):
        found = FakeLocator(self, selector)
        if "Download" in selector:
            found.is_visible = lambda: True
        return found

    @contextlib.contextmanager
    def expect_download(self, **_kwargs):
        yield SimpleNamespace(value=SimpleNamespace(save_as=lambda _dest: None))


@pytest.mark.parametrize("adaptive", [True, False])
def test_duplicate_audio_retry_is_bounded_by_failover_limit(monkeypatch, tmp_path, adaptive):
    page = _DownloadingPage(
        url=SPEECH_URL,
        landing_url=SPEECH_URL,
        visible={SPLASH, "ms-run-settings"},
        textarea=False,
    )
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    harness.on_reapply = close_splash_keep_panel
    harness.manifest["chapters"].insert(
        0,
        {
            "chapter_num": 0,
            "text": "سابق",
            "audio_file": str(tmp_path / "Chapter_0.wav"),
            "status": "COMPLETED",
            "md5": "same-audio",
        },
    )
    monkeypatch.setattr(tts_generator, "is_valid_wav_file", lambda _path: True)
    monkeypatch.setattr(tts_generator, "get_file_md5", lambda _path: "same-audio")
    retry_limit = 3  # FAILOVER_RETRY_LIMIT default; the harness returns config defaults
    if adaptive:
        # Adaptive maps chapters onto the script, and a failed one-paragraph chapter is never
        # resent unchanged, so the duplicate stops the run after its one send.
        (tmp_path / "refined_script.txt").write_text("سابق\n\nمرحبا بالعالم", encoding="utf-8")
        with pytest.raises(tts_generator.TTSProviderError, match="matches an earlier"):
            harness.run()
        assert harness.run_clicks == harness.typed == harness.downloads == 1 < retry_limit
        return
    with pytest.raises(SystemExit):
        harness.run()
    assert harness.run_clicks == retry_limit
    assert harness.typed == retry_limit
    assert harness.downloads == retry_limit


@pytest.mark.parametrize(
    "url",
    [
        "https://aistudio.google.com/prompts/x?next=generate-speech",
        f"https://aistudio.google.com/prompts/x?next=generate-speech&model={MODEL}",
        f"https://aistudio.google.com/generate-speech-old?model={MODEL}",
        f"https://aistudio.google.com/x/generate-speech?model={MODEL}",
        f"https://aistudio.google.com/generate-speech/extra?model={MODEL}",
        f"https://aistudio.google.com/generate-speech//?model={MODEL}",
        f"http://aistudio.google.com/generate-speech?model={MODEL}",
        f"https://evil.example/generate-speech?model={MODEL}",
        f"https://user:pass@aistudio.google.com/generate-speech?model={MODEL}",
        f"https://aistudio.google.com:8443/generate-speech?model={MODEL}",
        "",
    ],
)
def test_url_lookalikes_are_rejected_in_loop_and_at_entry(url):
    assert tts_generator._is_speech_url(url) is False
    assert tts_generator._is_speech_url(url, MODEL) is False
    page = FakePage(url=url, visible={"ms-run-settings"})
    assert tts_generator._is_speech_workspace(page) is False


@pytest.mark.parametrize(
    "url",
    [
        f"https://aistudio.google.com/generate-speech?model={MODEL}-extra",
        f"https://aistudio.google.com/generate-speech?model=x{MODEL}",
        f"https://aistudio.google.com/generate-speech?model={MODEL}&model=other",
        f"https://aistudio.google.com/generate-speech?other={MODEL}",
    ],
)
def test_model_lookalikes_are_rejected_at_entry(url):
    assert tts_generator._TTS_REQUIRE_MODEL_QUERY_AT_ENTRY is True
    assert tts_generator._is_speech_url(url, MODEL) is False


@pytest.mark.parametrize(
    "url",
    [
        SPEECH_URL,
        f"https://aistudio.google.com/generate-speech/?model={MODEL}",
        f"https://aistudio.google.com:443/generate-speech?model={MODEL}",
    ],
)
def test_real_speech_urls_pass_in_loop_and_at_entry(url):
    assert tts_generator._is_speech_url(url) is True
    assert tts_generator._is_speech_url(url, MODEL) is True


def test_mid_loop_speech_url_without_model_passes(monkeypatch, tmp_path):
    assert tts_generator._is_speech_url(SPEECH_NO_MODEL_URL) is True
    page = realistic_speech_page()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=True)

    def drop_model_query(p):
        close_splash_keep_panel(p)
        p.url = p.landing_url = SPEECH_NO_MODEL_URL

    harness.on_reapply = drop_model_query
    harness.on_click = stop_after_first_send
    with pytest.raises(_Sent):
        harness.run()
    assert page.gotos == []
    assert harness.typed == 1
    assert harness.run_clicks == 1


def test_entry_requires_model_query_when_flag_is_on():
    assert tts_generator._TTS_REQUIRE_MODEL_QUERY_AT_ENTRY is True
    assert tts_generator._is_speech_url(SPEECH_NO_MODEL_URL, MODEL) is False
    page = realistic_speech_page(SPEECH_NO_MODEL_URL)
    context = SimpleNamespace(pages=[], new_page=lambda: pytest.fail("owned page given"))
    with pytest.raises(tts_generator.TTSWorkspaceUnavailableError):
        tts_generator.ensure_speech_playground_tab(context, MODEL, owned_page=page)
    assert 1 <= len(page.gotos) <= tts_generator._TTS_NAV_RETRY_LIMIT
    with pytest.raises(tts_generator.TTSWorkspaceUnavailableError):
        tts_generator._require_speech_workspace(page, MODEL)


def test_entry_accepts_missing_model_query_when_flag_is_off(monkeypatch):
    monkeypatch.setattr(tts_generator, "_TTS_REQUIRE_MODEL_QUERY_AT_ENTRY", False)
    prompts_with_model = f"https://aistudio.google.com/prompts/x?model={MODEL}"
    assert tts_generator._is_speech_url(SPEECH_NO_MODEL_URL, MODEL) is True
    assert tts_generator._is_speech_url(f"{SPEECH_NO_MODEL_URL}?model=other", MODEL) is True
    assert tts_generator._is_speech_url(prompts_with_model, MODEL) is False
    page = realistic_speech_page(SPEECH_NO_MODEL_URL)
    context = SimpleNamespace(pages=[], new_page=lambda: pytest.fail("owned page given"))
    assert tts_generator.ensure_speech_playground_tab(context, MODEL, owned_page=page) is page
    assert page.gotos == []
    tts_generator._require_speech_workspace(page, MODEL)


def test_workspace_error_is_exported():
    assert "TTSWorkspaceUnavailableError" in tts_generator.__all__


GATE_ERROR = tts_generator.TTSWorkspaceUnavailableError


@pytest.mark.parametrize("adaptive", [True, False])
def test_chat_model_on_speech_path_never_types_or_runs(monkeypatch, tmp_path, adaptive):
    page = speech_page(textarea=True)
    page.card_names = ["gemini-3.8-flash"]
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    with pytest.raises(GATE_ERROR, match="gemini-3.8-flash"):
        harness.run()
    assert harness.typed == 0
    assert harness.run_clicks == 0
    assert "Control+Enter" not in page.keyboard.presses


@pytest.mark.parametrize("adaptive", [True, False])
def test_missing_model_card_fails_closed_before_typing(monkeypatch, tmp_path, adaptive):
    page = speech_page()
    page.card_names = []
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    with pytest.raises(GATE_ERROR, match="speech entry did not finish loading within 20 seconds"):
        harness.run()
    assert page.wait_timeouts == [250] * 80
    assert harness.typed == 0
    assert harness.run_clicks == 0


@pytest.mark.parametrize("adaptive", [True, False])
def test_target_model_card_types_and_runs_once(monkeypatch, tmp_path, adaptive):
    page = speech_page()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    harness.on_click = stop_after_first_send
    with pytest.raises(_Sent):
        harness.run()
    assert harness.typed == 1
    assert harness.run_clicks == 1


@pytest.mark.parametrize("adaptive", [True, False])
def test_model_switch_between_typing_and_run_blocks_the_run_click(monkeypatch, tmp_path, adaptive):
    page = speech_page()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    harness.on_type = lambda p: setattr(p, "card_names", ["gemini-3.8-flash"])
    with pytest.raises(GATE_ERROR):
        harness.run()
    assert harness.typed == 1
    assert harness.run_clicks == 0
    assert "Control+Enter" not in page.keyboard.presses


@pytest.mark.parametrize("adaptive", [True, False])
def test_two_model_cards_fail_closed(monkeypatch, tmp_path, adaptive):
    page = speech_page()
    page.card_names = [MODEL, MODEL]
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    with pytest.raises(GATE_ERROR):
        harness.run()
    assert harness.typed == 0
    assert harness.run_clicks == 0


@pytest.mark.parametrize("adaptive", [True, False])
def test_card_locator_error_fails_closed(monkeypatch, tmp_path, adaptive):
    page = speech_page()
    page.card_error = True
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    with pytest.raises(GATE_ERROR):
        harness.run()
    assert harness.typed == 0
    assert harness.run_clicks == 0


def test_require_active_tts_model_accepts_only_the_exact_target():
    tts_generator._require_active_tts_model(speech_page(), MODEL)
    page = speech_page()
    page.card_names = [f"  {MODEL}  "]
    tts_generator._require_active_tts_model(page, MODEL)
    for names in ([], ["gemini-3.8-flash"], [MODEL, MODEL], [MODEL, "other"], [f"{MODEL}-x"]):
        page = speech_page()
        page.card_names = names
        with pytest.raises(GATE_ERROR) as info:
            tts_generator._require_active_tts_model(page, MODEL)
        message = str(info.value)
        assert MODEL in message
        assert repr(names) in message
        assert SPEECH_URL in message
        if names == []:
            assert "run-settings panel must be open" in message
            assert "does not match" not in message
        else:
            assert "does not match" in message
            assert "run-settings panel" not in message


def test_require_active_tts_model_treats_read_errors_as_unverifiable():
    page = speech_page()
    page.card_error = True
    with pytest.raises(GATE_ERROR, match="run-settings panel must be open") as info:
        tts_generator._require_active_tts_model(page, MODEL)
    assert "does not match" not in str(info.value)


def test_require_active_tts_model_closed_panel_explains_model_card_requirement():
    """A closed panel hides the model card; speech settings keep that panel open."""
    page = speech_page()
    page.visible.discard("ms-run-settings")
    with pytest.raises(GATE_ERROR, match="closed panel or an unavailable model card"):
        tts_generator._require_active_tts_model(page, MODEL)


@pytest.mark.parametrize("model", ["", None])
def test_require_active_tts_model_rejects_an_empty_target(model):
    page = speech_page()
    page.card_names = [""]
    with pytest.raises(GATE_ERROR, match="empty"):
        tts_generator._require_active_tts_model(page, model)


def test_gate_failure_before_run_presses_no_control_enter(monkeypatch, tmp_path):
    page = speech_page()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=False)
    harness.on_type = lambda p: setattr(p, "card_names", [])
    with pytest.raises(GATE_ERROR):
        harness.run()
    assert harness.run_clicks == 0
    assert page.keyboard.presses == []


@pytest.mark.parametrize("adaptive", [True, False])
@pytest.mark.parametrize("phase", ["after_settings", "before_fill", "after_fill", "cooldown"])
def test_voice_drift_blocks_fill_or_run(monkeypatch, tmp_path, adaptive, phase):
    page = speech_page()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    def drift(p):
        p.voice_names = ["Charon"]

    if phase == "after_settings":
        harness.on_reapply = drift
    elif phase == "before_fill" and adaptive:
        # Adaptive types voice-direction text (no sanitize_script_text); the network check is
        # its last step before the pre-fill settings gate.
        def healthy(*_args, **_kwargs):
            drift(page)

        monkeypatch.setattr(tts_generator.network_health, "require_healthy", healthy)
    elif phase == "before_fill":
        original = tts_generator.sanitize_script_text

        def sanitize(text):
            drift(page)
            return original(text)

        monkeypatch.setattr(tts_generator, "sanitize_script_text", sanitize)
    elif phase == "after_fill":
        harness.on_type = drift
    else:
        monkeypatch.setattr(tts_generator.time, "sleep", lambda *_: drift(page) if harness.typed else None)
    with pytest.raises(GATE_ERROR, match="voice"):
        harness.run()
    assert harness.typed == int(phase in {"after_fill", "cooldown"})
    assert harness.run_clicks == 0
    assert page.keyboard.presses == []


@pytest.mark.parametrize("fault", ["missing_voice", "wrong_voice", "duplicate_voice", "unreadable_voice", "hidden_voice", "missing_panel", "duplicate_panel", "hidden_model", "wrong_model", "duplicate_model", "unreadable_model", "pending_switch"])
def test_current_settings_guard_rejects_unverifiable_state(fault):
    page = speech_page()
    if fault == "missing_voice":
        page.voice_names = []
    elif fault == "wrong_voice":
        page.voice_names = ["Charon"]
    elif fault == "duplicate_voice":
        page.voice_names *= 2
    elif fault == "unreadable_voice":
        page.voice_error = True
    elif fault == "hidden_voice":
        page.hidden_values.add(VOICE)
    elif fault == "missing_panel":
        page.visible.clear()
    elif fault == "duplicate_panel":
        page.panel_count = 2
    elif fault == "hidden_model":
        page.hidden_values.add(CARD)
    elif fault == "wrong_model":
        page.card_names = ["gemini-3.8-flash"]
    elif fault == "duplicate_model":
        page.card_names *= 2
    elif fault == "unreadable_model":
        page.card_error = True
    else:
        page.visible.add(tts_generator._TTS_SWITCH_MODEL_DIALOG_SELECTOR)
    with pytest.raises(GATE_ERROR):
        tts_generator._require_current_tts_settings(page, MODEL, "Achird")
    assert page.gotos == []
    assert page.keyboard.presses == []


def test_current_settings_guard_allows_exact_ready_state_without_mutation():
    page = speech_page()
    tts_generator._require_current_tts_settings(page, MODEL, "Achird")
    assert page.voice_names == ["Achird"]
    assert page.card_names == [MODEL]
    assert page.gotos == []
    assert page.keyboard.presses == []


@pytest.mark.parametrize("phase", ["temperature", "reopen"])
def test_final_settings_check_detects_voice_drift_and_reopens_panel(monkeypatch, phase):
    page = speech_page()
    reopen_calls = []
    for helper in ("_cancel_switch_model_dialog", "_open_tts_editor", "_select_tts_text_mode"):
        monkeypatch.setattr(tts_generator, helper, lambda *_: None)
    monkeypatch.setattr(tts_generator, "_select_tts_voice", lambda p, voice: setattr(p, "voice_names", [voice]))

    def reopen(p):
        reopen_calls.append(True)
        p.visible.add("ms-run-settings")
        if phase == "reopen" and len(reopen_calls) == 2:
            p.voice_names = ["Charon"]

    def temperature(p, _value):
        p.visible.discard("ms-run-settings")
        if phase == "temperature":
            p.voice_names = ["Charon"]
        return False  # Optional quality-setting miss cannot bypass required settings.

    monkeypatch.setattr(tts_generator, "_ensure_run_settings_open", reopen)
    monkeypatch.setattr(tts_generator, "_set_tts_temperature", temperature)
    with pytest.raises(GATE_ERROR, match="voice"):
        tts_generator.reapply_speech_settings(page, {"model": MODEL, "voice": "Achird"})
    assert len(reopen_calls) == 2
