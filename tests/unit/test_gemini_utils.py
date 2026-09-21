"""Gemini clean-chat isolation must reject late-hydrating conversation history."""

import pytest

from youtube_automation.browser import gemini_utils


class _Button:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    def click(self, **_kwargs):
        if self.selector == "a[aria-label='New chat'][href='/app']":
            self.page.clicked_new_chat = True
            self.page.url = "https://gemini.google.com/app"
            return
        raise RuntimeError("selector unavailable")


class _Page:
    def __init__(self):
        self.url = "https://gemini.google.com/app/old-conversation"
        self.clicked_new_chat = False
        self.goto_calls = []
        self.keyboard = type("Keyboard", (), {"press": lambda _self, _key: None})()

    def goto(self, url, **_kwargs):
        self.goto_calls.append(url)
        self.url = url

    def wait_for_selector(self, *_args, **_kwargs):
        return None

    def locator(self, selector):
        return _Button(self, selector)


def test_start_clean_chat_does_not_trust_initial_zero_response_count(monkeypatch):
    page = _Page()
    monkeypatch.setattr(
        gemini_utils,
        "_wait_for_clean_chat_surface",
        lambda candidate: candidate.clicked_new_chat and gemini_utils._is_clean_chat_url(candidate.url),
    )

    gemini_utils.start_clean_gemini_chat(page)

    assert page.clicked_new_chat
    assert page.goto_calls == []


def test_start_clean_chat_fails_closed_when_blank_surface_never_stabilizes(monkeypatch):
    page = _Page()
    monkeypatch.setattr(gemini_utils, "_wait_for_clean_chat_surface", lambda _page: False)

    with pytest.raises(RuntimeError, match="refusing to reuse historical responses"):
        gemini_utils.start_clean_gemini_chat(page)


def test_rendered_query_match_requires_prompt_specific_tail():
    common = "Direct a still-image video with validated JSON. " * 5
    current = common + "EPISODE snoozer-hokkaido interval 0-2144"
    restored = common + "EPISODE unrelated-old-run interval 0-900"

    assert gemini_utils._rendered_query_matches_prompt("You said\n" + current, current)
    assert not gemini_utils._rendered_query_matches_prompt("You said\n" + restored, current)


def test_model_label_match_does_not_confuse_flash_with_flash_lite():
    assert gemini_utils._model_label_matches("3.8 Flash\nAll-around help", "Flash")
    assert not gemini_utils._model_label_matches("3.5 Flash-Lite\nFastest answers", "Flash")
    assert gemini_utils._model_label_matches("3.1 Pro\nAdvanced reasoning", "Pro")
