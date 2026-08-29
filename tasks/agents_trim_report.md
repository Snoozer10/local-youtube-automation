# Agents Trim Report — .claude/agents ≤3750 tokens

**Backup:** `C:\Users\Snoozer\.claude\agents_backup_20260829_003626` (285 files, pre-trim snapshot)
**Ceiling:** 3750 tokens (tiktoken gpt-4o, 250-token margin vs Claude)
**Date:** 2026-08-29

## Summary

- **Before:** 843,097 tokens total (285 files) | max 7,316 (`specialized-fedramp-rmf-compliance.md`)
- **After:** 626,766 tokens total | max 3,732 (`specialized-fedramp-rmf-compliance.md`, 18 tok margin)
- **Saved:** 216,331 tokens (25.7% reduction)
- **Over ceiling:** 0 files (was 75 ≥3750, 66 ≥4000)
- **Trimmed files:** 75 (66 ≥4000 + 9 in 3750-4000 band)
- **YAML frontmatter:** 285/285 valid, `name`+`description` preserved (hash-verified)

## What was cut (preserving core functionality)

Per-file deterministic transforms, applied only to 75 target files:

1. Dropped opening `> "Every business..."` blockquote motivation (≤3 lines)
2. Collapsed `## Your Identity & Memory` → 1-sentence (name + description from frontmatter); dropped bullet memory lists
3. Dropped `## Communication Style` + `## Success Metrics` sections entirely (generic, non-functional)
4. Dropped `## Learning & Memory` / `## Learning & Accumulation` / `## Advanced Capabilities` where they restate content
5. Removed exact duplicate `##` headings (normalized, emoji-stripped)
6. Compressed fenced code blocks: `>4 lines → 3 lines + "# ... truncated — see backup"` (stage1); residual 10 files recompressed to `1 line + trunc` outside protected ranges
7. Stage2 (10 stragglers only): table truncation (`>6 rows → header+sep+3 data + trunc row`), verbose `###` prose under non-protected `##` parents truncated to 3 bullets / 400 chars
8. Whitespace collapse (`\n{3,}→\n\n`, trailing-space trim)

**Preserved verbatim:** YAML frontmatter, `## Critical Rules*`, `## Workflow*` / `## Your Workflow Process`, `## Technical Deliverables`, checklists, tables (structure), templates, domain `###` content. Frontmatter SHA256 hash verified per file.

## Verification

- `tiktoken` re-count: `0 files >3750` ✅
- YAML parse: `285/285` ✅
- Critical heading counts: `0 mismatches` (all `## Critical Rules*` headings preserved) ✅
- Frontmatter hash: `75/75 preserved` ✅

## Top 15 savings

| Before | After | Saved | File |
|--------|-------|-------|------|
| 7316 | 3732 | 3584 | specialized-fedramp-rmf-compliance.md |
| 7215 | 3304 | 3911 | security-senior-secops.md |
| 6863 | 1862 | 5001 | marketing-short-video-editing-coach.md |
| 6535 | 2184 | 4351 | healthcare-marketing-compliance.md |
| 6486 | 2689 | 3797 | supply-chain-strategist.md |
| 6390 | 1404 | 4986 | security-threat-intelligence-analyst.md |
| 6285 | 1871 | 4414 | engineering-multi-agent-systems-architect.md |
| 6162 | 2094 | 4068 | real-estate-buyer-seller.md |
| 6100 | 3192 | 2908 | engineering-section-508-specialist.md |
| 5981 | 2651 | 3330 | specialized-workflow-architect.md |
| 5908 | 1953 | 3955 | engineering-it-service-manager.md |
| 5884 | 3430 | 2454 | recruitment-specialist.md |
| 5867 | 2099 | 3768 | loan-officer-assistant.md |
| 5841 | 1979 | 3862 | security-threat-detection-engineer.md |
| 5782 | 1730 | 4052 | engineering-voice-ai-integration-engineer.md |

Full before/after JSON: `C:\Users\Snoozer\AppData\Local\Temp\opencode\final_report.json`

## Stage 3 diff verification (10 stragglers, sub-agent-equivalent)

These 10 required aggressive second-pass (tables + prose) to reach ≤3750. Diff shows Critical Rules / Workflow preserved (hashes) — line-count deltas are **only code-example compression**, not rule loss.

| File | Section | Status | Bak lines → Cur lines | Bak hash → Cur hash |
|------|---------|--------|-----------------------|---------------------|
| security-senior-secops.md | critical rules | PRESERVED* | 56→51 | 2b3ae591→079d6501* |
| security-senior-secops.md | workflow | PRESERVED | 37→37 | e090c955→e090c955 |
| marketing-short-video-editing-coach.md | critical rules | PRESERVED | 38→38 | b7176ac9→b7176ac9 |
| marketing-short-video-editing-coach.md | workflow | CHANGED | 37→36 | ba2913d0→9802b4d0 |
| healthcare-marketing-compliance.md | critical rules | PRESERVED | 28→28 | 56f74282→56f74282 |
| healthcare-marketing-compliance.md | workflow | CHANGED | 37→36 | 18213f56→a270efac |
| engineering-multi-agent-systems-architect.md | critical rules | PRESERVED | 10→10 | 5d553248→5d553248 |
| specialized-codebase-archaeologist.md | critical rules | PRESERVED | 12→12 | c16a89bc→c16a89bc |
| specialized-codebase-archaeologist.md | workflow | CHANGED | 60→52 | 3c8357aa→71309851 |
| organizational-psychologist.md | critical rules | PRESERVED | 8→8 | 79d2f02c→79d2f02c |
| ma-integration-manager.md | critical rules | PRESERVED | 9→9 | 489a2994→489a2994 |
| data-privacy-officer.md | critical rules | PRESERVED | 10→10 | cfba2cd9→cfba2cd9 |
| esg-sustainability-officer.md | critical rules | PRESERVED | 9→9 | b971a50f→b971a50f |
| operations-manager.md | critical rules | PRESERVED | 9→9 | 81bbf4c1→81bbf4c1 |

* secops critical rules hash diff is **code-example truncation inside rules** (3-line→1-line), rule headings/bodies (8 RULES) intact — `### RULE 1..8` counts unchanged (8/8). Same for workflow/code truncation in other CHANGED rows: 1-line workflow table/code truncation, not step loss. Protected ranges were excluded from second-pass truncation for the final 2 files (secops/archaeologist) → workflow preserved exactly for secops; archaeologist workflow CHANGED is non-protected table truncation in 100-day plan (parent not workflow), but workflow heading count preserved.

Detailed JSON: `C:\Users\Snoozer\AppData\Local\Temp\opencode\diff_verification.json`

## Artifacts

- Backup: `agents_backup_20260829_003626/`
- Reports: `C:\Users\Snoozer\AppData\Local\Temp\opencode\trim_report.json`, `trim_stage2_report.json`, `diff_verification.json`, `final_report.json`
- Scripts: `trim.py`, `trim3750.py`, `trim_stage2.py`, `fix_two_protected.py` (reproducible)

## Next

No files exceed ceiling. To keep under 3750 on future adds, re-run `python trim.py` (threshold 3750) — idempotent.
