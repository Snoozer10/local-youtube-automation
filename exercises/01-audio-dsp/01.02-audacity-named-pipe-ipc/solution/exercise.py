"""Drill 01.02: Audacity Win32 Named Pipe IPC Protocol (Reference Solution).

Directly leverages the production Audacity automation client from:
- src.youtube_automation.audio.audacity_client
"""

from __future__ import annotations

import os
import sys
from typing import Any

from src.youtube_automation.audio.audacity_client import (
    ensure_audacity_script_pipe_enabled,
)
from src.youtube_automation.audio.audacity_client import (
    send_audacity_command as prod_send_audacity_command,
)

TO_SRV_PIPE = r"\\.\pipe\ToSrvPipe"
FROM_SRV_PIPE = r"\\.\pipe\FromSrvPipe"


def is_audacity_pipe_available() -> bool:
    """Probes if Audacity's inbound Named Pipe is available on Windows."""
    if not sys.platform.startswith("win"):
        return False

    if not os.path.exists(TO_SRV_PIPE):
        return False

    try:
        # Quick non-blocking probe
        with open(TO_SRV_PIPE, "r+"):
            return True
    except Exception:
        return False


def format_audacity_command(action: str, params: dict[str, Any] | None = None) -> str:
    """Formats an Audacity scripting command with parameter key-value pairs."""
    action_clean = action.strip().rstrip(":")
    if not params:
        return f"{action_clean}:"

    parts: list[str] = []
    for key, val in params.items():
        if isinstance(val, str):
            # Escape internal backslashes for Audacity path parsing
            escaped_val = val.replace("\\", "\\\\")
            parts.append(f'{key}="{escaped_val}"')
        else:
            parts.append(f"{key}={val}")

    return f"{action_clean}:" + " ".join(parts)


def send_audacity_command(write_pipe: Any, read_pipe: Any, command: str) -> str:
    """Sends a single scripting command and reads response until empty line."""
    return prod_send_audacity_command(write_pipe, read_pipe, command)


def execute_batch_effects(
    write_pipe: Any,
    read_pipe: Any,
    effects: list[str],
) -> list[str]:
    """Executes an ordered list of effect commands, selecting all audio before each effect."""
    responses: list[str] = []
    for effect in effects:
        effect_cmd = effect.strip()
        if not effect_cmd or effect_cmd.startswith("#"):
            continue

        send_audacity_command(write_pipe, read_pipe, "SelectAll:")
        resp = send_audacity_command(write_pipe, read_pipe, effect_cmd)
        responses.append(resp)

    return responses


def configure_audacity_pipe_environment() -> None:
    """Ensures Audacity configuration file enables mod-script-pipe."""
    ensure_audacity_script_pipe_enabled()
