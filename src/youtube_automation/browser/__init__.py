"""Browser CDP automation package."""

from .cdp_client import (
    DEFAULT_CDP_HOST,
    DEFAULT_CDP_PORT,
    CDPClient,
    capture_debug_state,
    clean_context_tabs,
    connect_cdp,
    ensure_cdp_browser,
    get_or_create_page,
    is_port_in_use,
    prepare_browser_context,
    safe_failover_teardown,
    verify_cdp_port,
)

__all__ = [
    "CDPClient",
    "DEFAULT_CDP_HOST",
    "DEFAULT_CDP_PORT",
    "capture_debug_state",
    "clean_context_tabs",
    "connect_cdp",
    "ensure_cdp_browser",
    "get_or_create_page",
    "is_port_in_use",
    "prepare_browser_context",
    "safe_failover_teardown",
    "verify_cdp_port",
]
