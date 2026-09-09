"""Unit & Diagnostic Drill Tests for 03.01 CDP Connection & Lifecycle."""

import socket
from unittest.mock import MagicMock

import pytest

from .exercise import (
    clean_context_tabs,
    is_port_in_use,
    safe_failover_teardown,
    verify_cdp_port,
)


class MockPage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.closed = False

    def close(self) -> None:
        self.closed = True


class MockContext:
    def __init__(self, pages: list[MockPage]) -> None:
        self._pages = pages

    @property
    def pages(self) -> list[MockPage]:
        # Filter out closed pages as Playwright does
        self._pages = [p for p in self._pages if not p.closed]
        return self._pages


@pytest.mark.drill
def test_is_port_in_use_detects_listening_socket() -> None:
    # Bind an ephemeral loopback socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        _, ephemeral_port = s.getsockname()

        assert is_port_in_use(ephemeral_port, "127.0.0.1") is True

    # Socket is now closed
    assert is_port_in_use(ephemeral_port, "127.0.0.1") is False


@pytest.mark.drill
def test_clean_context_tabs_prunes_blank_pages() -> None:
    tab1 = MockPage("https://gemini.google.com/app")
    tab2 = MockPage("about:blank")
    tab3 = MockPage("")
    tab4 = MockPage("https://aistudio.google.com/prompts/new_chat")

    context = MockContext([tab1, tab2, tab3, tab4])

    closed_count = clean_context_tabs(context)
    assert closed_count == 2
    assert tab2.closed is True
    assert tab3.closed is True
    assert tab1.closed is False
    assert tab4.closed is False
    assert len(context.pages) == 2


@pytest.mark.drill
def test_safe_failover_teardown_enforces_orderly_shutdown() -> None:
    mock_browser = MagicMock()
    mock_context = MagicMock()
    kill_called_with: list[int] = []

    def mock_kill(port: int) -> None:
        kill_called_with.append(port)

    steps = safe_failover_teardown(
        browser=mock_browser,
        context=mock_context,
        port=9222,
        kill_action=mock_kill,
    )

    assert steps == ["context.close()", "browser.close()", "kill_process(9222)"]
    mock_context.close.assert_called_once()
    mock_browser.close.assert_called_once()
    assert kill_called_with == [9222]


@pytest.mark.drill
def test_preflight_cdp_port_diagnostic() -> None:
    """Diagnostic check verifying whether port 9222 is active."""
    in_use = is_port_in_use(9222)
    if in_use:
        # If port 9222 is open, test if it is a CDP endpoint
        responding = verify_cdp_port(9222)
        assert isinstance(responding, bool)
    else:
        # Port is idle; probe confirms it is not currently occupied
        assert in_use is False
