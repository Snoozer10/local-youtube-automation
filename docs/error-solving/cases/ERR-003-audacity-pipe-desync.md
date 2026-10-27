# Case ID: ERR-003-audacity-pipe-desync

## Overview
- **Title**: Audacity Named Pipe Leading Newline Protocol Framing Desynchronization
- **Responsible Layer**: audio.pipe
- **Status**: resolved
- **Date Recorded**: 2026-10-23
- **Affected Components**: Audacity pipe-server client (`audacity_client.py`), batch command execution

## 1. Verified Facts
- Audacity 3.x `mod-script-pipe` C++ module formats batch command replies as:
  `mOutput += wxT("\nBatchCommand finished: ") + status + wxT("\n\n")`.
- When a command has no intermediate text output (e.g. `Import2:`, `SelectAll:`, or filter actions), Audacity sends a leading empty newline (`\n`) as the very first byte.
- Naive loop breaking on `if line.strip() == "": break` terminates immediately on the leading `\n`, leaving `BatchCommand finished: OK\n\n` unconsumed in the named pipe buffer.
- Subsequent pipe reads consume stale leftover lines, causing total command framing desynchronization and eventual deadlock in `read_pipe.readline()`.

## 2. Hypotheses
- Protocol parser mistakenly assumed leading whitespace was impossible and treated any blank line as an end-of-message delimiter instead of parsing the explicit protocol sentinel.
- Confidence: high.

## 3. Attempts and Outcomes
- **Attempt 1**: Add an arbitrary sleep (`time.sleep(0.1)`) before reading.
  - *Outcome*: Flaky, did not resolve buffer desynchronization.
- **Attempt 2**: Loop continuously until `BatchCommand finished: <status>` is explicitly parsed, followed by the terminating blank line.
  - *Outcome*: Succeeded. Pipe synchronization is 100% deterministic across all commands.

## 4. Remaining Gaps & False-Positive Boundaries
- **Boundaries**: Applies exclusively to Audacity `mod-script-pipe` IPC. Does not apply to standard CLI subprocess pipes or HTTP endpoints.
- **Gaps**: None.

## 5. Verified Prevention Check
- **Rule / Guard**: Always parse up to the authoritative completion sentinel `BatchCommand finished:` and terminal blank boundary.
- **Verification**: `tests/unit/test_audacity_client.py` and `src/youtube_automation/audio/audacity_client.py`

## 6. Evidence Links
- **Legacy Register**: [`docs/error-solving/understood-errors.md#audacity-named-pipe-leading-newline-protocol-framing-desynchronization`](../understood-errors.md)
- **Source Code**: [`src/youtube_automation/audio/audacity_client.py`](../../../src/youtube_automation/audio/audacity_client.py)
