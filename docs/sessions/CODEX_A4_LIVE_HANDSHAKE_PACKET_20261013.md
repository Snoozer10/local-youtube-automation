# A4 Live Audacity Help Preflight Packet

Status: OFFLINE HARNESS VERIFIED — live execution remains blocked pending a reviewed practical image-inspection receipt producer, end-to-end deadline reconciliation and separate live authorization. This packet authorizes no launch, connection or pipe command.

## Scope and target

- Future target: one specifically owned Audacity process and its verified main window, followed by exactly one read-only pipe command: Help: Command=Help (Windows framing: command bytes + CRLF + NUL).
- Do not invoke _open_ready_audacity_session: it sends Help and SelectAll. The reviewed offline controller is tools/audacity_help_once.py, backed by the separate one-Help worker and parent supervisor. It remains ineligible for live use until the practical inspection producer and end-to-end deadline contract are resolved; this document grants no invocation.
- A future run needs a separate explicit grant for at most one Audacity launch and one Help command. Current turn launch/pipe cap is zero. No SelectAll, DSP, retries, or second command.

## Preflight identity and readiness

The current executable candidate is C:/Program Files/Audacity/Audacity.exe: source lines 809–814 select this first when it exists. It was verified by file stat and SHA-256 for this packet (15,094,056 bytes; SHA-256 300a173a11ebed0d5786e5d5ed984bd812e6e9b944c58c9ae97233e52dbed33f). Re-stat and re-hash this exact canonical executable immediately before any later authorized run; abort on any mismatch. Bind once to the launched process handle; record PID, process creation FILETIME ticks, canonical executable path and executable SHA-256. After launch, verify the live PID still has the same creation FILETIME and image path. PID alone is insufficient. Never attach to a pre-existing/unowned PID or choose a process by window title.

Use the implemented owned-window backend with that PID, FILETIME, and executable identity. Require exactly one visible owned main HWND, stable across three consecutive observations spaced 500 ms apart; every observation must classify as ready, retain the same HWND and process identity, and show no additional visible owned window. Recheck identity immediately before capture and before the command. Any identity/HWND change resets stability; mismatch, enumeration error, inaccessible state, or process exit aborts.

Abort states: recovery_dialog, welcome_dialog, unknown_modal, any non-ready/ambiguous classification, additional visible owned HWND, PID exit/reuse, executable or FILETIME mismatch, observer/capture error, or deadline expiry. Preserve the process and all dialogs/recovery data for inspection. Never click Skip, Discard, Recover, or otherwise dismiss UI.

## Bounded timing and capture

Proposed hard wall-clock budget: 120 seconds total, enforced by a reviewed external supervisor that can terminate the worker and child helper at each phase deadline. Phase caps (sum 120 s): identity bind/stat 5 s; readiness 30 s; owned-HWND screenshot plus pixel inspection 5 s; pipe acquisition 25 s; pre-send guard plus the single Help request/response 35 s (Help response at most 30 s); failure capture 5 s; receipt persistence 5 s; owned-handle/helper cleanup 10 s. The three 500 ms stability intervals fit inside readiness. The legacy pipe opener has an internal 80-second timeout; it must be superseded by an enforced 25-second pipe-acquisition deadline in a reviewed harness before any send. No current enforcement is claimed. If the helper cannot be stopped at phase/outer deadlines, remain blocked.

Capture only the verified main HWND via the native owned-HWND capture backend; no whole-desktop or screen-coordinate capture. Revalidate PID/FILETIME/HWND before and after capture. Planned exclusive evidence directory: .runtime/a4_audacity_handshake_20261013T100625Z/capture/; create a fresh run-specific subdirectory for any later approved attempt, and create each BMP/JSON receipt with exclusive-create semantics (never overwrite). Bind the capture receipt to UTC timestamp, PID, creation FILETIME, executable path/hash, HWND, dimensions, image hash, and capture result. Capture failure or identity drift aborts before any pipe command.

## Exact operator sequence

