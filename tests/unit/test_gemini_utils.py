import logging
import subprocess
import time

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

    def wait_for_timeout(self, timeout_ms: float) -> None:
        pass


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


# ==============================================================================
# Deterministic Test Harness for Visible-Response Completion & Stop Detection
# ==============================================================================

class _FakeResponseElement:
    def __init__(self, text: str):
        self.text = text

    def evaluate(self, expr: str, **_kwargs) -> str:
        return self.text


class _FakeResponseLocator:
    def __init__(self, responses: list[str]):
        self._responses = responses

    def count(self) -> int:
        return len(self._responses)

    def nth(self, idx: int) -> _FakeResponseElement:
        if 0 <= idx < len(self._responses):
            return _FakeResponseElement(self._responses[idx])
        return _FakeResponseElement("")

    @property
    def last(self) -> _FakeResponseElement:
        if self._responses:
            return _FakeResponseElement(self._responses[-1])
        return _FakeResponseElement("")


class _FakeErrorElement:
    def is_visible(self) -> bool:
        return True


class _FakeErrorLocator:
    def __init__(self, is_active: bool):
        self._active = is_active

    def count(self) -> int:
        return 1 if self._active else 0

    @property
    def first(self) -> _FakeErrorElement:
        return _FakeErrorElement()


class FakeDomElement:
    def __init__(
        self,
        tag: str = "button",
        aria_label: str = "",
        text: str = "",
        visible: bool = True,
        attributes: dict[str, str] | None = None,
    ):
        self.tag = tag.lower()
        self.aria_label = aria_label
        self.text = text
        self.visible = visible
        self.attributes = attributes or {}


class FakeGeminiResponsePage:
    """Deterministic fake of Playwright Page for Gemini response completion detection."""

    def __init__(
        self,
        responses: list[str] | None = None,
        stop_control_active: bool = False,
        error_active: bool = False,
        stop_sequence: list[bool] | None = None,
        response_sequence: list[list[str]] | None = None,
        error_sequence: list[bool] | None = None,
        stop_control_fn: object | None = None,
        dom_elements: list[FakeDomElement] | None = None,
        sleep_on_wait: bool = True,
    ):
        self.responses = list(responses) if responses is not None else []
        self.stop_control_active = stop_control_active
        self.error_active = error_active
        self.stop_sequence = list(stop_sequence) if stop_sequence is not None else None
        self.response_sequence = (
            [list(r) for r in response_sequence] if response_sequence is not None else None
        )
        self.error_sequence = list(error_sequence) if error_sequence is not None else None
        self.stop_control_fn = stop_control_fn
        self.dom_elements = list(dom_elements) if dom_elements is not None else None
        self.sleep_on_wait = sleep_on_wait
        self.evaluate_calls: list[str] = []
        self.timeout_waits: list[float] = []

    def wait_for_timeout(self, timeout_ms: float) -> None:
        self.timeout_waits.append(timeout_ms)
        if self.sleep_on_wait and timeout_ms > 0:
            time.sleep(min(timeout_ms / 1000.0, 0.02))

    def locator(self, selector: str):
        if selector == gemini_utils.RESPONSE_SELECTOR:
            if self.response_sequence:
                self.responses = self.response_sequence.pop(0)
            return _FakeResponseLocator(self.responses)
        error_selectors = [
            "div[data-test-id='error-message']",
            ".error-card",
            "button:has-text('Try again')",
            "button:has-text('إعادة المحاولة')",
            "div:has-text('Something went wrong')",
            "div:has-text('حدث خطأ ما')",
        ]
        if selector in error_selectors:
            if self.error_sequence:
                self.error_active = self.error_sequence.pop(0)
            return _FakeErrorLocator(self.error_active)
        return _FakeResponseLocator([])

    def _evaluate_dom_elements(self) -> bool:
        if self.dom_elements is None:
            return False
        for el in self.dom_elements:
            if not el.visible:
                continue
            label = el.aria_label.lower()
            if any(kw in label for kw in gemini_utils.EXCLUDED_AUDIO_PLAYBACK_KEYWORDS):
                continue
            if el.tag in gemini_utils.FORBIDDEN_BROAD_SELECTORS:
                continue
            for sel in gemini_utils.STOP_GENERATING_SELECTORS:
                if "aria-label" in sel:
                    target = sel.split("'")[1].lower() if "'" in sel else ""
                    if target and target in label:
                        return True
                elif "data-test-id" in sel:
                    target_id = sel.split("'")[1] if "'" in sel else ""
                    if el.attributes.get("data-test-id") == target_id:
                        return True
                elif sel.startswith("button."):
                    cls = sel.split(".")[1]
                    if el.tag == "button" and el.attributes.get("class") == cls:
                        return True
            if el.tag in ("button", "a") or el.attributes.get("role") == "button":
                text_clean = el.text.strip().lower()
                if text_clean in gemini_utils.STOP_TEXT_KEYWORDS:
                    return True
        return False

    def evaluate(self, script: str, **kwargs):
        self.evaluate_calls.append(script)
        if self.stop_control_fn is not None and callable(self.stop_control_fn):
            return self.stop_control_fn()
        if self.dom_elements is not None:
            return self._evaluate_dom_elements()
        if self.stop_sequence:
            self.stop_control_active = self.stop_sequence.pop(0)
        return self.stop_control_active


