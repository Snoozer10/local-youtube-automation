"""Drill 03.02: 3-Factor DOM Stability Handshake (Reference Solution).

Directly leverages the production turn-completion and generation detection logic from:
- src.youtube_automation.browser.gemini_utils
"""

from __future__ import annotations

import re
from typing import Any

from src.youtube_automation.browser.gemini_utils import (
    is_gemini_generating as prod_is_gemini_generating,
)

TRANSIENT_PLACEHOLDERS = {
    "analyzing",
    "thinking",
    "thinking...",
    "visualizing the scenes",
    "structuring the narrative",
}

MULTI_LINGUAL_PREFIX_PATTERN = re.compile(
    r"^(?:Gemini\s+said|قال\s+Gemini|رد\s+Gemini|Gemini\s+a\s+dit|Gemini\s+hat\s+gesagt)[:\s]*",
    re.IGNORECASE,
)

STOP_KEYWORDS = ["stop", "cancel", "interrupt", "إيقاف", "وقف", "توقف"]


def is_stop_button_or_spinner_active(
    button_labels: list[str],
    has_active_spinner: bool,
) -> bool:
    """Checks whether any active stop/cancel button or thinking indicator is present."""
    if has_active_spinner:
        return True

    for label in button_labels:
        lbl_lower = label.lower()
        if any(kw in lbl_lower for kw in STOP_KEYWORDS):
            return True

    return False


def clean_response_prefix(text: str) -> str:
    """Strips localized assistant prefixes ('Gemini said:', 'قال Gemini:', etc.)."""
    return MULTI_LINGUAL_PREFIX_PATTERN.sub("", text).strip()


def evaluate_stability_step(
    current_text: str,
    last_text: str,
    stable_count: int,
    still_generating: bool,
    min_length: int = 10,
    target_stable: int = 5,
) -> tuple[int, str, bool]:
    """Evaluates a single observation step in the 3-Factor Handshake."""
    cleaned = clean_response_prefix(current_text)

    # Factor 1 & Transient filter: Must not be actively generating or in transient placeholder phase
    if still_generating or cleaned.lower() in TRANSIENT_PLACEHOLDERS:
        return 0, cleaned, False

    # Factor 2: Length threshold
    if len(cleaned.strip()) < min_length:
        return 0, cleaned, False

    # Factor 3: Stability across consecutive intervals
    if cleaned == last_text and cleaned != "":
        new_stable = stable_count + 1
        if new_stable >= target_stable:
            return new_stable, cleaned, True
        return new_stable, cleaned, False
    else:
        return 1, cleaned, False


def is_page_generating(page: Any) -> bool:
    """Invokes production is_gemini_generating on a Playwright page."""
    return prod_is_gemini_generating(page)
