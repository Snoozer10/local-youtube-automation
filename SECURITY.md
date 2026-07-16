# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 4.x     | :white_check_mark: |
| < 4.0   | :x:                |

## Reporting a Vulnerability

**Please do not open public GitHub issues for security vulnerabilities.**

Instead, report security issues privately via email to **security@yourdomain.com** (replace with actual contact).

Include the following information:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes or mitigations

## Response Timeline

We are committed to responding to security reports in a timely manner:

- **Acknowledgment:** Within 48 hours of receipt
- **Initial Assessment:** Within 7 days
- **Fix Development:** Within 30 days for critical issues, 90 days for non-critical
- **Coordinated Disclosure:** After fix is deployed

## Security Considerations

This project has several unique security considerations due to its architecture:

### Credential Management

- **Telegram Bot Token** — Stored in `gemini_model.txt` (gitignored). Never commit this file.
- **Browser Profiles** — Contain authentication cookies/sessions for Google accounts. Stored in `C:\ChromeDebugProfile` and `C:\OperaDebugProfile` (gitignored).
- **No API Keys** — All AI interactions use browser automation against manually-signed-in sessions.

### Browser Automation Risks

- Playwright CDP connects to browser on localhost:9222. Ensure this port is not exposed externally.
- Browser profiles persist login state. Treat them as credentials.
- Account rotation (`ACTIVE_PROFILE_INDEX`) cycles through 3 profiles on rate limits/errors.

### External Dependencies

- **FFmpeg** — Invoked via subprocess. Validate input paths to prevent command injection.
- **Audacity** — Named pipes (`\\.\pipe\ToSrvPipe`) and PyAutoGUI require local Audacity instance.
- **Telegram Bot API** — Outbound HTTPS only. Token stored in gitignored config.

### Data Handling

- YouTube transcripts and generated content written to `youtube_runs/<Title>/` (gitignored)
- Arabic text handling uses `sys.stdout.reconfigure(encoding='utf-8')` and `ensure_ascii=False`
- No persistent database or external data storage beyond local filesystem

### Windows-Specific

- Hardcoded paths for Chrome, Opera, Audacity executables
- `ctypes.windll` for native clipboard access (TTS script only)
- `CREATE_NEW_CONSOLE | DETACHED_PROCESS` for browser launch
- Named pipes are Windows-only (`\\.\pipe\...`)

## Best Practices for Contributors

1. **Never commit secrets** — `.gitignore` covers `gemini_model.txt`, `.env`, browser profiles, runtime artifacts
2. **Validate all external inputs** — YouTube URLs, file paths, config values
3. **Use subprocess safely** — `shell=False` (default), pass args as list
4. **Keep dependencies updated** — Run `pip-audit` periodically
5. **Test security fixes** — Verify rate limiting, error handling, credential rotation

## Disclosure Policy

When a security issue is confirmed:

1. We will develop and test a fix
2. We will prepare a release with the fix
3. We will coordinate public disclosure with the reporter
4. We will publish a security advisory on GitHub

We appreciate responsible disclosure and will credit reporters (unless they prefer anonymity).