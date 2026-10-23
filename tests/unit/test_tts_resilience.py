"""Offline checks for the adaptive TTS UI-resilience layer (fakes only; no browser or provider)."""

import contextlib
from types import SimpleNamespace

import pytest

from youtube_automation.audio import tts_generator
from youtube_automation.production import contracts, narration, writing

MODEL = "gemini-2.5-pro-preview-tts"
SPEECH_URL = f"https://aistudio.google.com/generate-speech?model={MODEL}"
SPLASH = "text='Turn text into natural-sounding speech...'"
TEXTAREA = "textarea[aria-label='Enter a prompt']"
CARD = "ms-run-settings button.model-selector-card [data-test-id='model-name']"
VOICE = "ms-voice-settings .voice-display-name"
BACKDROP = ".cdk-overlay-backdrop.cdk-overlay-backdrop-showing"
STATUS_ZERO = "Http response at 400 or 500 level, error: , http status code: 0"
TEMPERATURE = "ms-run-settings input.slider-number-input"
RUN = "button[type='submit'], button:has-text('Run')"


class _Sent(BaseException):
    """Stops the run at a chosen point so the test can count real sends."""


# -- _click_tts_setting ------------------------------------------------------------------


class OverlayPage:
    url = SPEECH_URL

    def __init__(self, hide_after=None):
        self.overlay = True
        self.hide_after = hide_after
        self.waits = 0

    def locator(self, selector):
        visible = self.overlay and selector in (BACKDROP, "mat-dialog-container")
        element = SimpleNamespace(
            is_visible=lambda: visible,
            inner_text=lambda **_k: "Upgrade   your\nplan",
            locator=lambda _s: SimpleNamespace(count=lambda: 0, nth=None),
        )
        items = [element] if visible else []
        return SimpleNamespace(
            first=element if visible else SimpleNamespace(is_visible=lambda: False),
            count=lambda: len(items),
            nth=lambda i: items[i],
        )

    def wait_for_timeout(self, _milliseconds):
        self.waits += 1
        if self.hide_after is not None and self.waits >= self.hide_after:
            self.overlay = False


class FlakyElement:
    def __init__(self, failures):
        self.failures = failures
        self.clicks = 0

    def click(self, **kwargs):
        assert kwargs == {"timeout": 5000}
        self.clicks += 1
        if self.clicks <= self.failures:
            raise RuntimeError("<div class='cdk-overlay-backdrop'> intercepts pointer events")


def test_click_retries_once_after_transient_overlay_clears():
    page = OverlayPage(hide_after=3)
    element = FlakyElement(failures=1)
    tts_generator._click_tts_setting(page, element, "Create new dialog")
    assert element.clicks == 2


def test_persistent_overlay_fails_closed_with_blocked_by():
    page = OverlayPage()
    element = FlakyElement(failures=5)
    with pytest.raises(tts_generator.TTSWorkspaceUnavailableError) as raised:
        tts_generator._click_tts_setting(page, element, "Create new dialog")
    assert element.clicks == 1
    assert "blocked_by: Upgrade your plan" in str(raised.value)
    assert "Create new dialog" in str(raised.value)


def test_second_click_failure_fails_closed():
    page = OverlayPage(hide_after=1)
    element = FlakyElement(failures=2)
    with pytest.raises(tts_generator.TTSWorkspaceUnavailableError, match="click failed"):
        tts_generator._click_tts_setting(page, element, "Text mode")
    assert element.clicks == 2


# -- connect_tts_browser -----------------------------------------------------------------


class FakeChromium:
    def __init__(self):
        self.calls = []

    def connect_over_cdp(self, endpoint, **kwargs):
        self.calls.append((endpoint, kwargs))
        return "browser"


def test_adaptive_connect_refuses_foreign_debugger_tabs(monkeypatch):
    chromium = FakeChromium()
    monkeypatch.setattr(
        tts_generator.ui_guard,
        "foreign_debugger_targets",
        lambda port: [{"type": "page", "origin": "https://browsermcp.io"}],
    )
    with pytest.raises(tts_generator.AdaptiveBrowserOwnershipError, match="browsermcp.io"):
        tts_generator.connect_tts_browser(
            SimpleNamespace(chromium=chromium),
            adaptive=True, browser_type="chrome", profile_index="1", port=9222,
        )
    assert chromium.calls == []


def test_adaptive_connect_uses_bounded_timeout(monkeypatch):
    chromium = FakeChromium()
    ports = []
    monkeypatch.setattr(
        tts_generator.ui_guard, "foreign_debugger_targets", lambda port: ports.append(port) or []
    )
    browser = tts_generator.connect_tts_browser(
        SimpleNamespace(chromium=chromium),
        adaptive=True, browser_type="chrome", profile_index="1", port=9333,
    )
    assert browser == "browser"
    assert ports == [9333]
    assert chromium.calls == [("http://127.0.0.1:9333", {"timeout": 30000})]


