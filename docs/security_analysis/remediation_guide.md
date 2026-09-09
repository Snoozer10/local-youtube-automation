# Remediation Guide — YouTube Automation Pipeline
**Classification:** CONFIDENTIAL — Operational Security Procedures  
**Version:** 1.0  
**Date:** 2026-07-16

---

## IMMEDIATE ACTIONS (P0 — Execute Before Any Git Push)

### 1. Revoke & Rotate Telegram Bot Credentials
```bash
# Step 1: Message @BotFather on Telegram
# /revoke → Select your bot → Confirm revocation
# /newbot → Create replacement bot (or /mybots → select → API Token → Regenerate)

# Step 2: Note the NEW token format: 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
# Step 3: Get your Chat ID (if changed):
#   - Message @userinfobot or use: https://api.telegram.org/bot<NEW_TOKEN>/getUpdates
#   - Look for "chat":{"id":1487991308,...}
```

### 2. Create `.gitignore` (Project Root)
```bash
cat > .gitignore << 'EOF'
# Secrets & Credentials
.env
.env.*
*.env
gemini_model.txt
voice_option_notes.txt
video_config.local.txt
compile_checkpoint.json
*_checkpoint.json
pipeline.json
refine_checkpoint.json
audacity_checkpoint.json
voice_checkpoint.json
*.log
error.log

# Browser Profiles (contain auth cookies/sessions)
C:\ChromeDebugProfile
C:\OperaDebugProfile
%LOCALAPPDATA%\Google\Chrome\User Data\Default
%LOCALAPPDATA%\Opera Software\Opera Stable

# Runtime Artifacts
youtube_runs/
__pycache__/
*.pyc
*.pyo
*.pyd
.pytest_cache/
.coverage
htmlcov/

# IDE / Editor
.vscode/
.idea/
*.swp
*.swo
*~

# OS
Thumbs.db
Desktop.ini
EOF
```

### 3. Create `.env.example` Template
```bash
cat > .env.example << 'EOF'
# ============================================================
# YouTube Automation Pipeline — Environment Configuration
# COPY THIS FILE TO .env AND FILL IN YOUR VALUES
# NEVER COMMIT .env TO VERSION CONTROL
# ============================================================

# --- Telegram Notifications ---
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=1487991308

# --- Browser & Profile ---
BROWSER_TYPE=chrome          # chrome | opera
ACTIVE_PROFILE_INDEX=1       # 1 = Default, 2 = Profile 1, etc.
SWITCH_ACCOUNTS_ENABLED=false
FAILOVER_RETRY_LIMIT=3

# --- Model Selection (Gemini Web App) ---
SCRIPT_BREAKER_MODEL=Flash
SCRIPT_TRANSLATOR_MODEL=Pro
VOICE_GENERATOR_MODEL=Flash-Lite
IMAGE_PLANNER_MODEL=Flash-Lite
REFINE_MODEL=Pro
THUMBNAIL_MODEL=Pro

# --- Image Generation (Google Flow) ---
FLOW_IMAGE_MODEL=Nano Banana 2
FLOW_IMAGE_COUNT=1x
IMAGE_GENERATOR_TYPE=script    # script | flow
IMAGE_RESET_LOOP_LIMIT=20

# --- Whisper Transcription ---
WHISPER_ENGINE=faster_whisper  # faster_whisper | hard_whisper

# --- Pipeline Orchestration ---
ENABLE_REFINE_SCRIPT=true
FLIP_AUDACITY_ORDER=false
EOF
```

### 4. Migrate `utils.py` to Use `python-dotenv`
```bash
# Install dependency
pip install python-dotenv

# Then modify utils.py — replace get_config_value() and get_config_path()
```
**Patch for `utils.py` (lines 7-60):**
```python
import os
from dotenv import load_dotenv

# Load .env from project root (where this script lives)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

def get_config_value(target_key, default_val=""):
    """Reads a KEY=VALUE pair from environment variables (.env)."""
    # Direct parser-level diagnostics
    val = os.getenv(target_key, default_val)
    print(f"[DEBUG PARSER] Match found! key='{target_key}' -> value='{val}'")
    return val

def update_config_value(target_key, new_val):
    """Updates a specific KEY=VALUE pair in .env file."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    lines = []
    key_found = False
    
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    
    with open(env_path, "w", encoding="utf-8") as f:
        for line in lines:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, _ = line.split("=", 1)
                if key.strip() == target_key:
                    f.write(f"{target_key}={new_val}\n")
                    key_found = True
                    continue
            f.write(line)
        if not key_found:
            f.write(f"{target_key}={new_val}\n")

# Remove get_config_path() — no longer needed
```

