# 🛡️ Security Policy & Threat Model

The **YouTube Video Automation Pipeline** operates on a local Windows architecture combining browser automation, native Win32 inter-process communication (IPC), hardware-accelerated media subprocesses, and AI model orchestration.

This document outlines our security policies, threat model, vulnerability reporting procedures, and architectural defense-in-depth strategies.

---

## 📋 Supported Versions

We actively maintain and provide security updates for the following versions:

| Version             | Supported | Status      | Security Maintenance                                                    |
| :------------------ | :-------: | :---------- | :---------------------------------------------------------------------- |
| **`4.x` (Current)** |    ✅     | **Active**  | Full patch support for CDP exploits, IPC security, and dependency CVEs. |
| **`3.x`**           |    ❌     | End-of-Life | Unsupported. Please upgrade to the `v4.x` architecture.                 |
| **`< 3.0`**         |    ❌     | Deprecated  | Unsupported legacy release.                                             |

---

## 🚨 Reporting a Vulnerability

**Please do not report security vulnerabilities via public GitHub issues, discussions, or pull requests.**

If you discover a security vulnerability or potential exploit in this repository, please report it through one of the following confidential channels:

1. **GitHub Private Vulnerability Reporting (Preferred)**: Navigate to the **Security** tab of this repository $\rightarrow$ **Advisories** $\rightarrow$ Click **"Report a vulnerability"**.
2. **Confidential Security Email**: Send your disclosure to **`security@yourproject.org`** _(or the maintainer's verified security contact)_.

### What to Include in Your Disclosure

To help us triage and remediate the issue quickly, please provide:

- **Description**: Detailed explanation of the vulnerability, attack vector, and potential impact.
- **Component Affected**: Specific script or module (e.g., `utils.py`, `compile_video.py`, `automate_audacity.py`).
- **Reproduction Steps**: A minimal, reproducible proof-of-concept (PoC).
- **Environment Context**: Windows version, Python version, Chrome/Opera version, and relevant config flags.
- **Mitigation**: Any proposed patches or code remediation (if available).

### Response & Coordinated Disclosure SLA

- **Initial Acknowledgment**: Within **24 to 48 hours**.
- **Triage & Severity Assessment**: Within **7 business days**.
- **Fix & Patch Deployment**: Within **30 calendar days** for high/critical vulnerabilities.
- **Coordinated Public Disclosure**: We follow responsible coordinated disclosure and will credit security researchers in release notes (unless anonymity is requested).

---

## 🧱 Threat Model & Architectural Defenses

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             LOCAL ATTACK SURFACE MATRIX                          │
│                                                                                  │
│   [Browser Layer]  ──► CDP Port 9222 (Loopback Only, Local Auth Profiles)       │
│   [IPC Layer]      ──► Audacity Named Pipes (\\.\pipe\ToSrvPipe)                 │
│   [Memory Layer]   ──► Win32 Clipboard (ctypes GlobalAlloc/GlobalLock)           │
│   [Subprocess]     ──► FFmpeg / FFprobe (List-based args, -filter_complex_script)│
│   [Secrets Layer]  ──► .env / gemini_model.txt (Gitignored Credentials)         │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 1. Chrome DevTools Protocol (CDP) Socket Isolation

- **Threat**: If the Chrome/Opera remote debugging port (`9222` / `9223`) binds to an external network interface (`0.0.0.0`), any remote actor on the local area network (LAN) could connect, execute arbitrary JavaScript, steal session cookies, or compromise host systems.
- **Defense**:
  - The launcher in `utils.py` strictly binds debugging sessions to local loopback interfaces (`localhost` / `127.0.0.1`).
  - Process management uses surgical PID discovery (`netstat -ano | findstr :<port>`) combined with `taskkill /PID` to terminate only verified debugging child processes.
  - Browser debugging profiles (`C:\ChromeDebugProfile`, `C:\OperaDebugProfile`) are stored outside workspace repositories and strictly gitignored.

### 2. Subprocess Execution & Command Injection Prevention

- **Threat**: Maliciously crafted video titles, YouTube transcripts, or filter parameters could attempt shell injection when spawning external binaries (FFmpeg, FFprobe, Audacity).
- **Defense**:
  - **No Unsafe Shells**: All subprocess calls (`subprocess.Popen`, `subprocess.run`) avoid `shell=True` where user/external strings are evaluated. Commands are passed strictly as sanitized argument lists.
  - **File-Based Filter Graphs**: To prevent Windows CLI argument overflow (~32 KB limit) and quote injection attacks, `compile_video.py` compiles complex video filter graphs into temporary `.txt` files and loads them via `-filter_complex_script`.
  - **Path Normalization**: Media paths are passed through `os.path.abspath()` with character escaping applied to colons (`\:`) and single quotes (`'\'\\'\''`) before injection into FFmpeg subtitle filters.

### 3. Win32 Named Pipe IPC Security

- **Threat**: Audacity's `mod-script-pipe` creates two local named pipes (`\\.\pipe\ToSrvPipe` and `\\.\pipe\FromSrvPipe`). Unvalidated data streams or orphaned pipes could cause buffer overflows or deadlock conditions.
- **Defense**:
  - `automate_audacity.py` explicitly clears Audacity's temporary `SessionData` and `AutoSave` crash directories before opening pipe handles.
  - Named pipe interactions enforce non-blocking retry loops, explicit command delimiters (`\n`), and structured response terminators to prevent infinite hangs.

### 4. Native Memory & Clipboard Protection

- **Threat**: Direct Win32 memory allocation via `ctypes` in `generate_voice.py` could cause heap corruption or memory leaks if memory handles are not released properly.
- **Defense**:
  - The native clipboard helper explicitly configures 64-bit argument/return types for `kernel32` and `user32` functions (`GlobalAlloc`, `GlobalLock`, `GlobalUnlock`, `SetClipboardData`).
  - Memory is managed within `try ... finally` blocks to ensure `user32.CloseClipboard()` executes even when exceptions occur.

### 5. Credential & Environment Variable Security

- **Threat**: Accidental disclosure of Telegram bot tokens, chat IDs, or personal browser authentication sessions in source control.
- **Defense**:
  - All credentials are read from `.env` and `gemini_model.txt`. Both filenames are hardcoded in `.gitignore`.
  - The codebase uses local browser session cookies directly from your machine, meaning **zero third-party API keys or cloud service tokens** are ever stored or transmitted over external networks.
  - Telegram alerting in `utils.py` uses direct outbound HTTPS requests with timeout bounds and error suppression to avoid leaking tokens into console logs.

---

## 🛡️ Security Best Practices for Operators & Developers

When deploying or modifying this pipeline, follow these security rules:

```powershell
# 1. Verify your git status never tracks secrets or profile directories
git status --ignored

# 2. Run dependency vulnerability audits regularly
pip-audit

# 3. Restrict file permissions on Chrome debug directories
icacls "C:\ChromeDebugProfile" /inheritance:r /grant:r "%USERNAME%:(OI)(CI)F"
```

1. **Never Commit Secrets**: Ensure `.env`, `gemini_model.txt`, and `youtube_runs/` remain untracked.
2. **Isolate Debugging Profiles**: Do not use your primary personal Chrome profile for automation. Always use dedicated directories (`C:\ChromeDebugProfile`).
3. **Verify Upstream Sources**: When executing batch runs from `youtube_urls.txt`, ensure URLs originate from trusted creators to avoid malicious transcript injection.
4. **Keep Binaries Updated**: Maintain up-to-date versions of FFmpeg, Audacity, and Chromium to protect against upstream media decoder vulnerabilities.

---

## 🔍 Supply Chain & Dependency Auditing

We periodically audit all Python dependencies (`requirements.txt`, `requirements-dev.txt`) for known vulnerabilities using automated tooling:

```bash
# Audit installed packages against PyPI advisory database
pip install pip-audit
pip-audit -r requirements.txt
```

Any dependencies with known Critical or High CVEs are updated or replaced immediately.

---

Thank you for helping maintain the security and integrity of the **YouTube Video Automation Pipeline**! 🔒
