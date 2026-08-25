"""Unit tests: Gemini response stability polling (mocked Playwright objects)."""


from mocks.fake_gemini import FakeLocator, FakePage

import gemini_utils


class TestWaitForGeminiResponse:
    def test_stable_text_returned_after_stability_window(self, monkeypatch):
        page = FakePage(response_locator=FakeLocator(count=2, text="الجواب النهائي الكامل"))
        sleeps = []

        class FakeTime:
            base = 1000.0

            @classmethod
            def time(cls):
                return cls.base

        monkeypatch.setattr(gemini_utils.time, "time", FakeTime.time)
        real_sleep = gemini_utils.time.sleep
        monkeypatch.setattr(
            gemini_utils.time, "sleep",
            lambda s: (sleeps.append(s), setattr(FakeTime, "base", FakeTime.base + 0.3)),
        )
        try:
            result = gemini_utils.wait_for_gemini_response(page, initial_count=1, min_length=5)
        finally:
            monkeypatch.setattr(gemini_utils.time, "sleep", real_sleep)
        assert result == "الجواب النهائي الكامل"
        assert len(sleeps) >= 4  # multiple stability samples required

    def test_error_card_fast_fails_to_empty(self):
        page = FakePage(error_visible=True)
        result = gemini_utils.wait_for_gemini_response(page, initial_count=0, timeout_seconds=10)
        assert result == ""

    def test_timeout_returns_empty_string(self, monkeypatch):
        # Response node never mounts; clock advances past timeout instantly.
        page = FakePage(response_locator=FakeLocator(count=0))

        class FakeTime:
            base = 0.0

            @classmethod
            def time(cls):
                cls.base += 45.0  # blow past both 90s start window and timeout
                return cls.base

        monkeypatch.setattr(gemini_utils.time, "time", FakeTime.time)
        monkeypatch.setattr(gemini_utils.time, "sleep", lambda s: None)
        result = gemini_utils.wait_for_gemini_response(
            page, initial_count=0, timeout_seconds=30
        )
        assert result == ""


class TestCheckGeminiErrorState:
    def test_no_error_selectors_visible(self):
        page = FakePage()
        assert gemini_utils.check_gemini_error_state(page) is False

    def test_error_card_detected(self):
        page = FakePage(error_visible=True)
        assert gemini_utils.check_gemini_error_state(page) is True


class TestIsGeminiGenerating:
    def test_idle_when_no_indicators(self):
        page = FakePage(generating=False)
        assert gemini_utils.is_gemini_generating(page) is False

    def test_generating_when_spinner_present(self):
        page = FakePage(generating=True)
        assert gemini_utils.is_gemini_generating(page) is True
