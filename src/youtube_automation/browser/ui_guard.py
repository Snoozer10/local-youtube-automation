"""Bounded, fail-safe helpers for transient browser UI obstacles.

Every helper takes a duck-typed Playwright ``page`` so this module never imports Playwright.
Nothing here clicks a button whose label could accept terms, spend money or change an
account: only an allow-listed dismiss label is ever clicked, and Escape is opt-in.
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

OVERLAY_SELECTORS: tuple[str, ...] = (
    ".cdk-overlay-backdrop.cdk-overlay-backdrop-showing",
    "mat-dialog-container",
    "[role='dialog']",
    "[role='alertdialog']",
)
DIALOG_SELECTORS: tuple[str, ...] = OVERLAY_SELECTORS[1:]
_BUTTON_SELECTOR = "button, [role='button']"
_INPUT_SELECTOR = "input, textarea, select"
_OVERLAY_PROBE_FAILED = "overlay visibility probe failed"

SAFE_LABELS = frozenset(
    {
        "close",
        "dismiss",
        "got it",
        "no thanks",
        "not now",
        "maybe later",
        "skip",
    }
)
FORBIDDEN_WORDS: tuple[str, ...] = (
    "accept",
    "agree",
    "allow",
    "continue",
    "upgrade",
    "subscribe",
    "pay",
    "purchase",
    "buy",
    "billing",
    "link",
    "sign in",
    "confirm",
    "delete",
    "trial",
    "understand",
)
FOREIGN_HOSTS = frozenset({"browsermcp.io"})

ProviderErrorKind = Literal["quota", "account", "transient", "unknown"]

_QUOTA_MARKERS: tuple[str, ...] = (
    "403",
    "429",
    "quota",
    "rate limit",
    "too many requests",
    "resource has been exhausted",
    "resource exhausted",
    "paid api key",
    "link a paid",
    "billing",
)
_ACCOUNT_MARKERS: tuple[str, ...] = (
    "sign in",
    "terms of service",
    "consent",
    "verify your",
    "permission denied",
    "not available in your",
)
_TRANSIENT_MARKERS: tuple[str, ...] = (
    "status code: 0",
    "status code: 5",
    " 500",
    " 502",
    " 503",
    " 504",
    "internal error",
    "internal server error",
    "network",
    "timed out",
    "timeout",
    "try again",
    "temporarily unavailable",
    "service unavailable",
)


@dataclass(frozen=True)
class OverlayResult:
    cleared: bool
    actions: tuple[str, ...] = ()
    blocked_by: str | None = None


def _collapse(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _wait(page: Any, milliseconds: float) -> None:
    try:
        page.wait_for_timeout(milliseconds)
    except Exception:
        pass


def _visible_overlay(page: Any) -> str | None:
    """Return a visible selector, confirmed absence, or an error marker if unreadable."""
    probe_failed = False
    max_matches = 32
    for selector in OVERLAY_SELECTORS:
        try:
            matches = page.locator(selector)
            count = int(matches.count())
            if count < 0:
                raise ValueError("negative overlay match count")
            if count > max_matches:
                probe_failed = True
                count = max_matches
            for index in range(count):
                try:
                    if matches.nth(index).is_visible():
                        return selector
                except Exception:
                    probe_failed = True
        except Exception:
            probe_failed = True
    return _OVERLAY_PROBE_FAILED if probe_failed else None


def _blocked_text(page: Any) -> str | None:
    selector = _visible_overlay(page)
    if selector is None:
        return None
    if selector == _OVERLAY_PROBE_FAILED:
        return selector
    text = ""
    for candidate in (*DIALOG_SELECTORS, selector):
        try:
            element = page.locator(candidate).first
            if element.is_visible():
                text = _collapse(element.inner_text(timeout=1000))
                if text:
                    break
        except Exception:
            continue
    return (text or selector)[:200]


def wait_for_overlay_clear(page: Any, timeout_sec: float = 10.0, poll_sec: float = 0.25) -> bool:
    """Poll a bounded number of times until overlay absence is confirmed."""
    poll_sec = max(float(poll_sec), 0.01)
    polls = max(int(float(timeout_sec) / poll_sec), 0)
    for attempt in range(polls + 1):
        if _visible_overlay(page) is None:
            return True
        if attempt < polls:
            _wait(page, poll_sec * 1000)
    return False


def _label(button: Any) -> str:
    for method, args in (("get_attribute", ("aria-label",)), ("inner_text", ())):
        try:
            text = _collapse(getattr(button, method)(*args, timeout=1000)).lower()
        except Exception:
            continue
        if text:
            return text
    return ""


def _is_forbidden(label: str) -> bool:
    return any(word in label for word in FORBIDDEN_WORDS)


def _visible_dialogs(page: Any) -> list[Any]:
    found: list[Any] = []
    for selector in DIALOG_SELECTORS:
        try:
            matches = page.locator(selector)
            for index in range(matches.count()):
                element = matches.nth(index)
                if element.is_visible():
                    found.append(element)
        except Exception:
            continue
    return found


def _dialog_buttons(dialog: Any) -> list[tuple[Any, str]]:
    buttons: list[tuple[Any, str]] = []
    try:
        matches = dialog.locator(_BUTTON_SELECTOR)
        for index in range(matches.count()):
            button = matches.nth(index)
            if button.is_visible():
                buttons.append((button, _label(button)))
    except Exception:
        pass
    return buttons


def _has_inputs(dialog: Any) -> bool:
    try:
        return int(dialog.locator(_INPUT_SELECTOR).count()) > 0
    except Exception:
        return True  # unverifiable: treat as having inputs so Escape is never pressed


def dismiss_safe_overlays(
    page: Any, *, allow_escape: bool = False, max_actions: int = 2
) -> OverlayResult:
    """Click only allow-listed dismiss buttons inside visible dialogs; never a forbidden one."""
    actions: list[str] = []
    for dialog in _visible_dialogs(page):
        if len(actions) >= max_actions:
            break
        buttons = _dialog_buttons(dialog)
        clicked = False
        for button, label in buttons:
            if label in SAFE_LABELS and not _is_forbidden(label):
                try:
                    button.click(timeout=2000)
                except Exception:
                    continue
                actions.append(f"click:{label}")
                clicked = True
                break
        if clicked or not allow_escape or len(actions) >= max_actions:
            continue
        if "escape" in actions:
            continue
        if any(_is_forbidden(label) for _button, label in buttons) or _has_inputs(dialog):
            continue
        try:
            page.keyboard.press("Escape")
        except Exception:
            continue
        actions.append("escape")
    cleared = _visible_overlay(page) is None
    return OverlayResult(
        cleared=cleared,
        actions=tuple(actions),
        blocked_by=None if cleared else _blocked_text(page),
    )


def ensure_clear(page: Any, *, wait_sec: float = 10.0, allow_escape: bool = False) -> OverlayResult:
    """Wait for overlays, then try one safe dismissal; never raises on unknown overlays."""
    try:
        if wait_for_overlay_clear(page, wait_sec):
            return OverlayResult(cleared=True)
        dismissed = dismiss_safe_overlays(page, allow_escape=allow_escape)
        cleared = wait_for_overlay_clear(page, 3.0)
        return OverlayResult(
            cleared=cleared,
            actions=dismissed.actions,
            blocked_by=None if cleared else (_blocked_text(page) or dismissed.blocked_by),
        )
    except Exception as exc:  # defensive: callers rely on this never raising
        return OverlayResult(cleared=False, blocked_by=_collapse(exc)[:200] or "overlay check failed")


def classify_provider_error(text: str) -> ProviderErrorKind:
    """Classify an AI Studio error banner; only "transient" is safe to retry."""
    lowered = f" {_collapse(text).lower()}"
    if not lowered.strip():
        return "unknown"
    if any(marker in lowered for marker in _QUOTA_MARKERS):
        return "quota"
    if any(marker in lowered for marker in _ACCOUNT_MARKERS):
        return "account"
    if any(marker in lowered for marker in _TRANSIENT_MARKERS):
        return "transient"
    return "unknown"


class TargetProbeError(RuntimeError):
    """Redacted failure from the local debugger-target probe."""

    def __init__(self, code: Literal["probe_failed", "invalid_payload"]) -> None:
        self.code = code
        super().__init__(f"debugger target probe {code}")


def foreign_debugger_targets(
    port: int = 9222,
    host: str = "127.0.0.1",
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> list[dict[str, str]]:
    """List foreign debugger tabs; failures raise a redacted typed error."""
    try:
        with opener(f"http://{host}:{int(port)}/json/list", timeout=5) as response:
            raw_payload = response.read().decode("utf-8")
    except Exception:
        raise TargetProbeError("probe_failed") from None

    try:
        targets = json.loads(raw_payload)
        if not isinstance(targets, list):
            raise ValueError("target list must be an array")
        found: list[dict[str, str]] = []
        for target in targets:
            if not isinstance(target, dict):
                raise ValueError("target must be an object")
            kind = target.get("type")
            raw_url = target.get("url")
            if not isinstance(kind, str) or not kind or not isinstance(raw_url, str):
                raise ValueError("target type and URL must be strings")
            if kind not in ("page", "other"):
                continue
            parsed = urlparse(raw_url)
            scheme = (parsed.scheme or "").lower()
            hostname = (parsed.hostname or "").lower()
            if scheme == "chrome-extension" or hostname in FOREIGN_HOSTS:
                found.append({"type": kind, "origin": f"{scheme}://{hostname}"})
        return found
    except Exception:
        raise TargetProbeError("invalid_payload") from None

__all__ = [
    "OverlayResult",
    "TargetProbeError",
    "classify_provider_error",
    "dismiss_safe_overlays",
    "ensure_clear",
    "foreign_debugger_targets",
    "wait_for_overlay_clear",
]
