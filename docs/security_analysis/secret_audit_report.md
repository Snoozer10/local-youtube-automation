# Secret Audit Report

**Project:** YouTube Video Automation Pipeline (Version 4)  
**Audit Date:** 2026-07-16  
**Classification:** CONFIDENTIAL — Internal Security Review  
**Scan Methodology:** Automated entropy scanning (Shannon H ≥ 4.5) + Pattern-based secret detection (gitleaks-style rules) + Manual code review  
**Scope:** Source code directory only (excludes `youtube_runs/`, `.opencode/`, `venv/`, `__pycache__/`, `.git/`)

---

## 1. Executive Summary

| Metric | Count |
|--------|-------|
| **Critical Findings** | 1 |
| **High Findings** | 0 |
| **Medium Findings** | 0 |
| **Low Findings** | 0 |
| **Files Scanned** | 47 Python + 12 Config + 8 Prompt files |
| **Lines Analyzed** | ~18,500 |
| **False Positives (Entropy)** | ~1,600 (package-lock.json hashes, Arabic text, prompt templates) |

**Bottom Line:** **One verified active credential leak** — Telegram Bot Token and Chat ID hardcoded in `gemini_model.txt`. No API keys, AWS credentials, database passwords, or private keys found in source code.

---

## 2. Verified Findings

### FINDING-001: Hardcoded Telegram Bot Credentials in Configuration File
| Attribute | Detail |
|-----------|--------|
| **Severity** | **CRITICAL** |
| **CWE** | CWE-798: Use of Hard-coded Credentials |
| **File** | `gemini_model.txt` |
| **Lines** | 16-17 |
| **Variables** | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| **Entropy H(X)** | Token: 4.72 | Chat ID: 3.17 (low entropy but structural) |
| **Status** | **ACTIVE LEAK** — File tracked by git, committed to repo |

**Evidence:**
```ini
# gemini_model.txt:16-17
TELEGRAM_BOT_TOKEN=8932913661:AAG-HJFJcx_hXAID76B7huEXUHsMrfp57j4
TELEGRAM_CHAT_ID=1487991308
```

**Context:**
- `utils.py:189-196` loads these values via `get_config_value()` and sends notifications via `urllib.request` to `api.telegram.org`
- `utils.py:28-45` auto-creates this file with **empty placeholder values** if missing — but the committed version contains real credentials
- Used by: `run_agency.py`, `refine_script.py`, `generate_voice.py`, `flow_image_generator.py`, `compile_video.py`

**Impact:**
- Anyone with repo access can send messages as the bot to chat ID `1487991308`
- Bot token allows full Telegram Bot API access (send messages, read updates, manage webhooks)
- Chat ID exposes target recipient (potential PII / operational security)

**Remediation:** Immediate revocation via @BotFather → `/revoke` → generate new token → store in `.env` only.

---

## 3. Entropy Scan Results (High-Entropy Strings H ≥ 4.5)

The entropy scan flagged 1,623 high-entropy strings. After triage:

| Category | Count | Status | Examples |
|----------|-------|--------|----------|
| **SHA512 hashes (package-lock.json)** | ~1,400 | FALSE POSITIVE | `sha512-Dew1okvhM/SQcIa2rcgujNndZwU8VnSapDgdxlYoB84ZlpAD43U6KLAFqYo17ykSFGHNPrg0q` |
| **Arabic prompt content** | ~150 | FALSE POSITIVE | Generated image prompts with mixed scripts |
| **Style anchor templates** | ~50 | FALSE POSITIVE | Repeated prompt boilerplate in `pre_planned_prompts.txt` |
| **Actual secrets** | **1** | **VERIFIED** | Telegram bot token in `gemini_model.txt` |

**Entropy Threshold:** H(X) ≥ 4.5 bits/char (standard for 20+ char base64-like secrets)  
**Minimum Length:** 16 characters  
**Note:** Package-lock.json hashes are expected high-entropy artifacts — not secrets.

---

## 4. Pattern-Based Secret Detection Results

| Pattern | Files Matched | Verified Secrets |
|---------|---------------|------------------|
| `telegram[_-]?bot[_-]?token` | 1 (`gemini_model.txt`) | **1** |
| `chat[_-]?id` | 1 (`gemini_model.txt`) | **1** |
| `ghp_[A-Za-z0-9]{36}` | 0 | 0 |
| `sk-[A-Za-z0-9]{48}` | 0 | 0 |
| `AKIA[0-9A-Z]{16}` | 0 | 0 |
| `api[_-]?key\s*[:=]` | 0 | 0 |
| `secret[_-]?key\s*[:=]` | 0 | 0 |
| `password\s*[:=]` | 0 | 0 |