def test_legacy_connect_is_unchanged(monkeypatch):
    chromium = FakeChromium()
    monkeypatch.setattr(
        tts_generator.ui_guard,
        "foreign_debugger_targets",
        lambda *_a: pytest.fail("legacy path must not probe debugger targets"),
    )
    tts_generator.connect_tts_browser(
        SimpleNamespace(chromium=chromium),
        adaptive=False, browser_type="chrome", profile_index="1", port=9222,
    )
    assert chromium.calls == [("http://127.0.0.1:9222", {})]


# -- post-Run classification -------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kind"),
    [("Link a paid API key", "quota"), ("Please sign in", "account"), ("", "unknown"),
     ("Something odd", "unknown")],
)
def test_post_run_failure_raises_for_non_transient(text, kind):
    with pytest.raises(tts_generator.TTSProviderError, match=f"^{kind}: "):
        tts_generator._adaptive_post_run_failure(text)


def test_post_run_failure_allows_transient():
    assert tts_generator._adaptive_post_run_failure(STATUS_ZERO) is None


def test_provider_error_is_exported():
    assert "TTSProviderError" in tts_generator.__all__
    assert issubclass(tts_generator.TTSProviderError, RuntimeError)


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector
        self.index = 0

    def count(self):
        if self.selector in (CARD, VOICE):
            return len(self.all_text_contents())
        return int(self.is_visible())

    def nth(self, index):
        element = FakeLocator(self.page, self.selector)
        element.index = index
        return element

    @property
    def first(self):
        return self

    def is_visible(self):
        if self.selector in (CARD, VOICE, TEMPERATURE, RUN):
            return "ms-run-settings" in self.page.visible
        if self.selector == TEXTAREA:
            return self.page.textarea_visible
        if "Download" in self.selector:
            return self.page.download_ready
        return self.selector in self.page.visible

    def wait_for(self, **kwargs):
        if "Download" in self.selector and kwargs.get("timeout") == 3000:
            self.page.salvage_checks += 1
            self.page.download_ready = self.page.download_on_salvage

    def inner_text(self, **_kwargs):
        return self.all_text_contents()[self.index]

    def click(self, *_args, **_kwargs):
        if self.selector == RUN and hasattr(self.page, "on_run_click"):
            self.page.on_run_click()
        return None

    def input_value(self, **_kwargs):
        return "1.1" if self.selector == TEMPERATURE else self.page.typed_text

    def is_enabled(self, **_kwargs):
        return True

    def get_attribute(self, _name, **_kwargs):
        return None

    def all_text_contents(self):
        if "ms-run-settings" not in self.page.visible:
            return []
        if self.selector == VOICE:
            return ["Achird"]
        if self.selector == CARD:
            return [MODEL]
        return []


class LoopPage:
    def __init__(self, *, stop_appears=False, download_on_salvage=False):
        self.url = SPEECH_URL
        self.visible = {SPLASH, "ms-run-settings"}
        self.textarea_visible = False
        self.stop_appears = stop_appears
        self.download_ready = False
        self.download_on_salvage = download_on_salvage
        self.salvage_checks = 0
        self.typed_text = ""
        self.keyboard = SimpleNamespace(presses=[], press=lambda key: self.keyboard.presses.append(key))

    def locator(self, selector):
        return FakeLocator(self, selector)

    def goto(self, url, **_kwargs):
        self.url = url

    def wait_for_selector(self, selector, **_kwargs):
        if self.stop_appears:
            return None
        raise TimeoutError(f"{selector} never appeared")

    @contextlib.contextmanager
    def expect_download(self, **_kwargs):
        yield SimpleNamespace(value=SimpleNamespace(save_as=lambda _dest: None))

    def wait_for_timeout(self, _milliseconds):
        return None

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


