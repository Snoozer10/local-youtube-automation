"""Offline checks for the bounded browser UI guard (fakes only; no browser or network)."""

import io
import json

import pytest

from youtube_automation.browser import ui_guard

BACKDROP = ".cdk-overlay-backdrop.cdk-overlay-backdrop-showing"
DIALOG = "mat-dialog-container"
STATUS_ZERO = "Http response at 400 or 500 level, error: , http status code: 0"


class Collection:
    def __init__(self, items):
        self.items = list(items)

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]

    @property
    def first(self):
        return self.items[0] if self.items else Hidden()

    def is_visible(self):
        return self.first.is_visible()


class Hidden:
    def is_visible(self):
        return False

    def inner_text(self, **_kwargs):
        return ""


class FakeButton:
    def __init__(self, page, text, aria=None):
        self.page = page
        self.text = text
        self.aria = aria

    def is_visible(self):
        return True

    def get_attribute(self, name, **_kwargs):
        return self.aria if name == "aria-label" else None

    def inner_text(self, **_kwargs):
        return self.text

    def click(self, **_kwargs):
        self.page.clicked.append(self.text)
        if self.page.clear_on_click:
            self.page.overlay = False


class FakeDialog:
    def __init__(self, page, text, buttons=(), inputs=0):
        self.page = page
        self.text = text
        self.buttons = [FakeButton(page, label) for label in buttons]
        self.inputs = inputs

    def is_visible(self):
        return self.page.overlay

    def inner_text(self, **_kwargs):
        return self.text

    def locator(self, selector):
        if selector == "button, [role='button']":
            return Collection(self.buttons)
        if selector == "input, textarea, select":
            return Collection([object()] * self.inputs)
        raise AssertionError(selector)


class Keyboard:
    def __init__(self, page):
        self.page = page
        self.presses = []

    def press(self, key):
        self.presses.append(key)
        if self.page.clear_on_escape:
            self.page.overlay = False


class FakePage:
    def __init__(self, *, text="Promo", buttons=(), inputs=0, hide_after=None):
        self.overlay = True
        self.hide_after = hide_after
        self.waits = 0
        self.clicked = []
        self.clear_on_click = True
        self.clear_on_escape = True
        self.keyboard = Keyboard(self)
        self.dialog = FakeDialog(self, text, buttons, inputs)

    def locator(self, selector):
        if selector == BACKDROP:
            return Collection([self.dialog] if self.overlay else [])
        if selector == DIALOG:
            return Collection([self.dialog] if self.overlay else [])
        return Collection([])

    def wait_for_timeout(self, _milliseconds):
        self.waits += 1
        if self.hide_after is not None and self.waits >= self.hide_after:
            self.overlay = False


def test_overlay_visible_for_some_polls_then_gone_returns_true():
    page = FakePage(hide_after=3)
    assert ui_guard.wait_for_overlay_clear(page, timeout_sec=10.0, poll_sec=0.25)
    assert page.waits == 3


def test_overlay_wait_is_bounded():
    page = FakePage()
    assert not ui_guard.wait_for_overlay_clear(page, timeout_sec=1.0, poll_sec=0.25)
    assert page.waits == 4


def test_confirmed_absence_counts_as_clear():
    class NoOverlay:
        def locator(self, _selector):
            return Collection([])

    assert ui_guard.wait_for_overlay_clear(NoOverlay(), timeout_sec=0.0)
    assert ui_guard.ensure_clear(NoOverlay(), wait_sec=0.0).cleared


def test_probe_errors_fail_closed():
    class Broken:
        def locator(self, _selector):
            raise RuntimeError("detached")

    page = Broken()
    assert not ui_guard.wait_for_overlay_clear(page, timeout_sec=0.0)
    result = ui_guard.ensure_clear(page, wait_sec=0.0)
    assert not result.cleared
    assert result.blocked_by == "overlay visibility probe failed"


def test_overlay_guard_checks_visible_matches_after_hidden_first():
    class Match:
        def __init__(self, visible):
            self.visible = visible

        def is_visible(self):
            return self.visible

    class Page:
        def locator(self, selector):
            if selector == BACKDROP:
                return Collection([Match(False), Match(True)])
            return Collection([])

    result = ui_guard.ensure_clear(Page(), wait_sec=0.0)
    assert not result.cleared
    assert result.blocked_by == BACKDROP


def test_unreadable_overlay_match_count_fails_closed():
    class BrokenCount:
        def count(self):
            raise RuntimeError("detached")

    class Page:
        def locator(self, _selector):
            return BrokenCount()

    result = ui_guard.ensure_clear(Page(), wait_sec=0.0)
    assert not result.cleared
    assert result.blocked_by == "overlay visibility probe failed"


def test_unreadable_overlay_visibility_fails_closed():
    class BrokenVisibility:
        def is_visible(self):
            raise RuntimeError("detached")

    class Page:
        def locator(self, _selector):
            return Collection([BrokenVisibility()])

    result = ui_guard.ensure_clear(Page(), wait_sec=0.0)
    assert not result.cleared
    assert result.blocked_by == "overlay visibility probe failed"


