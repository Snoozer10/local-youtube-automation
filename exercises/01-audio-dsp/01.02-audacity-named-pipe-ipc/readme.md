# Drill 01.02: Audacity Win32 Named Pipe IPC Protocol

## Objectives
- Master the Win32 Named Pipe communication protocol used by Audacity's `mod-script-pipe`.
- Implement duplex pipe commands to `\\.\pipe\ToSrvPipe` (write) and `\\.\pipe\FromSrvPipe` (read).
- Handle the Audacity command response contract (multiline text terminated by an empty line).
- Verify batch audio processing commands (`SelectAll:`, effect presets, `Export2:`).
- Build pre-flight diagnostics using `@pytest.mark.drill` and `@pytest.mark.skipif` when Audacity daemon is offline.

## Architectural Context
Audacity audio polishing ([`audacity_client.py`](file:///C:/Users/Snoozer/Downloads/Antigravity/Youtube%20Automation%202/buckup/Version%204%20before%20deepseek%20implementation%20plan/image_generation/src/youtube_automation/audio/audacity_client.py)) runs autonomously via named pipes. The Python client opens:
1. `\\.\pipe\ToSrvPipe` for sending commands.
2. `\\.\pipe\FromSrvPipe` for reading status responses.

```
[Python Pipeline]
    │
    ├─ (Write) ──► \\.\pipe\ToSrvPipe ──► [Audacity mod-script-pipe]
    │                                              │
    └─ (Read)  ◄── \\.\pipe\FromSrvPipe ◄──────────┘
```

## Input/Output Contracts
- `is_audacity_pipe_available() -> bool`:
  - Returns `True` if `\\.\pipe\ToSrvPipe` exists and can be probed, `False` otherwise.
- `send_command(write_pipe, read_pipe, command: str) -> str`:
  - Sends `<command>\n`, flushes buffer, reads until a terminating blank line (`""`), and returns the full response string.
- `format_pipe_command(action: str, parameters: dict[str, Any] | None = None) -> str`:
  - Formats commands, e.g. `Import2:Filename="C:\\track.wav"` or `SelectAll:`.

## Drill Variants
- [Detailed Architectural Explainer](explainer/readme.md)
- [Problem Workspace (Student)](problem/exercise.py)
- [Solution Reference](solution/exercise.py)
- [Solution Verification Tests](solution/test_exercise.py)
