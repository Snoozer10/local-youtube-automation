"""Drill 03.01: CDP Connection & Lifecycle (Reference Solution).

Directly leverages the production CDP client from:
- src.youtube_automation.browser.cdp_client
"""

from __future__ import annotations

from typing import Any

from src.youtube_automation.browser.cdp_client import (
    clean_context_tabs as prod_clean_context_tabs,
)
from src.youtube_automation.browser.cdp_client import (
    is_port_in_use as prod_is_port_in_use,
)
from src.youtube_automation.browser.cdp_client import (
    safe_failover_teardown as prod_safe_failover_teardown,
)
from src.youtube_automation.browser.cdp_client import (
    verify_cdp_port as prod_verify_cdp_port,
)


def is_port_in_use(port: int = 9222, host: str = "127.0.0.1") -> bool:
    """Checks if a local TCP port is actively occupied."""
    return prod_is_port_in_use(port=port, host=host)


def verify_cdp_port(port: int = 9222, host: str = "127.0.0.1", timeout_seconds: float = 2.0) -> bool:
    """Verifies that the Chrome DevTools Protocol endpoint responds over HTTP."""
    return prod_verify_cdp_port(port=port, host=host, timeout_seconds=timeout_seconds)


def clean_context_tabs(context: Any) -> int:
    """Prunes orphaned, blank, or transient pages from browser context and returns closed count."""
    pages_before = len(context.pages)
    prod_clean_context_tabs(context)
    pages_after = len(context.pages)
    return max(0, pages_before - pages_after)


def safe_failover_teardown(
    browser: Any = None,
    context: Any = None,
    port: int = 9222,
    kill_action: Any = None,
) -> list[str]:
    """Gracefully detaches Playwright CDP handles BEFORE terminating browser processes."""
    execution_steps: list[str] = []

    if context:
        execution_steps.append("context.close()")
        try:
            context.close()
        except Exception:
            pass

    if browser:
        execution_steps.append("browser.close()")
        try:
            browser.close()
        except Exception:
            pass

    execution_steps.append(f"kill_process({port})")
    if kill_action:
        kill_action(port)
    else:
        # Delegate to production teardown logic
        prod_safe_failover_teardown(browser=None, context=None, port=port)

    return execution_steps
