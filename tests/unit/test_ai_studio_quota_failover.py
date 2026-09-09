"""Unit tests for AI Studio quota error detection and profile failover handling."""

import pytest

from youtube_automation.audio.tts_generator import is_ai_studio_quota_error


class TestAIStudioQuotaDetection:
    """Validates accurate classification of quota/account restrictions vs generic errors."""

    @pytest.mark.parametrize(
        "error_text",
        [
            "Link a paid API key",
            "Please link a paid API key to continue",
            "Link a paid project",
            "Paid API key required",
            "Http response at 400 or 500 level, error: , http status code: 403",
            "status code: 403",
            "Quota Exceeded",
            "quota exceeded for this project",
            "Resource has been exhausted",
            "Rate limit exceeded. Please wait.",
            "Too Many Requests: quota reached",
            "Billing account required",
        ],
    )
    def test_quota_strings_detected(self, error_text):
        assert is_ai_studio_quota_error(error_text) is True

    @pytest.mark.parametrize(
        "error_text",
        [
            "",
            None,
            "500 Internal Server Error",
            "Network connection timed out",
            "Failed to load audio resource",
            "SyntaxError: unexpected token",
        ],
    )
    def test_non_quota_strings_not_detected(self, error_text):
        assert is_ai_studio_quota_error(error_text) is False
