# Explainer: Audacity Win32 Named Pipe IPC

## 1. Win32 Named Pipes Architecture
Audacity's `mod-script-pipe` is a native C++ module that hosts two named pipes under the Windows named pipe filesystem namespace (`\\.\pipe\`):
- `\\.\pipe\ToSrvPipe`: Server inbound (client write).
- `\\.\pipe\FromSrvPipe`: Server outbound (client read).

Under standard Python on Windows, these pipes can be opened using standard file I/O:
```python
write_pipe = open(r"\\.\pipe\ToSrvPipe", "w", encoding="utf-8")
read_pipe = open(r"\\.\pipe\FromSrvPipe", "r", encoding="utf-8")
```

## 2. Command Termination & Response Framing
Every command sent to Audacity must be terminated with a newline (`\n`).
Audacity executes the command synchronously and transmits status lines back over `FromSrvPipe`.
The protocol marks completion by transmitting an empty line (`\n` or `\r\n`):
```text
[Pipe Send]: SelectAll:
[Pipe Response]:
BatchCommand finished: OK
<empty line>
```
If the client does not read until the empty line terminator, subsequent command responses will be desynchronized, causing catastrophic pipeline failures.

## 3. Pre-Flight Diagnostic Probing
In continuous integration or headless test runners, Audacity may not be running.
The pre-flight drill must:
1. Probe whether the named pipe exists without hanging the process.
2. In mock tests: simulate the duplex pipe pair to verify protocol framing.
3. In hardware drill runs: probe real hardware and skip with `@pytest.mark.skipif` if Audacity is not currently active.

## 4. Cold-Boot Polling Window & Module Initialization
On Windows systems where Audacity 3.x is cold-booted via subprocess (`subprocess.Popen([executable_path])`), wxWidgets and the dynamic `mod-script-pipe` module require 10–20 seconds to initialize the pipe server.
A naive 3s grace + 15s polling window prematurely fails with a connection error. The hardened client implements:
- Initial startup grace: 6.0 seconds.
- Extended retry loop: 80 attempts at 1.0s interval (80s total connection budget).
- Heartbeat logging: Progress output emitted every 10 attempts to keep the supervisor informed.