1. Confirm separate one-launch/one-Help authorization and the reviewed supervisor's hard 120-second kill deadline; otherwise stop.
2. A reviewed harness may Popen the exact stat-pinned C:/Program Files/Audacity/Audacity.exe only once, retaining the owned handle and recording PID/FILETIME/executable in its run-local ownership receipt under the audio resource lease. Do not call the production nested launcher or _open_ready_audacity_session: both invoke Help and SelectAll. Steps 3–7 define the single subsequent sequence; do not execute a second launch or handshake.
3. Observe through the owned-window backend until three stable ready observations or the 30-second cap. Any abort state ends the run with zero pipe commands.
4. Capture the owned main HWND to a fresh exclusive path; inspect the saved pixels and verify the receipt/image hash; re-observe identity/readiness. No pipe may be acquired before this inspection passes.
5. Acquire the owned pipe handles under the enforced 25-second cap; this phase sends zero commands. On timeout/error, close owned handles and stop.
6. Recheck process identity and readiness in the pre-send guard, then send exactly Help: Command=Help once through the reviewed one-command seam; require a complete response within the 35-second phase cap (response at most 30 seconds). Do not run SelectAll or retry.
7. Close owned pipe handles, preserve the process/dialog and all evidence, then seal an outcome receipt within the cleanup cap. Any abort before the send must report pipe command count=0.

## Durable attempt receipts

Write atomic, append-only attempt state receipts for preparing, before_send, sent, result, and stop. Each transition records UTC time, run ID, process identity, phase/deadline, command count, and evidence hashes. before_send must be durable before writing command bytes; sent is recorded only after the one Help write succeeds; result contains the bounded response or error. stop records the exact abort and final command count. If the process dies or state is ambiguous after before_send, do not resend: preserve receipts and stop for review.

## Acceptance evidence

A run can pass only with one launch, the exact bound process identity, one stable main HWND, three ready observations, a valid owned-HWND image receipt, exactly one Help command, a complete Help response before all deadlines, and zero other commands. Any missing receipt, timeout, state ambiguity, or extra command fails closed. Passing this handshake proves only current owned-window readiness plus one Help response; it does not prove Audacity DSP, audio correctness, or historical failure causality.

## Current-turn evidence

Offline A1–A3 report: .runtime/codex_audacity_readiness_20261013T093350Z/VERIFICATION_REPORT.md records 62 focused offline tests passed; live/native GUI behavior remains unverified. This planning turn performed no process launch, native API call, pipe connection, screenshot, test, or provider/network call. The repository interpreter stat is venv/Scripts/python.exe (274712 bytes; stat only). The Audacity executable candidate above was statted and hashed; it was not launched, and no live process identity was bound. Recheck the executable path/stat/hash for the future run.

Evidence SHA-256 pins (bytes and UTC mtimes are in the adjacent A4_PACKET_RECEIPT.json): core/audacity_windows.py 30be526e2456b510bc07192447e29d68fe65b42f6625925abf5a13227d5b8beb; core/window_readiness.py c103ad7a15d62d56f492518e204e3993dd331ec8dc1c25cab7808eb443f92f9d; audio/audacity_client.py 1121bae702b47f42d8a627f78d2d712fb74e96804abae5f784eb3dc4d96b6db4; offline verification report b79d2dd6270db80d9571ce82e3faaa343b054cffe398ace37010be0ed77ee626.

## Offline implementation checkpoint — 2026-10-13

The one-Help supervisor now exists in `src/youtube_automation/core/process_supervisor.py`, `src/youtube_automation/audio/audacity_readiness_probe.py` and `tools/audacity_help_once.py`. Earlier “runner absent” language above describes the pre-implementation checkpoint; it is superseded by this section. Current evidence: `.runtime/codex_a4_supervisor_20261013T103126Z/VERIFICATION_REPORT.md`, `CODE_PINS.json` and `TEST_ATTEMPT_03_EXIT.json`.95 mocked tests pass; no live/native invocation occurred.

Current blocker: the controller awaits a current image-bound `capture/inspection.json` receipt within the5s capture phase; its practical producer is not configured. The parent enforces a120s worker watchdog and25s pipe acquisition;250ms reap and receipt filesystem I/O may follow that watchdog. Strict end-to-end completion within120s is not established, so the proposed overall packet budget must be reconciled before live approval. A4 remains gated and its cap remains0.
