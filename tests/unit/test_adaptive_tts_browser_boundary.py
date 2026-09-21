"""Offline checks for adaptive TTS ownership of the shared CDP browser."""

from types import SimpleNamespace

import pytest

from youtube_automation.audio import tts_generator
from youtube_automation.production import ledger


def test_adaptive_tts_refuses_a_busy_browser_lease(tmp_path, monkeypatch):
    (tmp_path / "episode_brief.json").write_text("{}", encoding="utf-8")
    database = tmp_path / "resource.sqlite3"
    monkeypatch.setattr(tts_generator.sys, "argv", ["generate_voice.py", str(tmp_path)])
    monkeypatch.setattr(ledger, "resource_database", lambda: database)
    monkeypatch.setattr(
        tts_generator, "_run_voice_generation",
        lambda: pytest.fail("TTS must not start without the browser lease"),
    )
    assert ledger.Ledger(database).claim("browser", "resource-v1", "another-worker") is not None
    with pytest.raises(RuntimeError, match="Resource is busy: browser"):
        tts_generator.main()


def test_adaptive_tts_does_not_launch_browser_when_cdp_is_unavailable(monkeypatch):
    def fail_connect(_endpoint):
        raise ConnectionError("CDP offline")

    monkeypatch.setattr(
        tts_generator, "launch_browser_with_profile",
        lambda *_args: pytest.fail("Adaptive TTS must not launch or replace a browser"),
    )
    playwright = SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=fail_connect))
    with pytest.raises(tts_generator.AdaptiveBrowserOwnershipError, match="existing CDP"):
        tts_generator.connect_tts_browser(
            playwright, adaptive=True, browser_type="chrome", profile_index="1", port=9222
        )


def test_adaptive_tts_keeps_unrelated_tabs_untouched():
    target_url = "https://aistudio.google.com/generate-speech?model=gemini-2.5-pro-preview-tts"

    class Page:
        def __init__(self, url):
            self.url = url
            self.focused = False

        def bring_to_front(self):
            self.focused = True

    user_tab = Page("https://example.com/my-work")
    owned_page = Page(target_url)
    context = SimpleNamespace(
        pages=[user_tab],
        new_page=lambda: pytest.fail("An owned page was already provided"),
    )
    assert tts_generator.ensure_speech_playground_tab(context, owned_page=owned_page) is owned_page
    assert owned_page.focused
    assert not user_tab.focused
    assert user_tab.url == "https://example.com/my-work"