def test_regression_1_new_response_stable_and_stop_disappears():
    """1. A new response appears, becomes stable, and the real Stop control disappears: return it."""
    page = FakeGeminiResponsePage(
        responses=["Old turn 1", "Gemini said: Completed educational video plan."],
        stop_sequence=[True, False, False, False, False],
    )
    result = gemini_utils.wait_for_gemini_response(
        page,
        initial_count=1,
        min_length=5,
        timeout_seconds=5.0,
        stability_polls=3,
        poll_interval=0.01,
    )
    assert result == "Completed educational video plan."
    assert len(page.timeout_waits) > 0


def test_regression_2_unrelated_decorative_spinner_does_not_block():
    """2. An unrelated decorative spinner remains visible: still return the stable response."""
    page = FakeGeminiResponsePage(
        responses=["Old turn 1", "Completed plan without active stop button."],
        dom_elements=[
            FakeDomElement(tag="mat-progress-spinner", visible=True),
            FakeDomElement(tag="mat-progress-bar", visible=True),
            FakeDomElement(tag="button", aria_label="Stop audio", text="Stop", visible=True),
            FakeDomElement(tag="button", aria_label="Stop playback", text="Stop", visible=True),
        ],
    )
    result = gemini_utils.wait_for_gemini_response(
        page,
        initial_count=1,
        min_length=5,
        timeout_seconds=5.0,
        stability_polls=3,
        poll_interval=0.01,
    )
    assert result == "Completed plan without active stop button."


def test_regression_3_real_stop_control_remains_visible_continues_waiting():
    """3. The real Stop-generating control remains visible: continue waiting."""
    page = FakeGeminiResponsePage(
        responses=["Old turn 1", "Draft text that should not return while stop button is visible"],
        stop_control_active=True,
    )
    result = gemini_utils.wait_for_gemini_response(
        page,
        initial_count=1,
        min_length=5,
        timeout_seconds=0.05,
        stability_polls=2,
        poll_interval=0.01,
    )
    assert result == ""


def test_regression_4_response_text_growing_does_not_return_early():
    """4. Response text continues growing: do not return early."""
    response_stream = [
        ["Old turn 1", "Part 1"],
        ["Old turn 1", "Part 1 Part 2"],
        ["Old turn 1", "Part 1 Part 2 Part 3"],
        ["Old turn 1", "Part 1 Part 2 Part 3 Part 4"],
        ["Old turn 1", "Part 1 Part 2 Part 3 Part 4 Final"],
        ["Old turn 1", "Part 1 Part 2 Part 3 Part 4 Final"],
        ["Old turn 1", "Part 1 Part 2 Part 3 Part 4 Final"],
    ]
    page = FakeGeminiResponsePage(
        response_sequence=response_stream,
        stop_control_active=False,
    )
    result = gemini_utils.wait_for_gemini_response(
        page,
        initial_count=1,
        min_length=5,
        timeout_seconds=5.0,
        stability_polls=3,
        poll_interval=0.01,
    )
    assert result == "Part 1 Part 2 Part 3 Part 4 Final"


def test_regression_5_only_old_response_at_baseline_count_does_not_return():
    """5. Only an old response exists at the baseline count: do not return it."""
    page = FakeGeminiResponsePage(
        responses=["Old turn 1 that should never be returned as new turn"],
        stop_control_active=False,
    )
    result = gemini_utils.wait_for_gemini_response(
        page,
        initial_count=1,
        min_length=5,
        timeout_seconds=0.05,
        stability_polls=2,
        poll_interval=0.01,
    )
    assert result == ""


def test_regression_6_gemini_shows_error_card_preserves_behavior():
    """6. Gemini shows an error card: preserve current error behavior."""
    page = FakeGeminiResponsePage(
        responses=["Old turn 1", "Some partial text before network drop"],
        error_active=True,
    )
    result = gemini_utils.wait_for_gemini_response(
        page,
        initial_count=1,
        min_length=5,
        timeout_seconds=5.0,
        stability_polls=3,
        poll_interval=0.01,
    )
    assert result == ""


