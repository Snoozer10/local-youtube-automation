<!--
SYNC IMPACT REPORT
=================
Template version: constitution-template.md (untracked) -> ratified as 1.0.0
Date: 2026-07-11

ADDED (this document):
  - 9 Core Principles (I–IX), each written with MUST/SHOULD language and
    concrete, verifiable mandates.
  - Section: Development Workflow
  - Section: Security & Compliance
  - Section: Governance (supersedes other practices; amendment + Sync Impact
    Report + template-update requirements)
  - Adjusted Principle I (resilient-locator mandate) and Principle II
    (checkpoint isolation + resume + no-duplicate-work) per review mandate.

REMOVED:
  - None. No principles, sections, or requirements were removed from the
    template structure.

TEMPLATES UPDATED:
  - plan-template.md    ✅  Constitution Check placeholder replaced with 9 concrete, checkable gate bullets (one per Principle I–IX).
  - spec-template.md    ⚠  No mandatory change. Verified aligned: its Security/Edge-Cases sections are compatible with Principle VII; no edit made.
  - tasks-template.md    ⚠  No change. Verified it already covers testing/observability (contract/integration/unit test tasks, logging tasks).

CONSTITUTION MOVE:
  - .specify relocated from spec-kit/.specify -> image_generation/.specify (project root).
  - spec-kit/.github and spec-kit/.vscode left intact as the clean toolkit copy.
-->

# YouTube Video Automation Pipeline Constitution

## Core Principles

### I. Browser-Automation-Only AI (Resilient Locators)

All artificial-intelligence work in this pipeline (Gemini Web UI translation/planning, AI Studio Speech Playground TTS, Google Flow image generation) MUST be performed exclusively through Playwright CDP browser automation against a manually-signed-in, persistent browser profile. No script MAY import an AI vendor API SDK (e.g. `openai`, `google.generativeai`, `genai`, `anthropic`) or read any AI API key. The only permitted outbound credential is the Telegram bot token in `gemini_model.txt`, used solely via `utils.send_telegram_notification()`.

**Resilient-locator mandate (NON-NEGOTIABLE):**

- No script MAY rely on a single hard-coded DOM path to locate a Gemini/Google UI element.
- Every UI target MUST be expressed as a prioritized list of fallback selectors (e.g. role/label, stable attributes, then the known fragile path `"model-response div.markdown"` as a last resort — not the only entry).
- Every interaction MUST be preceded by an explicit `wait_for_*` condition (`wait_for_selector`, `wait_for_response`, `wait_for_function`) tied to application state — never a wall-clock sleep as a substitute for readiness.
- If a selector breaks after a Google UI update, that is a **constitution violation**, not a routine bug. The fix MUST harden the locator strategy (add/reprioritize fallbacks, add explicit waits). It is forbidden to silently re-patch a single path or mask the break with `wait_for_timeout`/`sleep`.

### II. Checkpoint & Resume Safety

- Every script MUST persist JSON progress files ONLY under `youtube_runs/<Title>/` (e.g. `checkpoint.json`, `voice_checkpoint.json`, `planning_checkpoint.json`, `flow_workspace_url.txt`, `pipeline.json`). Progress files MUST NOT be written to the project root or any other location.
- A rerun after failure MUST resume from the last saved state and MUST NOT duplicate work already completed (no re-translation, no re-generation, no re-stitch of finished units).
- Checkpoint files MUST be deleted on successful completion of the stage they guard; checkpoint presence signals "resume", absence signals "start fresh".
- Every script SHOULD expose a single-step safe rerun: invoking it again on a partially-completed run continues, never restarts.

### III. Orchestrator Discipline

`run_agency.py` is the source of truth for the full pipeline. The legacy `run.bat` (steps 1–5 only: no audacity polish, stitch, spellcheck, fixtimes, or Flow image generation) MUST NOT be used for production runs. `IMAGE_GENERATOR_TYPE` (value exactly `flow` or `script`, no extra whitespace) selects the image-generation path; its value MUST be honored by the orchestrator and MUST NOT be overridden by a hard-coded branch.

### IV. Account Rotation & Profile Mapping

`ACTIVE_PROFILE_INDEX` MUST cycle through 1→3 mapping to Chrome profiles `Default`, `Profile 1`, `Profile 2`. Before any script spawns a new CDP browser it MUST call `kill_cdp_chrome(port=9222)` to terminate the previous instance. The profile index → Chrome profile-name mapping MUST stay correct; a mismatch that points two workers at the same signed-in profile is a constitution violation.