class Harness:
    """Drives the real adaptive _run_voice_generation loop with fakes (no browser, no provider)."""

    def __init__(self, monkeypatch, tmp_path, page, banner):
        self.page = page
        self.typed = 0
        self.run_clicks = 0
        page.on_run_click = lambda: setattr(self, "run_clicks", self.run_clicks + 1)
        self.downloads = 0
        self.stop_on_type = None
        (tmp_path / "refined_script.txt").write_text("مرحبا بالعالم", encoding="utf-8")
        (tmp_path / "episode_brief.json").write_text("{}", encoding="utf-8")
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
        brief = SimpleNamespace(channel=SimpleNamespace(voice="Achird"))
        # This harness drives the Pro path; Flash coverage is in test_tts_flash_adapter.py.
        monkeypatch.setenv("ADAPTIVE_TTS_MODEL", MODEL)
        monkeypatch.setattr(writing, "verify_written_episode", lambda _run: None)
        monkeypatch.setattr(contracts, "load_brief", lambda _run: brief)
        monkeypatch.setattr(narration, "require_unpolished_run", lambda _run: None)
        monkeypatch.setattr(narration, "prepare_manifest", lambda _r, m, _b, _t: m)
        context = SimpleNamespace(pages=[page], new_page=lambda: page)
        browser = SimpleNamespace(contexts=[context])
        tts = tts_generator
        monkeypatch.setattr(tts.main, "attempt_count", 0, raising=False)
        monkeypatch.setattr(tts.sys, "argv", ["generate_voice.py", str(tmp_path)])
        monkeypatch.setattr(tts.time, "sleep", lambda *_a: None)
        monkeypatch.setattr(tts, "read_voice_options", lambda: dict(voice))
        monkeypatch.setattr(tts, "load_or_create_manifest", lambda *_a: manifest)
        monkeypatch.setattr(tts, "save_manifest", lambda *_a: None)
        monkeypatch.setattr(tts, "sync_audio_manifest", lambda *_a, **_k: {})
        monkeypatch.setattr(tts, "probe_audio_file", lambda *_a: None)
        monkeypatch.setattr(tts, "is_valid_wav_file", lambda _path: True)
        monkeypatch.setattr(tts, "get_file_md5", lambda _path: "fresh-audio")
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
        monkeypatch.setattr(tts, "check_ai_studio_errors", lambda _p: (bool(banner), banner))
        monkeypatch.setattr(tts, "human_click", lambda *_a: True)
        monkeypatch.setattr(tts, "reapply_speech_settings", self._reapply)
        monkeypatch.setattr(tts, "humanize_text_input", self._type)
        monkeypatch.setattr(tts, "human_hover_and_click", self._click)

    def _reapply(self, page, _options):
        page.visible.discard(SPLASH)
        page.visible.add("ms-run-settings")
        page.textarea_visible = True

    def _type(self, _page, _textbox, _text):
        self.typed += 1
        self.page.typed_text = _text
        if self.stop_on_type == self.typed:
            raise _Sent("retry reached a second fill")
        if self.typed > 5:
            raise _Sent("unbounded typing")
        return True

    def _click(self, _page, locator):
        if "Download" in getattr(locator, "selector", ""):
            self.downloads += 1
            return True
        return None

    def run(self):
        return tts_generator._run_voice_generation()


@pytest.mark.parametrize(
    ("banner", "kind"), [("Link a paid API key", "quota"), ("Something odd", "unknown")]
)
def test_non_transient_banner_after_run_stops_without_retry(monkeypatch, tmp_path, banner, kind):
    harness = Harness(monkeypatch, tmp_path, LoopPage(), banner)
    with pytest.raises(tts_generator.TTSProviderError, match=f"^{kind}: "):
        harness.run()
    assert harness.typed == 1
    assert harness.run_clicks == 1
    assert "Control+Enter" not in harness.page.keyboard.presses


def test_transient_banner_after_run_reaches_the_retry(monkeypatch, tmp_path):
    harness = Harness(monkeypatch, tmp_path, LoopPage(), STATUS_ZERO)
    # A failed full chapter is never resent unchanged: the retry is a split piece, so the
    # chapter needs more than two paragraphs (a one-piece chapter stops instead).
    script = "مرحبا بالعالم\n\nمرحبا مرة ثانية\n\nمرحبا مرة ثالثة"
    (tmp_path / "refined_script.txt").write_text(script, encoding="utf-8")
    harness.manifest["chapters"][0]["text"] = " ".join(script.split())
    harness.stop_on_type = 2
    with pytest.raises(_Sent, match="second fill"):
        harness.run()
    assert harness.typed == 2
    assert harness.run_clicks == 1


def test_download_failure_without_error_text_stops_after_salvage(monkeypatch, tmp_path):
    page = LoopPage(stop_appears=True)
    harness = Harness(monkeypatch, tmp_path, page, "")
    with pytest.raises(tts_generator.TTSProviderError, match="^unknown: "):
        harness.run()
    assert page.salvage_checks == 1
    assert harness.typed == 1
    assert harness.run_clicks == 1
    assert harness.downloads == 0


def test_no_stop_and_no_banner_after_run_stops_without_retyping(monkeypatch, tmp_path):
    harness = Harness(monkeypatch, tmp_path, LoopPage(), "")
    with pytest.raises(tts_generator.TTSProviderError, match="^unknown: AI Studio showed no Stop"):
        harness.run()
    assert harness.typed == 1
    assert harness.run_clicks == 1


def test_download_salvage_uses_a_late_download_button(monkeypatch, tmp_path):
    page = LoopPage(stop_appears=True, download_on_salvage=True)
    harness = Harness(monkeypatch, tmp_path, page, "")
    harness.run()
    assert page.salvage_checks == 1
    assert harness.downloads == 1
    assert harness.typed == 1
    assert harness.run_clicks == 1
    assert harness.manifest["chapters"][0]["status"] == "COMPLETED"