def test_regression_7_response_completes_on_final_timeout_boundary_observation():
    """7. The response completes on the final timeout-boundary observation: return it instead of raising a false timeout."""
    # Text is stable for 3 polls while stop button is visible; at boundary stop button disappears
    eval_calls = 0

    def dynamic_stop():
        nonlocal eval_calls
        eval_calls += 1
        return eval_calls < 4

    page = FakeGeminiResponsePage(
        responses=["Old turn 1", "Answer completed right at boundary."],
        stop_control_fn=dynamic_stop,
    )
    result = gemini_utils.wait_for_gemini_response(
        page,
        initial_count=1,
        min_length=5,
        timeout_seconds=0.04,
        stability_polls=3,
        poll_interval=0.01,
    )
    assert result == "Answer completed right at boundary."


def test_regression_timeout_boundary_rejects_insufficient_stability_polls():
    """Timeout boundary must NOT accept single equality when stability_polls requires >= 2."""
    # Text keeps changing across polls up to boundary; only 1 poll of equality at boundary
    stream = [["Old turn 1", f"Draft text version {i}"] for i in range(1, 20)]
    page = FakeGeminiResponsePage(
        response_sequence=stream,
        stop_control_active=False,
    )
    result = gemini_utils.wait_for_gemini_response(
        page,
        initial_count=1,
        min_length=5,
        timeout_seconds=0.03,
        stability_polls=3,
        poll_interval=0.01,
    )
    assert result == ""


def test_phase1_boundary_response_mounts_at_final_observation():
    """Response node appears only during final phase-one boundary observation: transitions to phase 2."""
    poll_calls = 0

    class _BoundaryPhase1Page(FakeGeminiResponsePage):
        def locator(self, selector: str):
            nonlocal poll_calls
            if selector == gemini_utils.RESPONSE_SELECTOR:
                poll_calls += 1
                if poll_calls < 4:
                    return _FakeResponseLocator(["Old turn 1"])
                return _FakeResponseLocator(["Old turn 1", "Completed response mounted at boundary."])
            return super().locator(selector)

    page = _BoundaryPhase1Page(stop_control_active=False)
    result = gemini_utils.wait_for_gemini_response(
        page,
        initial_count=1,
        min_length=5,
        timeout_seconds=5.0,
        stability_polls=2,
        poll_interval=0.01,
    )
    assert result == "Completed response mounted at boundary."


def test_wait_for_gemini_response_uses_wait_for_timeout_not_sleep(monkeypatch):
    """Verify LEARNING-008: polling loop calls page.wait_for_timeout and never bare time.sleep."""
    sleep_calls = []
    monkeypatch.setattr(gemini_utils.time, "sleep", lambda s: sleep_calls.append(s))

    page = FakeGeminiResponsePage(
        responses=["Old turn 1", "Completed without bare sleep."],
        stop_sequence=[True, False, False, False],
        sleep_on_wait=False,
    )
    result = gemini_utils.wait_for_gemini_response(
        page,
        initial_count=1,
        min_length=5,
        timeout_seconds=5.0,
        stability_polls=2,
        poll_interval=0.01,
    )
    assert result == "Completed without bare sleep."
    assert len(sleep_calls) == 0, f"Bare time.sleep was called inside polling loop: {sleep_calls}"
    assert len(page.timeout_waits) > 0


def test_regression_8_truly_incomplete_response_still_times_out():
    """8. A truly incomplete response still times out."""
    page = FakeGeminiResponsePage(
        responses=["Old turn 1", "Incomplete streaming text..."],
        stop_control_active=True,
    )
    result = gemini_utils.wait_for_gemini_response(
        page,
        initial_count=1,
        min_length=5,
        timeout_seconds=0.03,
        stability_polls=3,
        poll_interval=0.01,
    )
    assert result == ""


def test_diagnostic_logging_never_exposes_prompt_or_response_contents(caplog):
    """Structured diagnostic logging contains telemetry counts/states but never prompt/response text."""
    secret_text = "SECRET_PROPRIETARY_PAYLOAD_987654321"
    page = FakeGeminiResponsePage(
        responses=["Old turn 1", secret_text],
        stop_sequence=[True, False, False, False],
    )
    with caplog.at_level(logging.INFO):
        result = gemini_utils.wait_for_gemini_response(
            page,
            initial_count=1,
            min_length=5,
            timeout_seconds=5.0,
            stability_polls=2,
            poll_interval=0.01,
        )
    assert result == secret_text

    detector_logs = [r.message for r in caplog.records if "[gemini_detector]" in r.message]
    assert len(detector_logs) > 0
    for log_msg in detector_logs:
        assert "baseline_count=" in log_msg
        assert "new_count=" in log_msg
        assert "gen_control=" in log_msg
        assert "stable_polls=" in log_msg
        assert "response_len=" in log_msg
        assert "decision=" in log_msg
        assert secret_text not in log_msg