### V. Windows-Only Hardcoded Constraints

The pipeline is Windows-only and non-portable by design. Hardcoded paths (`C:\Program Files\Google\Chrome\Application\chrome.exe`, Opera under `%LOCALAPPDATA%\Programs\Opera\...`, `C:\Program Files\Audacity\Audacity.exe`), debug profiles (`C:\ChromeDebugProfile`, `C:\OperaDebugProfile`), native clipboard access via `ctypes.windll.user32`/`kernel32`, and `CREATE_NEW_CONSOLE | DETACHED_PROCESS` launch flags MUST be centralized in `utils.py` and documented as Windows-only. Cross-platform portability is out of scope and MUST NOT be silently assumed.

### VI. UTF-8 / Arabic Correctness

Every script that handles Arabic text MUST call `sys.stdout.reconfigure(encoding='utf-8')` and MUST write JSON with `ensure_ascii=False`. Arabic content MUST round-trip without mojibake through `final_output.txt`, `flow_prompts.json`, and any `.docx`/`.srt` artifacts.

### VII. Secrets & Security (NON-NEGOTIABLE)

`gemini_model.txt` contains the Telegram bot token and MUST remain listed in `.gitignore`. Secrets MUST NOT be committed, logged to stdout/stderr, or inlined in source. Any commit that adds `gemini_model.txt` to version control is a hard violation. Telegram credentials are the only secrets in scope; no AI API keys exist because Principle I forbids them.

### VIII. Idempotent Rerun / Stateless Skip

Scripts MUST be safe to re-run. The image generators MUST honor the stateless skip rule: if `generated_images/<timestamp>.png` exists and is larger than 100 bytes, generation for that timestamp MUST be skipped. Temporary artifacts (e.g. `generated_images_duplicates/`, `temp_clips/`) MUST NOT cause a rerun to regenerate or duplicate completed outputs.

### IX. Simplicity / Preferred Paths

`flow` image generation is the preferred path over `script` (more reliable, resumable workspace URL) and SHOULD be the default unless overridden by `IMAGE_GENERATOR_TYPE=script`. YAGNI is enforced: no unrequested features, config fields, or scripts MAY be added. Dead config (e.g. the unused `Whisper Model` field in `voice_option_notes.txt`) MUST NOT be promoted into active code paths.

## Development Workflow

- The full pipeline is invoked via `python run_agency.py`; single-step reruns use `python <script>.py` and rely on Principle II checkpoints to resume.
- A "clean room" reset is achieved by deleting `youtube_runs/<Title>/` and rerunning — NO script MAY require manual state surgery outside that directory.
- New features and specs MUST pass the plan-template "Constitution Check" gate (Principle I–IX) before implementation begins.
- `AGENTS.md` is the runtime guidance companion to this constitution: it documents the exact mechanics (launcher functions, selectors, debug profiles). Where `AGENTS.md` and this constitution conflict, this constitution wins.

## Security & Compliance

- Principle VII is the binding security control. `.gitignore` MUST contain `gemini_model.txt`; CI/pre-commit SHOULD fail if it is staged.
- No outbound network call from a script MAY carry an AI API key (per Principle I).
- Browser automation operates on a manually-signed-in profile; credentials live in the browser profile, never in repo files.
- Telegram notifications are the only external integration and MUST use the token exclusively from `gemini_model.txt` via `utils`.

## Governance

- This constitution supersedes all other development practices, conventions, and ad-hoc habits for the YouTube Video Automation Pipeline.
- Amendments MUST: (a) bump the version using semver (MAJOR for principle removals/redefinitions, MINOR for additions, PATCH for wording/clarification); (b) include a Sync Impact Report (added/removed/changed, templates touched); (c) update the affected templates (`plan-template.md` at minimum) so the Constitution Check gate stays in sync.
- Every new feature/spec/PR MUST pass the plan-template "Constitution Check" gate; violations MUST be justified in the plan's Complexity Tracking table or rejected.
- `AGENTS.md` is the runtime companion; changes there SHOULD be cross-checked against this constitution but do not themselves amend it.
- The ratified version line below is the single source of truth for currency.

**Version**: 1.0.0 | **Ratified**: 2026-07-11 | **Last Amended**: 2026-07-11
