"""Unit tests for gemini_controller using fake browser objects (no real browser)."""

import time as real_time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

import gemini_controller
from gemini_controller import (
    GEMINI_APP_URL,
    inject_prompt_via_cdp,
    jitter_delay,
    open_ephemeral_session,
    read_gemini_input_text,
    reset_chat_session,
    wait_for_gemini_turn_completion,
)


class FakeContext:
    def __init__(self, page: "FakePage") -> None:
        self.page = page
        self.granted_permissions: list[list[str]] = []

    def grant_permissions(self, permissions: list[str]) -> None:
        self.granted_permissions.append(list(permissions))


class FakeKeyboard:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    def insert_text(self, text: str) -> None:
        if not self.page.insert_enabled:
            return
        if self.page.insert_override is not None:
            self.page.input_value = self.page.insert_override
        else:
            self.page.input_value = text

    def press(self, key: str) -> None:
        self.page.pressed_keys.append(key)
        if key == "Backspace":
            self.page.input_value = ""
        elif key == "Control+v" and self.page.paste_enabled:
            self.page.input_value = self.page.clipboard_content


class FakeLocator:
    def __init__(self, page: "FakePage", selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> "FakeLocator":
        return self

    @property
    def last(self) -> "FakeLocator":
        return self

    def count(self) -> int:
        return self.page.count_map.get(self.selector, 0)

    def click(self) -> None:
        if self.count() == 0:
            raise AssertionError(f"click on empty locator: {self.selector}")

    def is_visible(self) -> bool:
        return self.page.visible

    def evaluate(self, expression: str, arg: object = None) -> object:
        if "innerText" in expression:
            return self.page.response_text
        return self.page.evaluate(expression, arg)

    def fill(self, text: str) -> None:
        raise AssertionError(f"unexpected locator.fill on {self.selector}")


class FakeInputBox:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    def click(self) -> None:
        return None

    def inner_text(self) -> str:
        return self.page.input_value

    def fill(self, text: str) -> None:
        self.page.fill_called += 1
        self.page.input_value = text


class FakePage:
    def __init__(self) -> None:
        self.url: str = GEMINI_APP_URL
        self.keyboard = FakeKeyboard(self)
        self.context = FakeContext(self)
        self.input_value: str = ""
        self.insert_enabled: bool = True
        self.insert_override: str | None = None
        self.paste_enabled: bool = True
        self.exec_enabled: bool = True
        self.clipboard_content: str = ""
        self.fill_called: int = 0
        self.pressed_keys: list[str] = []
        self.evaluate_calls: list[tuple[str, object]] = []
        self.goto_calls: list[str] = []
        self.count_map: dict[str, int] = {}
        self.visible: bool = True
        self.response_text: str = ""

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)

    def evaluate(self, expression: str, arg: object = None) -> object:
        self.evaluate_calls.append((expression, arg))
        if "clipboard.writeText" in expression:
            if isinstance(arg, str):
                self.clipboard_content = arg
            return None
        if "execCommand" in expression and self.exec_enabled and isinstance(arg, str):
            self.input_value += arg
        return None

    def goto(self, url: str, **kwargs: object) -> None:
        self.goto_calls.append(url)


class NoSleepClock:
    def __init__(self) -> None:
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    def time(self) -> float:
        return real_time.time()

    def strftime(self, fmt: str) -> str:
        return real_time.strftime(fmt)


@pytest.fixture
def fake_page() -> FakePage:
    return FakePage()


def _patch_box(monkeypatch: pytest.MonkeyPatch, page: FakePage) -> FakeInputBox:
    box = FakeInputBox(page)
    monkeypatch.setattr(gemini_controller, "find_input_box", lambda p: box)
    return box


def test_read_gemini_input_text_returns_inner_text(monkeypatch, fake_page):
    fake_page.input_value = "hello world"
    _patch_box(monkeypatch, fake_page)
    assert read_gemini_input_text(fake_page) == "hello world"


def test_read_gemini_input_text_missing_box(monkeypatch, fake_page):
    monkeypatch.setattr(gemini_controller, "find_input_box", lambda p: None)
    assert read_gemini_input_text(fake_page) == ""


def test_inject_tier1_keyboard_success(monkeypatch, fake_page):
    _patch_box(monkeypatch, fake_page)
    clock = NoSleepClock()
    monkeypatch.setattr(gemini_controller, "time", clock)
    payload = "مرحبا بالعالم من القاهرة"
    assert inject_prompt_via_cdp(fake_page, payload) is True
    assert fake_page.input_value == payload
    assert fake_page.context.granted_permissions == []
    assert fake_page.pressed_keys.count("Control+v") == 0
    assert fake_page.fill_called == 0
    assert all("clipboard.writeText" not in expr for expr, _ in fake_page.evaluate_calls)
    assert any(s == gemini_controller._SETTLE_SLEEP_SECONDS for s in clock.slept)


def test_inject_truncated_tier1_escalates_to_clipboard(monkeypatch, fake_page):
    _patch_box(monkeypatch, fake_page)
    monkeypatch.setattr(gemini_controller, "time", NoSleepClock())
    fake_page.insert_override = "partial"
    payload = "A" * 40
    assert inject_prompt_via_cdp(fake_page, payload) is True
    assert ["clipboard-read", "clipboard-write"] in fake_page.context.granted_permissions
    assert fake_page.input_value == payload


def test_long_payload_never_reaches_fill_tier(monkeypatch, fake_page):
    _patch_box(monkeypatch, fake_page)
    monkeypatch.setattr(gemini_controller, "time", NoSleepClock())
    fake_page.insert_enabled = False
    fake_page.paste_enabled = False
    fake_page.exec_enabled = False
    result = inject_prompt_via_cdp(fake_page, "x" * 501, fill_limit=500)
    assert result is False
    assert fake_page.fill_called == 0