def test_is_gemini_stop_control_visible_delegates_to_page_evaluate():
    page = FakeGeminiResponsePage(stop_control_active=True)
    assert gemini_utils.is_gemini_stop_control_visible(page) is True
    assert gemini_utils.is_gemini_generating(page) is True

    page.stop_control_active = False
    assert gemini_utils.is_gemini_stop_control_visible(page) is False
    assert gemini_utils.is_gemini_generating(page) is False


def test_is_gemini_stop_control_visible_handles_exceptions_gracefully():
    class _ErrorPage:
        def evaluate(self, _script: str):
            raise RuntimeError("CDP target detached")

    assert gemini_utils.is_gemini_stop_control_visible(_ErrorPage()) is False
    assert gemini_utils.is_gemini_generating(_ErrorPage()) is False


def test_forbidden_broad_selectors_absent():
    """Forbidden broad selectors must never appear in canonical policy or STOP_CONTROL_CHECK_JS."""
    for forbidden in gemini_utils.FORBIDDEN_BROAD_SELECTORS:
        assert forbidden not in gemini_utils.STOP_GENERATING_SELECTORS
        assert forbidden not in gemini_utils.STOP_CONTROL_CHECK_JS


def test_semantic_stop_selectors_and_audio_exclusion():
    """Canonical collection has semantic stop selectors and excludes audio/playback controls."""
    assert any("Stop generating" in sel for sel in gemini_utils.STOP_GENERATING_SELECTORS)
    assert any("Stop response" in sel for sel in gemini_utils.STOP_GENERATING_SELECTORS)
    assert any("إيقاف الإنشاء" in sel for sel in gemini_utils.STOP_GENERATING_SELECTORS)
    assert any("stop-button" in sel for sel in gemini_utils.STOP_GENERATING_SELECTORS)

    for kw in ("audio", "playback", "listen", "صوت"):
        assert kw in gemini_utils.EXCLUDED_AUDIO_PLAYBACK_KEYWORDS
        assert kw in gemini_utils.STOP_CONTROL_CHECK_JS


def test_stop_control_check_js_runtime_execution():
    """Run STOP_CONTROL_CHECK_JS with Node to verify JS execution against simulated DOM."""
    js_test_script = f"""
    const fn = ({gemini_utils.STOP_CONTROL_CHECK_JS});

    function runWith(elements) {{
        global.document = {{
            querySelectorAll: (sel) => {{
                return elements.filter(el => {{
                    if (sel === "button, [role='button']") {{
                        return el.tag === 'button' || el.role === 'button';
                    }}
                    if (sel.startsWith('button[aria-label')) {{
                        return el.tag === 'button' && el.ariaLabel && el.ariaLabel.toLowerCase().includes('stop');
                    }}
                    if (sel.includes("data-test-id='stop-button'")) {{
                        return el['data-test-id'] === 'stop-button';
                    }}
                    return el.tag === sel;
                }}).map(el => ({{
                    offsetParent: el.visible !== false ? 1 : null,
                    getAttribute: (attr) => el[attr] || (attr === 'aria-label' ? el.ariaLabel : null),
                    innerText: el.text || ''
                }}));
            }}
        }};
        return fn();
    }}

    const tests = [
        runWith([{{ tag: 'mat-progress-spinner' }}]) === false,
        runWith([{{ tag: 'mat-progress-bar' }}]) === false,
        runWith([{{ tag: 'button', ariaLabel: 'Stop audio', text: 'Stop' }}]) === false,
        runWith([{{ tag: 'button', ariaLabel: 'Stop playback', text: 'Stop' }}]) === false,
        runWith([{{ tag: 'button', ariaLabel: 'إيقاف الصوت', text: 'إيقاف' }}]) === false,
        runWith([{{ tag: 'button', ariaLabel: 'Stop generating' }}]) === true,
        runWith([{{ tag: 'button', ariaLabel: 'Stop response' }}]) === true,
        runWith([{{ tag: 'button', 'data-test-id': 'stop-button' }}]) === true,
        runWith([{{ tag: 'button', text: 'Stop' }}]) === true,
        runWith([{{ tag: 'button', text: 'إيقاف الإنشاء' }}]) === true,
    ];

    if (!tests.every(Boolean)) {{
        console.error('JS test failed', tests);
        process.exit(1);
    }}
    console.log('ALL_JS_TESTS_PASSED');
    """

    res = subprocess.run(
        ["node", "-e", js_test_script],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ALL_JS_TESTS_PASSED" in res.stdout