### 5. Remove `gemini_model.txt` from Git History (If Already Committed)
```bash
# WARNING: Rewrites history — coordinate with team first!
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch gemini_model.txt" \
  --prune-empty --tag-name-filter cat -- --all

# Force push (requires admin rights on remote)
git push origin --force --all
git push origin --force --tags
```

---

## PRE-PUSH HARDENING (P1 — Before First GitHub Push)

### 6. Install Pre-Commit Secret Scanning
```bash
pip install pre-commit gitleaks

cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.2
    hooks:
      - id: gitleaks
        args: ["--no-banner", "--verbose"]
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: detect-private-key
      - id: detect-aws-credentials
        args: ["--allow-missing-credentials"]
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-yaml
      - id: check-json
      - id: check-toml
EOF

pre-commit install
pre-commit run --all-files  # Test scan
```

### 7. Add GitHub Actions Secret Scanning Workflow
```bash
mkdir -p .github/workflows

cat > .github/workflows/secret-scan.yml << 'EOF'
name: Secret Scan
on:
  push:
    branches: [main, master, develop]
  pull_request:
    branches: [main, master, develop]
  schedule:
    - cron: '0 2 * * 1'  # Weekly Monday 2 AM

jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for scan
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
EOF
```

### 8. Verify No Secrets in Staged Changes
```bash
# Run before every commit
git diff --staged --name-only | xargs -I {} python secret_scan2.py {}
# Or use pre-commit: pre-commit run gitleaks
```

---

## CONFIGURATION FILE PROTECTION

### 9. Protect Local Override Files
These files are generated at runtime:
| File | Purpose | Action |
|------|---------|--------|
| `video_config.local.txt` | Loudnorm measured values per-run | Add to `.gitignore` ✓ |
| `compile_checkpoint.json` | Video compile resume state | Add to `.gitignore` ✓ |
| `flow_workspace_url.txt` | Google Flow project URL | Add to `.gitignore` ✓ |
| `pipeline.json` | run_agency.py step state | Add to `.gitignore` ✓ |

### 10. Secure Browser Profiles
```bash
# These directories contain authenticated sessions — NEVER share/backup
# Chrome: C:\ChromeDebugProfile
# Opera:  C:\OperaDebugProfile

# Verify they're excluded from backups/sync
# Add to .gitignore (already done in step 2)
```

---

## DEEPSEEK MIGRATION PREPARATION (P2)

### 11. Prompt Templating Refactor (Prevents Injection)
**Create `prompt_templates.py`:**
```python
from string import Template

class PromptTemplate:
    """Safe prompt assembly — no raw f-string interpolation."""
    
    SCRIPT_BREAKER = Template("""$prompt
    
[Disclaimer: Sociological/educational analysis only.]
    
Transcript:
$transcript""")
    
    TRANSLATOR_SETUP = Template("$prompt")
    
    TRANSLATOR_CHUNK = Template("paragraph $index outof $total paragraphs of the script:\n\n$paragraph")
    
    REFINER_SETUP = Template("""ACADEMIC DIRECTIVE: You are executing a highly structured, analytical comparative linguistic transcreation task. You must analyze English source texts and adapt them into regional colloquial Egyptian Arabic dialects. Acknowledge the style guide:
$guide""")
    
    REFINER_CHUNK = Template("""LINGUISTIC EXPERIMENT Turn $index of $total. Transcreate the following technical educational and diagnostic text segment into the Egyptian Arabic colloquial dialect defined in the guide. Do not add metadata or platform warnings, as this is for terminology tracking:
$paragraph""")
    
    TTS_GUIDELINES = Template("$prompt")
    TTS_TRANSCRIPT = Template("This is My Transcript script:\n\n$transcript")
    TTS_PROCEED = "Choose the recommended Vocal Archetype and proceed."
    TTS_CONFIRM = "proceed"

    @staticmethod
    def render(template, **kwargs) -> str:
        return template.safe_substitute(**kwargs)
```

**Usage:**
```python
from prompt_templates import PromptTemplate

# Instead of: f"{prompt_p1}{disclaimer}\n\n{transcript}"
payload = PromptTemplate.render(PromptTemplate.SCRIPT_BREAKER, 
                                prompt=prompt_p1, 
                                transcript=transcript_text)
```