def test_short_payload_falls_through_to_fill_tier(monkeypatch, fake_page):
    _patch_box(monkeypatch, fake_page)
    monkeypatch.setattr(gemini_controller, "time", NoSleepClock())
    fake_page.insert_enabled = False
    fake_page.paste_enabled = False
    fake_page.exec_enabled = False
    payload = "fill me"
    assert inject_prompt_via_cdp(fake_page, payload) is True
    assert fake_page.fill_called == 1
    assert fake_page.input_value == payload


def test_wait_completion_generating_then_stable(monkeypatch, fake_page):
    fake_page.count_map = {"model-response": 1}
    fake_page.response_text = "Gemini said: Hello world"
    generating_seq = [True, False, False, False]
    monkeypatch.setattr(
        gemini_controller,
        "is_gemini_generating",
        lambda p: generating_seq.pop(0) if generating_seq else False,
    )
    monkeypatch.setattr(gemini_controller, "check_gemini_error_state", lambda p: False)
    monkeypatch.setattr(gemini_controller, "time", NoSleepClock())
    result = wait_for_gemini_turn_completion(
        fake_page, timeout_seconds=5.0, stability_polls=2, poll_interval=0.0
    )
    assert result == "Hello world"


def test_wait_completion_error_card_mid_wait(monkeypatch, fake_page):
    fake_page.count_map = {"model-response": 1}
    fake_page.response_text = "Gemini said: partial answer"
    error_seq = [False, True]
    monkeypatch.setattr(gemini_controller, "is_gemini_generating", lambda p: False)
    monkeypatch.setattr(
        gemini_controller,
        "check_gemini_error_state",
        lambda p: error_seq.pop(0) if error_seq else True,
    )
    monkeypatch.setattr(gemini_controller, "time", NoSleepClock())
    result = wait_for_gemini_turn_completion(
        fake_page, timeout_seconds=5.0, stability_polls=3, poll_interval=0.0
    )
    assert result == ""


def test_wait_completion_timeout_raises(monkeypatch, fake_page):
    fake_page.count_map = {"model-response": 1}
    monkeypatch.setattr(gemini_controller, "is_gemini_generating", lambda p: True)
    monkeypatch.setattr(gemini_controller, "check_gemini_error_state", lambda p: False)
    monkeypatch.setattr(gemini_controller, "time", NoSleepClock())
    with pytest.raises(PlaywrightTimeoutError, match="before DOM stabilized"):
        wait_for_gemini_turn_completion(
            fake_page, timeout_seconds=0.2, stability_polls=3, poll_interval=0.0
        )


def test_jitter_delay_bounds_and_sleep(monkeypatch):
    captured: dict[str, float] = {}

    def fake_uniform(lo: float, hi: float) -> float:
        captured["lo"] = lo
        captured["hi"] = hi
        return 7.25

    slept: list[float] = []
    monkeypatch.setattr(gemini_controller.random, "uniform", fake_uniform)
    monkeypatch.setattr(gemini_controller.time, "sleep", lambda s: slept.append(s))
    result = jitter_delay()
    assert captured == {"lo": 1.5, "hi": 3.0}
    assert result == 7.25
    assert slept == [7.25]


def test_reset_spa_first_avoids_goto(monkeypatch, fake_page):
    new_chat_hit = "button[aria-label*='New chat' i]"
    fake_page.url = GEMINI_APP_URL
    fake_page.count_map = {
        new_chat_hit: 1,
        gemini_controller.RESPONSE_SELECTOR: 0,
    }
    _patch_box(monkeypatch, fake_page)
    monkeypatch.setattr(gemini_controller, "time", NoSleepClock())
    assert reset_chat_session(fake_page) is True
    assert fake_page.goto_calls == []
    assert fake_page.pressed_keys == []


def test_reset_fallback_navigates_when_url_mismatch(monkeypatch, fake_page):
    fake_page.url = "https://example.com/unrelated"
    fake_page.count_map = {gemini_controller.INPUT_BOX_SELECTOR: 1}
    _patch_box(monkeypatch, fake_page)
    monkeypatch.setattr(gemini_controller, "time", NoSleepClock())
    assert reset_chat_session(fake_page) is True
    assert fake_page.goto_calls == [GEMINI_APP_URL]


def test_open_ephemeral_happy_path(monkeypatch, fake_page):
    selected: list[str] = []
    monkeypatch.setattr(gemini_controller, "reset_chat_session", lambda p: True)

    def fake_select(page: object, model_name: str) -> bool:
        selected.append(model_name)
        return True

    monkeypatch.setattr(gemini_controller, "select_gemini_model", fake_select)
    _patch_box(monkeypatch, fake_page)
    monkeypatch.setattr(gemini_controller, "time", NoSleepClock())
    assert open_ephemeral_session(fake_page, "Flash") is True
    assert selected == ["Flash"]


def test_open_ephemeral_reset_failure_propagates(monkeypatch, fake_page):
    selected: list[str] = []
    monkeypatch.setattr(gemini_controller, "reset_chat_session", lambda p: False)
    monkeypatch.setattr(gemini_controller, "select_gemini_model", lambda p, m: selected.append(m))
    assert open_ephemeral_session(fake_page, "Pro") is False
    assert selected == []


def test_open_ephemeral_model_select_soft_fail(monkeypatch, fake_page):
    monkeypatch.setattr(gemini_controller, "reset_chat_session", lambda p: True)
    monkeypatch.setattr(gemini_controller, "select_gemini_model", lambda p, m: False)
    _patch_box(monkeypatch, fake_page)
    monkeypatch.setattr(gemini_controller, "time", NoSleepClock())
    assert open_ephemeral_session(fake_page, "Flash") is True