**No** GitHub PATs, OpenAI keys, AWS keys, database URLs, or private keys detected in source code.

---

## 5. Configuration Files Analysis

| File | Purpose | Secrets Present | Risk |
|------|---------|-----------------|------|
| `gemini_model.txt` | Model selection, account switching, Telegram | **YES (2)** | CRITICAL |
| `video_config.txt` | FFmpeg encoding parameters | NO | LOW |
| `voice_option_notes.txt` | TTS voice/model settings | NO | LOW |
| `TTS_PROMPT.txt` | System prompt for voice generation | NO | LOW |
| `prompt.txt` / `prompt_phase3.txt` | Translation/refinement prompts | NO | LOW |
| `refine_prompt.txt` | Script refinement guide | NO | LOW |
| `manual_animations.txt` | Per-clip camera overrides | NO | LOW |

**Key Finding:** `gemini_model.txt` serves dual purpose — configuration **and** credential storage. This violates separation of concerns. The auto-create logic in `utils.py:28-45` writes placeholders but the committed file was manually edited with real values.

---

## 6. Git History Risk (Capability B - Differential Scanning)

```bash
# Run to verify if credentials exist in git history:
git log --all --full-history -- gemini_model.txt
git log -p --all -S 'TELEGRAM_BOT_TOKEN' -- '*.txt'
```

**Recommendation:** If this repo was ever pushed to a remote (GitHub/GitLab), assume the token is compromised and rotate immediately. Use `git filter-branch` or `BFG Repo-Cleaner` to purge from history if needed.

---

## 7. DeepSeek Transition Risk Profile (Capability C)

| Vector | Current State | Migration Risk |
|--------|---------------|----------------|
| System prompt assembly | Raw f-string interpolation | **HIGH** — Injection possible |
| Transcript → LLM payload | Direct concatenation | **HIGH** — Attacker-controlled input |
| Config → LLM context | `get_config_value()` loads into memory | **MEDIUM** — Could leak if referenced |
| Browser automation sync | Blocking Playwright calls | **MEDIUM** — Blocks async SDK |
| Telegram credentials in memory | `bot_token` variable in `send_telegram_notification()` | **LOW** — Not interpolated into prompts |

**No evidence** of active DeepSeek integration yet — this is a forward-looking risk for the planned migration.

---

## 8. Compliance Mapping

| Standard | Requirement | Status |
|----------|-------------|--------|
| **OWASP ASVS 4.0** | V7.1: No hardcoded secrets | ❌ FAIL |
| **OWASP ASVS 4.0** | V7.2: Secrets in config files | ❌ FAIL |
| **NIST 800-53** | IA-5: Authenticator Management | ❌ FAIL |
| **PCI DSS 4.0** | Req 8.2.1: No hardcoded credentials | ❌ FAIL |
| **GDPR** | Art. 32: Security of processing | ⚠️ PARTIAL |

---

## 9. Remediation Verification Steps

After applying fixes from `remediation_guide.md`:

```bash
# 1. Verify no secrets in staged files
python secret_scan2.py

# 2. Verify gitleaks clean
gitleaks detect --source . --no-git --verbose

# 3. Verify .env not tracked
git check-ignore .env && echo "OK: .env ignored"

# 4. Verify gemini_model.txt has placeholders only
grep -E 'TELEGRAM_(BOT_TOKEN|CHAT_ID)=' gemini_model.txt
# Should output:
# TELEGRAM_BOT_TOKEN=
# TELEGRAM_CHAT_ID=

# 5. Verify utils.py uses python-dotenv
grep -c "load_dotenv" utils.py
# Should be ≥ 1
```

---

## 10. Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| **CISO Agent** | Automated Security Division | 2026-07-16 | ✅ |
| **AppSec Engineer** | [Pending Human Review] | — | ⏳ |
| **SecOps Lead** | [Pending Human Review] | — | ⏳ |

---

**Report Classification:** CONFIDENTIAL  
**Distribution:** Security Division, Lead Developer, DevOps  
**Retention:** 3 years per security policy  
**Next Scheduled Audit:** 2026-10-16 (Quarterly)