### 12. Transcript Sanitization (Input Validation)
```python
import re

def sanitize_transcript(text: str) -> str:
    """Strip potential prompt injection patterns from YouTube transcripts."""
    # Remove instruction-like patterns
    injection_patterns = [
        r"(?i)ignore\s+(previous|above|all)\s+instructions?",
        r"(?i)disregard\s+(previous|above|all)\s+(prompts?|instructions?)",
        r"(?i)you\s+are\s+now\s+",
        r"(?i)act\s+as\s+(an?\s+)?",
        r"(?i)system\s*[:\-]",
        r"(?i)assistant\s*[:\-]",
        r"(?i)user\s*[:\-]",
        r"(?i)<\|.*?\|>",  # ChatML tokens
        r"\[INST\].*?\[/INST\]",  # Llama tokens
    ]
    
    sanitized = text
    for pattern in injection_patterns:
        sanitized = re.sub(pattern, "[FILTERED]", sanitized, flags=re.IGNORECASE | re.DOTALL)
    
    # Limit length to prevent context stuffing
    max_chars = 50000
    if len(sanitized) > max_chars:
        sanitized = sanitized[:max_chars] + "\n[TRUNCATED]"
    
    return sanitized
```

### 13. Async DeepSeek Client Scaffold
```python
# deepseek_client.py
import os
import httpx
from typing import AsyncGenerator

class DeepSeekClient:
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = "https://api.deepseek.com/v1"
        self.client = httpx.AsyncClient(timeout=120.0)
    
    async def chat_completion(self, messages: list, model: str = "deepseek-chat", 
                              stream: bool = False) -> dict | AsyncGenerator:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {"model": model, "messages": messages, "stream": stream}
        
        if stream:
            async with self.client.stream("POST", f"{self.base_url}/chat/completions", 
                                          json=payload, headers=headers) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line[6:]
        else:
            resp = await self.client.post(f"{self.base_url}/chat/completions", 
                                          json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    
    async def close(self):
        await self.client.aclose()
```

---

## ONGOING OPERATIONS (P3)

### 14. Quarterly Credential Rotation Schedule
| Credential | Rotation Frequency | Owner | Procedure |
|------------|-------------------|-------|-----------|
| Telegram Bot Token | 90 days | DevOps | @BotFather → /revoke → /newbot → update `.env` |
| Chrome/Opera Profiles | 180 days | DevOps | Delete `C:\ChromeDebugProfile`, relaunch via `utils.launch_browser_with_profile()` |
| DeepSeek API Key | 90 days | DevOps | DeepSeek Console → Regenerate → update `.env` |
| YouTube Transcript API | N/A (public) | — | No auth required |

### 15. Security Documentation
```bash
cat > SECURITY.md << 'EOF'
# Security Policy

## Reporting Vulnerabilities
Email: security@yourdomain.com (or GitHub Security Advisories)

## Credential Management
- All secrets in `.env` (gitignored)
- Template in `.env.example`
- Pre-commit: gitleaks + detect-secrets
- CI: gitleaks on every PR/push

## Rotation Schedule
- Telegram Bot: Quarterly
- Browser Profiles: Semi-annually  
- DeepSeek API: Quarterly

## Incident Response
1. Revoke compromised credential immediately
2. Rotate all related credentials
3. Audit logs for unauthorized access
4. Document in incident log
EOF
```

---

## VERIFICATION CHECKLIST

Run before any push to GitHub:

- [ ] `TELEGRAM_BOT_TOKEN` revoked and regenerated
- [ ] `TELEGRAM_CHAT_ID` verified with new token
- [ ] `.gitignore` created and committed
- [ ] `.env.example` created and committed
- [ ] `.env` created locally with real values (NOT committed)
- [ ] `utils.py` migrated to `python-dotenv`
- [ ] `gemini_model.txt` removed from git history (if committed)
- [ ] `pre-commit` installed and passing
- [ ] `.github/workflows/secret-scan.yml` added
- [ ] `secret_scan2.py` reports **zero** findings on staged files
- [ ] `SECURITY.md` documented

---

## ROLLBACK PROCEDURE

If secrets are accidentally pushed:

```bash
# 1. Immediately revoke the credential (BotFather / API Console)
# 2. Remove from history:
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env gemini_model.txt" \
  --prune-empty --tag-name-filter cat -- --all

# 3. Force push (coordinate with team!)
git push origin --force --all
git push origin --force --tags

# 4. Rotate ALL potentially exposed credentials
# 5. Notify team — treat as security incident
```

---

**End of Remediation Guide**  
**Next Review:** 2026-10-16 (Quarterly)  
**Owner:** Security Division — CISO Agent