def test_too_many_unchecked_overlay_matches_fail_closed():
    class Page:
        def locator(self, _selector):
            return Collection([Hidden() for _ in range(33)])

    result = ui_guard.ensure_clear(Page(), wait_sec=0.0)
    assert not result.cleared
    assert result.blocked_by == "overlay visibility probe failed"


def test_unreadable_overlay_text_stays_blocked_by_selector():
    class UnreadableText(FakeDialog):
        def inner_text(self, **_kwargs):
            raise RuntimeError("detached")

    page = FakePage()
    page.dialog = UnreadableText(page, "Promo")

    result = ui_guard.ensure_clear(page, wait_sec=0.0)
    assert not result.cleared
    assert result.blocked_by == BACKDROP


def test_safe_got_it_button_is_clicked():
    page = FakePage(text="New feature", buttons=["Got it"])
    result = ui_guard.ensure_clear(page, wait_sec=0.5)
    assert result.cleared
    assert result.actions == ("click:got it",)
    assert result.blocked_by is None
    assert page.clicked == ["Got it"]
    assert page.keyboard.presses == []


@pytest.mark.parametrize("label", ["Accept", "Continue", "Upgrade"])
def test_forbidden_buttons_are_never_clicked(label):
    page = FakePage(text=f"Terms   of\nuse {label}", buttons=[label])
    result = ui_guard.ensure_clear(page, wait_sec=0.5, allow_escape=True)
    assert not result.cleared
    assert page.clicked == []
    assert page.keyboard.presses == []
    assert result.blocked_by == f"Terms of use {label}"


def test_safe_button_beside_forbidden_one_clicks_only_the_safe_one():
    page = FakePage(buttons=["Upgrade", "Not now"])
    result = ui_guard.dismiss_safe_overlays(page)
    assert page.clicked == ["Not now"]
    assert result.cleared


def test_escape_is_pressed_only_when_allowed():
    page = FakePage(buttons=["Learn more"])
    result = ui_guard.dismiss_safe_overlays(page, allow_escape=False)
    assert page.keyboard.presses == []
    assert not result.cleared
    result = ui_guard.dismiss_safe_overlays(page, allow_escape=True)
    assert page.keyboard.presses == ["Escape"]
    assert result.actions == ("escape",)
    assert result.cleared


def test_escape_is_not_pressed_with_inputs_in_the_dialog():
    page = FakePage(buttons=["Learn more"], inputs=1)
    result = ui_guard.dismiss_safe_overlays(page, allow_escape=True)
    assert page.keyboard.presses == []
    assert not result.cleared
    assert result.blocked_by == "Promo"


def test_blocked_by_is_truncated_to_200_chars():
    page = FakePage(text="x" * 500)
    result = ui_guard.ensure_clear(page, wait_sec=0.25)
    assert result.blocked_by == "x" * 200


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (STATUS_ZERO, "transient"),
        ("Link a paid API key", "quota"),
        ("429 Too Many Requests", "quota"),
        ("You exceeded your quota", "quota"),
        ("Please sign in", "account"),
        ("Internal server error, try again", "transient"),
        ("", "unknown"),
        ("   ", "unknown"),
        ("Something odd happened", "unknown"),
    ],
)
def test_classify_provider_error(text, kind):
    assert ui_guard.classify_provider_error(text) == kind


def _opener_for(payload, calls):
    def opener(url, timeout):
        calls.append((url, timeout))
        return io.BytesIO(json.dumps(payload).encode("utf-8"))

    return opener


def test_foreign_debugger_targets_returns_only_sanitized_foreign_pages():
    payload = [
        {"type": "page", "id": "A1", "title": "Ext", "url": "chrome-extension://abcdef/popup.html?x=1"},
        {"type": "page", "id": "B2", "title": "MCP", "url": "https://browsermcp.io/blank"},
        {"type": "page", "id": "C3", "title": "Gemini", "url": "https://gemini.google.com/app"},
        {"type": "service_worker", "id": "D4", "url": "chrome-extension://abcdef/sw.js"},
        {"type": "browser_ui", "id": "E5", "url": "chrome://newtab-footer/"},
    ]
    calls = []
    found = ui_guard.foreign_debugger_targets(9333, opener=_opener_for(payload, calls))
    assert calls == [("http://127.0.0.1:9333/json/list", 5)]
    assert found == [
        {"type": "page", "origin": "chrome-extension://abcdef"},
        {"type": "page", "origin": "https://browsermcp.io"},
    ]


def test_foreign_debugger_targets_raises_redacted_probe_error():
    def opener(*_args, **_kwargs):
        raise OSError("connection refused: secret detail")

    with pytest.raises(ui_guard.TargetProbeError) as exc_info:
        ui_guard.foreign_debugger_targets(opener=opener)

    assert exc_info.value.code == "probe_failed"
    assert "secret detail" not in str(exc_info.value)
