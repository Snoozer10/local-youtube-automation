# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]

**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]

**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]

**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]

**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]

**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]

**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]

**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]

**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design. Each bullet is a concrete, review-checkable assertion against the ratified constitution (image_generation/.specify/memory/constitution.md, v1.0.0).*

- [ ] **I. Browser-Automation-Only AI** — Confirm no script imports an AI API SDK (`openai`, `google.generativeai`, `genai`, `anthropic`) or reads an AI API key; all AI goes through Playwright CDP. Confirm every Gemini/Google UI locator is a prioritized fallback list (not a single hard-coded path) and every interaction uses an explicit `wait_for_*` condition — NOT a blind `sleep`/`wait_for_timeout`.
- [ ] **II. Checkpoint & Resume Safety** — Confirm all progress JSON is written ONLY under `youtube_runs/<Title>/`; a rerun resumes from last state without duplicating work; checkpoints are deleted on success.
- [ ] **III. Orchestrator Discipline** — Confirm the plan invokes `run_agency.py` (not legacy `run.bat`); `IMAGE_GENERATOR_TYPE` is honored exactly (`flow`/`script`, no whitespace).
- [ ] **IV. Account Rotation & Profile Mapping** — Confirm profile index cycles 1→3 (Default/Profile 1/Profile 2), `kill_cdp_chrome` is called before spawning, and no two workers share a profile.
- [ ] **V. Windows-Only Hardcoded Constraints** — Confirm hardcoded Chrome/Opera/Audacity paths, debug profiles, `ctypes` clipboard, and `CREATE_NEW_CONSOLE` flags are centralized in `utils.py` and documented as non-portable.
- [ ] **VI. UTF-8 / Arabic Correctness** — Confirm every Arabic-handling script calls `sys.stdout.reconfigure(encoding='utf-8')` and writes JSON with `ensure_ascii=False`.
- [ ] **VII. Secrets & Security (NON-NEGOTIABLE)** — Confirm `gemini_model.txt` is in `.gitignore`, is never committed/logged/inlined, and no secrets leak into source or artifacts.
- [ ] **VIII. Idempotent Rerun / Stateless Skip** — Confirm `generated_images/<ts>.png` >100 bytes is skipped on rerun and scripts are safe to re-run without duplication.
- [ ] **IX. Simplicity / Preferred Paths** — Confirm `flow` is the default image path unless `IMAGE_GENERATOR_TYPE=script`, and no unrequested features/config fields are added (YAGNI).

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
