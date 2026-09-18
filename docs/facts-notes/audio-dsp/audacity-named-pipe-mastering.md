# Note: Audacity Win32 Named Pipe Batch Mastering

**Category:** Audio DSP  
**Date Logged:** 2026-09-17  
**Relevant Code Files:** src/youtube_automation/audio/audacity_client.py, utomate_audacity.py  
**Audit Reference:** Phase 4 Audacity DSP Mastering  

### 1. Core Rule in Plain English
Audacity automation via Win32 Named Pipes (\\.\pipe\ToSrvPipe and \\.\pipe\FromSrvPipe) must always use a single persistent session with automated mod-script-pipe=1 config injection, SessionData cleanup before launch, and explicit track clearing (SelectAll: followed by RemoveTracks:) between chapter processing runs.

### 2. The Failure Mode It Prevents
Spawning a new Audacity instance per audio chapter causes process handle starvation, stale socket locks, recovery popups on crash recovery (SessionData), and unclosed pipe deadlocks on Windows CRT. Furthermore, omitting mod-script-pipe=1 causes pipe connection failure.

### 3. Implementation Specification
`python
# Enable pipe in audacity.cfg
if 'mod-script-pipe=1' not in content:
    content += '\n[Modules]\nmod-script-pipe=1\n'

# Send command and parse BatchCommand finished
def send_audacity_command(write_pipe, read_pipe, command):
    write_pipe.write(command + '\n')
    write_pipe.flush()
    response = ''
    while True:
        line = read_pipe.readline()
        if not line:
            break
        response += line
        if 'BatchCommand finished' in line:
            ...
`

### 4. Verification Check
Run python -m pytest tests/unit/test_audacity_pipe_protocol.py -v and inspect that all 10 polished chapter WAV files exist with non-zero duration and valid 44.1kHz 16-bit PCM headers.\n