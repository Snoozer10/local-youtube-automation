# Secret Scanning Gate Implementation Report
**Task S04 (Issue #103): Add Proportionate Secret-Scanning Gate Covering Service Tokens and Documentation**
**Campaign Context**: Issue #78 (Architecture Renewal Campaign)
**Inventory Reference**: `tasks/REMAINING_WORK.md:59` (S04, P1 · Confirmed)
**Task Branch**: `sec/s04-secret-scanning-103`
**Base Commit**: `7a67cf67ffd5940b1217b0da52f64e10c13dbdb2` (origin/master)
**Date**: 2026-11-11

---

## 1. Executive Summary

This report documents the design, implementation, and audit repairs of **Task S04 (Issue #103)** under the **Architecture Renewal Campaign (Issue #78)**. Task S04 introduces an offline, dependency-free, high-fidelity repository secret scanner (`tools/check_secrets.py`) with reviewed exclusions (`tools/secrets_allowlist.json`), integrating directly into continuous integration (`.github/workflows/ci.yml`) and pre-commit hooks (`.pre-commit-config.yaml`).

### Core Delivered Items:
1. **Zero-Dependency Proportionate Secret Scanner (`tools/check_secrets.py`)**:
   - Implemented using Python standard library only (`argparse`, `dataclasses`, `json`, `pathlib`, `re`, `subprocess`, `sys`).
   - Scans both codebase files and documentation (e.g. Markdown `.md`, plaintext `.txt`, YAML, JSON) for high-fidelity secret signatures: Telegram Bot Tokens, AWS access keys, AWS secret access keys, GitHub tokens, Slack tokens, private key headers, and generic high-entropy API key assignments.
   - Emits only safe location and rule name in terminal diagnostics (`path:line: [rule_name] potential secret token detected`) with sanitized path tokens to guarantee failure logs never leak secret values or credential fragments.
2. **Reviewed Exclusions Mechanism (`tools/secrets_allowlist.json`)**:
   - Matches exclusions against individual matched secret values and token strings using strict whole-match semantics, preventing placeholders like `[redacted]` or substring prefixes like `your-api-key` from suppressing adjacent or longer credentials.
   - Supports path-specific allowlists targeting individual files without leaking patterns to the broader codebase.
   - Supports inline pragma annotations with rule-scoping (`# pragma: allowlist secret: <rule>`, `# noqa: secret-check(<rule>)`, and HTML comments `<!-- pragma: allowlist secret: <rule> -->` for Markdown documentation), strictly isolated to unquoted comments and 1-to-1 match proximity.
   - Supports excluded directory paths (`.git`, `.runtime`, `.venv`, etc.) and non-text binary extensions (`.png`, `.jpg`, `.wav`, `.mp3`, etc.).
3. **CI and Pre-Commit Quality Gate Integration**:
   - Added `Quality gate (secret scanning)` step in `.github/workflows/ci.yml`.
   - Added `check-secrets` hook in `.pre-commit-config.yaml` to prevent committing secrets locally.
4. **Dedicated Test Suite (`tests/unit/test_check_secrets.py`)**:
   - 42 unit tests validating clean baseline repository passing, synthetic secret rejection in code and documentation, targeted path exclusions, inline/HTML comment pragmas, binary/path exclusions, safe diagnostics, and regression test cases for all Codex audit items.
5. **Contract Documentation (`tools/AGENTS.md`)**:
   - Documented tool purpose, ownership, inertness invariants, and integration points, preserving base mixed line endings outside the new section.

---

## 2. Technical Architecture & Codex Audit Repairs

### 2.1 Codex Audit Repairs (Key Improvements)

#### Phase 1 Repairs:
1. **Arabic & Non-ASCII Git Path Preservation**:
   - Enumeration uses `git -C <root> ls-files -t -z` and decodes raw bytes with `errors="surrogateescape"`.
   - Bypasses git's default octal-quoting on non-ASCII filenames, ensuring files with Arabic names (e.g. `ملف_بيانات_سري.py`) are resolved and scanned verbatim.
   - Respects sparse checkout tags (`S`/`s`), skipping untracked sparse entries not present on disk.
2. **Individual Match Allowlists & Rule-Scoped Pragmas**:
   - Allowlists match against `matched_value` and `matched_str` instead of raw lines, ensuring a placeholder like `[redacted]` on a line cannot suppress an adjacent credential.
   - Inline pragmas support rule-scoping: `# pragma: allowlist secret: <rule>`, `# noqa: secret-check(<rule>)`, and `<!-- pragma: allowlist secret: <rule> -->`. Pragmas scoped to a different rule do not suppress unmatched detections.
3. **Bounded Inputs & ScanError**:
   - Git enumeration failure raises `ScanError` and exits with code 2, eliminating any fallback to filesystem walking that could scan untracked files like `.env`.
   - Out-of-repo paths, non-existent target paths, and missing tracked files on disk raise `ScanError` (exit code 2) rather than reporting clean.
4. **UTF-16 Support, Unquoted Assignments & Quoted JSON Keys**:
   - `_decode_content` handles UTF-16 with BOM (LE/BE) and UTF-16 LE/BE without BOM (null-byte cadence check) while cleanly distinguishing text from binary files.
   - Regex patterns support unquoted `API_TOKEN=value` assignments and quoted JSON keys (`"aws_secret_access_key": "..."`, `"api_key": "..."`).
5. **Safe Diagnostic Format**:
   - `format_diagnostic()` emits strictly `f"{path}:{line}: [{rule_name}] potential secret token detected"`, never printing credential fragments.

#### Phase 2 Follow-up Repairs (Codex Review on 1c4b9de):
6. **Path Containment Validation on Both Scan Modes**:
   - Both the default Git scan (`git ls-files -t -z`) and explicit file scans validate path containment using `_validate_input_path` before reading any input.
   - Paths following Windows junctions or symlinks pointing outside the repository root fail containment check (`target.relative_to(root_resolved)`) and raise `ScanError` (exit code 2).
   - `scan_file` also validates containment before reading.
7. **Failed File Reads Treated as ScanError**:
   - In-scope files that fail `read_bytes()` due to `PermissionError` or `OSError` raise `ScanError(f"Failed to read file: {path} ({err})")` rather than silently returning empty findings.
   - `main()` catches `ScanError` and returns exit code 2.
8. **Scoped Exclusions, Whole-Match Allowlists & Quoted Marker Isolation**:
   - Quoted pragma text (bare or rule-scoped `# pragma: allowlist secret` or `<!-- pragma: allowlist secret -->` inside quotes or backticks) is recognized as string literals, not comments, and will not suppress credentials.
   - Whole-match allowlist evaluation (`re.fullmatch`) replaces substring searches, preventing longer credentials like `your-api-key-live-secret-12345` from passing allowlist checks.
   - Pragma association operates 1-to-1 based on proximity to matches, ensuring an exemption for one match cannot hide another credential on the same line.
9. **Diagnostic Path Sanitization**:
   - Implemented `sanitize_path()` to replace secret tokens in file paths with `[REDACTED]` using boundary-safe regex patterns across finding diagnostics and stderr error messages (`ScanError`).

#### Phase 3 Follow-up Repairs (Codex Review on PR #114):
10. **Pre-Commit `--` Flag Delimiter**:
    - Added `--` delimiter before forwarded filenames in `.pre-commit-config.yaml` (`entry: python tools/check_secrets.py --`).
    - Ensures filenames starting with hyphens (e.g. `--root=docs`) are forwarded and treated strictly as positional file paths by `argparse`, preventing flag injection attacks against the scanner CLI.
11. **Multiline Literal State Tracking**:
    - `_find_unquoted_pragmas` tracks multiline triple quotes (`"""`, `'''`) and multiline HTML comments (`<!--`) across lines.
    - When inside multiline literal state, lines cannot emit unquoted pragmas. This prevents pragma comments embedded inside Python triple-quoted docstrings or multiline strings from suppressing secret findings.
    - Single-line quotes (`'`, `"`) remain scoped strictly to single lines, preventing apostrophes in Markdown or documentation from spilling across lines.

### 2.2 Detection Signatures
The scanner applies focused regular expressions targeting confirmed high-fidelity credential formats:
- **Telegram Bot Token**: `(?:(?<=\b)|(?<=bot))[0-9]{8,10}:[a-zA-Z0-9_-]{34,36}\b` (supporting both standalone assignments and `/bot<token>/` API endpoint URLs).
- **AWS Access Key ID**: `\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b`.
- **AWS Secret Access Key**: `(?i)['\"]?\b(?:aws_secret_access_key|aws_secret_key)\b['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9/+=]{40})['\"]?`.
- **GitHub Token**: `\b(?:ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82}|gho_[a-zA-Z0-9]{36}|ghu_[a-zA-Z0-9]{36}|ghs_[a-zA-Z0-9]{36}|ghr_[a-zA-Z0-9]{36})\b`.
- **Private Key Block**: `-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----`.
- **Slack Token**: `\bxox[baprs]-[0-9a-zA-Z]{10,48}\b`.
- **Generic High-Entropy API Key**: `(?i)['\"]?\b(?:api_key|api_token|secret_key|auth_token|client_secret|bearer_token)\b['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{24,})['\"]?`.

---

## 3. Synthetic Verification & Positive Test Case Evidence

The scanner was verified against synthetic test values to guarantee true positives in both code and documentation:

1. **Synthetic Secret Detection in Source Code**:
   - Python module (`sample.py`): Synthetic Telegram token `9876543210:AAFl...stuv` detected on line 1, formatted safely.
   - Environment file (`config.env`): Synthetic AWS access key `AKIA1234567890ABCDEF` <!-- pragma: allowlist secret --> detected and formatted safely.
   - Credentials file (`aws_creds.py`): Synthetic 40-character secret key detected.
   - Authentication config (`auth.json`): Synthetic GitHub PAT `ghp_...` detected.
   - Private key fixture (`id_rsa`): RSA private key header block detected.
   - Slack integration (`slack.py`): Synthetic `xoxb-...` token detected.
   - Service definition (`service.py`): Generic high-entropy secret assignment detected.

2. **Synthetic Secret Detection in Documentation**:
   - Setup guide (`guide.md`): Synthetic Telegram bot token embedded within a documentation `curl` example URL caught at line 4.
   - Deployment guide (`deploy.md`): Synthetic `AWS_ACCESS_KEY_ID` in documentation export block caught at line 4.

3. **Codex Regression Test Cases (42 Tests Total)**:
   - `test_detects_secrets_in_arabic_and_non_ascii_git_paths`: Verified Arabic file `ملف_بيانات_سري.py` tracked in git is detected.
   - `test_line_level_placeholder_does_not_suppress_adjacent_secret`: Verified `[redacted]` on a line does not suppress adjacent token.
   - `test_placeholder_as_secret_value_is_allowed`: Verified placeholder used as secret value passes.
   - `test_rule_scoped_pragma_exemption`: Verified rule-scoped pragma exemptions match intended rule.
   - `test_unmatched_rule_scoped_pragma_does_not_exempt`: Verified pragma for different rule does not exempt unmatched secret.
   - `test_git_enumeration_failure_raises_scan_error_and_does_not_scan_untracked`: Verified `ScanError` is raised on Git failure and untracked `.env` is bypassed.
   - `test_target_path_outside_repository_raises_scan_error`: Verified out-of-repo path raises `ScanError`.
   - `test_nonexistent_target_path_raises_scan_error`: Verified missing path raises `ScanError`.
   - `test_missing_tracked_input_raises_scan_error`: Verified missing tracked file on disk raises `ScanError`.
   - `test_cli_exit_code_2_on_scan_error`: Verified CLI returns code 2 on `ScanError`.
   - `test_detects_secrets_in_utf16_text`: Verified detection in UTF-16 with BOM and UTF-16 LE without BOM.
   - `test_detects_unquoted_api_token_assignment`: Verified unquoted `API_TOKEN=value` detection.
   - `test_detects_quoted_json_credential_keys`: Verified quoted JSON keys detection.
   - `test_diagnostic_format_emits_no_secret_fragments`: Verified diagnostic format contains no credential fragments.
   - `test_git_scan_rejects_tracked_path_through_junction_outside_repo`: Verified default Git scan rejects tracked path through Windows junction outside repo with `ScanError`.
   - `test_failed_file_read_raises_scan_error_and_cli_exits_2`: Verified file read failure raises `ScanError` and produces exit code 2.
   - `test_quoted_bare_and_rule_scoped_pragma_does_not_suppress_credential`: Verified bare/scoped pragmas inside quotes or backticks do not suppress credentials.
   - `test_whole_match_allowlist_catches_longer_token_containing_placeholder`: Verified whole-match allowlist catches longer token containing `your-api-key`.
   - `test_exemption_for_one_match_does_not_hide_another_credential`: Verified allowlist or pragma exemption for one match cannot hide another credential on the line.
   - `test_sanitize_path_helper`: Verified `sanitize_path` helper redacts tokens in paths with `[REDACTED]`.
   - `test_finding_diagnostic_sanitizes_token_in_filename`: Verified finding diagnostic replaces token in filename with `[REDACTED]`.
   - `test_error_diagnostic_sanitizes_token_in_path`: Verified error diagnostics on stderr replace tokens in paths with `[REDACTED]`.
   - `test_pragma_inside_multiline_triple_quoted_string_does_not_suppress_finding`: Verified that `# pragma: allowlist secret` inside multiline docstrings (`"""` and `'''`) does not suppress secret findings.
   - `test_forwarded_flags_after_double_dash_scanned_as_files`: Verified that `--` forces flag-like arguments (`--root=docs`) to be scanned strictly as positional files, rejecting dirty secrets and passing clean files.

4. **Pre-Commit Hook Verification with Staged Synthetic Data**:
   - Staged synthetic secret `aws_secret_key = "1234567890abcdef1234567890abcdef12345678"` in `temp_staged_secret.py`: <!-- pragma: allowlist secret -->
     - Executed `pre-commit run check-secrets --files temp_staged_secret.py`:
     - Result: `Failed (exit code 1)`
     - Diagnostic: `temp_staged_secret.py:1: [aws_secret_key] potential secret token detected` (zero credential fragments leaked).
   - Staged synthetic secret in `--root=docs` containing synthetic Telegram token:
     - Executed `pre-commit run check-secrets --files --root=docs`:
     - Result: `Failed (exit code 1)`
     - Diagnostic: `--root=docs:1: [telegram_bot_token] potential secret token detected`
   - Staged clean file `--root=docs` containing `valid = 123`:
     - Executed `pre-commit run check-secrets --files --root=docs`:
     - Result: `Passed (exit code 0)`
   - Cleaned up staged synthetic files and confirmed pre-commit passes cleanly on clean repository files.

---

## 4. Byte & Format Integrity Invariants

1. **Line-Ending Invariants**:
   - `tools/AGENTS.md` preserves the base file's exact mixed line endings (29 CRLF, 5 LF on `origin/master`) outside the inserted section, with 0 extraneous byte or line-ending modifications.
   - All other touched files (`.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `tools/check_secrets.py`, `tools/secrets_allowlist.json`, `tests/unit/test_check_secrets.py`, `tasks/secret-scanning-gate-report.md`) maintain pure LF (`\n`, 0 `\r`) line endings.
   - Verified via `git diff --check master` with 0 warnings.
2. **Tracked File Hashes (SHA-256)**:
   - `.github/workflows/ci.yml`: `24f42253eb9f469cff79f8f61ac4ca0e72c8c4d5be603713d3b6af9fb8f7c95b`
   - `.pre-commit-config.yaml`: `8f65ce9a2a69273a9d37ca7d6d099db22ea28da38127a5826e1961fd6d04d0e6`
   - `tools/AGENTS.md`: `0a352e55fb4ee5069f0e9a71e3220dc31f29d193f665fb7e13e83e18d2909cb0`
   - `tools/check_secrets.py`: `4280d55697f7ae6b530e4138613546ebd1d50e34f7281cf247bd99ca03097abe`
   - `tools/secrets_allowlist.json`: `f5dc613055a21f538b08d85943c41030f58ee210ea2beae6b701c625f342c52f`
   - `tests/unit/test_check_secrets.py`: `f865d268c65ae1097077a3e152acca763302e213829b32e738f10ab7badda424`
   - `tasks/secret-scanning-gate-report.md`: `[tracked at commit]`

---

## 5. Verification Receipts

| Check | Command | Observed Result | Exit Code |
|---|---|---|---|
| **Git Diff Hygiene** | `git diff --check master` | 0 warnings, clean line endings | 0 |
| **Secret Scanning Gate** | `python tools/check_secrets.py` | 0 secrets detected across tracked files | 0 |
| **Dedicated Unit Suite** | `pytest tests/unit/test_check_secrets.py` | 42 passed in 9.62s | 0 |
| **Workspace Linting** | `ruff check .` | All checks passed with 0 errors | 0 |
| **Workspace Formatting** | `ruff format --check tools/check_secrets.py tests/unit/test_check_secrets.py` | All checks passed with 0 errors | 0 |
| **Strict Type Checking** | `mypy --strict --explicit-package-bases tools/check_secrets.py tests/unit/test_check_secrets.py` | Success: no issues found in 2 source files | 0 |
| **README & Public Docs** | `python tools/check_readme.py` | 7 documents checked and passed | 0 |
| **Pre-Commit Gate Test** | `pre-commit run check-secrets --files temp_staged_secret.py` | Rejection observed (exit code 1) | 1 (Expected) |
| **Pre-Commit Flag Delimiter Test** | `pre-commit run check-secrets --files --root=docs` | Rejection on dirty (exit code 1); clean passed (exit code 0) | 1 / 0 |

---

## 6. Scope & Limitations

- **Git History Scanning (S03)**: Marked complete under campaign #78 (credential revoked, replacement alert validated, owner declined history rewrite). This task (S04) provides the preventative pre-commit and CI gates covering current working tree and declared/tracked repository files.
- **Offline Bound**: All operations run completely offline with no network or third-party service calls.
