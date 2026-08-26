# Pipeline Audit & Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Full 5-phase audit → test harness → targeted hardening of the Al-Daheeh production pipeline, preserving all architectural invariants.

**Architecture:** Sequential phase-gated subagent dispatch. Each phase produces a forensic report in `.docs\` before handoff; new tests extend the existing green `tests\` baseline (170 unit / 17 integration); production changes are behavior-preserving and gated by the full suite.

**Tech Stack:** Python 3.10+, pytest, ruff/black/mypy/bandit, Playwright CDP, FFmpeg QSV/NVENC, Windows named pipes.

**User decisions locked:** tests extend existing `tests\` tree (not literal `.tests\`); subagent routing uses available specialist agents (directive's named free models unavailable here — substitution documented per report); Phase 5 scope = targeted hardening (defects + cc≥50 hotspots), NOT mass rewrite; one git commit per completed phase.

## Global Constraints

- Zero paid cloud SDKs — all AI via Playwright CDP on `127.0.0.1:{CDP_PORT}` only
- No destructive overwrite of any `*checkpoint*.json` / `pipeline.json`; backward-compatible schema migration only
- Integer frame math `N = round(duration × FPS)`; CFR only; zero-drift timeline
- All `subprocess` calls: strict list args + `shell=False`
- Filter graphs >1KB written to disk, loaded via `-filter_complex_script`
- Audacity IPC: `SelectAll:` before DSP; double-backslash escaped paths; wipe SessionData/AutoSave pre-pipe-open
- UTF-8 stream safety: `sys.stdout.reconfigure(encoding='utf-8')` everywhere
- Tests invoked as `python -m pytest ...` from repo root
- Never blind-kill chrome.exe — PID-targeted only via port lookup

---

### Task 1 — Phase 1: Ingestion Map (PARSE→NORMALIZE→MAP)

**Files:**
- Create: `.docs\PHASE_1_INGESTION_REPORT.md`
- Create (draft): `.docs\TRACE_AND_DATAFLOW_MAP.md`

- [x] Dispatch `explore` subagent (very thorough): module inventory, normalized config-key table (env var ↔ consumer ↔ default), checkpoint schema fields (7 state files), dataflow contract chain `youtube_urls.txt → run_agency state machine → phase scripts → pipeline_manifest gates → final MP4/thumbnail`, CDP/pipe touchpoints
- [x] Author both reports from findings
- [x] Commit `docs(phase1): ingestion map + dataflow trace`

### Task 2 — Phase 2: Static Verification (SCAN→LINT→VALIDATE→VERIFY)

**Files:**
- Create: `.docs\PHASE_2_STATIC_VERIFICATION_REPORT.md`

- [ ] Baseline runs: `python -m pytest tests/unit -v` (expect 170 passed); `ruff check .`; `black --check --line-length 100 .`; `mypy .`; `bandit -r . -x venv,youtube_runs,.git`
- [ ] Grep hunts → defect matrix rows: `shell=True`; subprocess without `timeout=`; bare `except`; unclosed handles; forbidden SDK imports (expect 0 hits); `localhost` CDP stragglers (known: run_agency.py:57, generate_voice.py:1015, script_image_generator.py:667, automate_all.py:250+463); `time.sleep` polling in Gemini waits
- [ ] VALIDATE: daheeh_config.json keys vs consumers (refine_script.py, validator.py); ratio sum == 1.0
- [ ] Commit `docs(phase2): static verification matrix`

### Task 3 — Phase 3: Test Harness (TRACE→ANALYZE→AUDIT)

**Executor:** Test Automation Engineer subagent → test-guard review
**Files (Create):**
- `tests\unit\test_timeline_sync.py` — prepare_synchronized_timeline (compile_video.py:669), integer frame bounds, zero drift
- `tests\unit\test_tashkeel_lexicon.py` — single-pass regex vocalization vs daheeh_config.json lexicon
- `tests\unit\test_checkpoint_resilience.py` — corrupt/truncated/partial JSON recovery; CheckpointManager signature validation
- `tests\unit\test_loudnorm_parser.py` — _extract_loudnorm_measured (compile_video.py:884)
- `tests\mocks\mock_cdp_session.py` — Playwright context mock, streaming responses, stability polling handshake
- `tests\mocks\mock_named_pipe.py` — ToSrvPipe/FromSrvPipe read-until-empty-line semantics

- [ ] TDD cycle per file: write → run fail/pass → suite green alongside existing 170
- [ ] Report `.docs\PHASE_3_TESTING_AND_AUDIT_REPORT.md`
- [ ] Commit `test(phase3): six mandated suites + mocks`

### Task 4 — Phase 4: Diagnostics & Review (DEBUG→REVIEW)

**Executor:** gem-debugger (root-cause each ERR-NN row) → gem-critic (peer-review fix designs)

**Files:**
- Create: `.docs\PHASE_4_DIAGNOSTICS_AND_REVIEW_REPORT.md`

- [ ] Root-cause table: trigger → failure path → minimal fix design (no code yet)
- [ ] REVIEW gate: fix designs free of logical fallacies/data holes; rejected alternatives logged
- [ ] Commit `docs(phase4): diagnostics + reviewed fix designs`

### Task 5 — Phase 5: Hardening (REFACTOR→OPTIMIZE→HARDEN)

**Executor:** gem-implementer subagents (parallel per-file) → clean-code-guard check
**Hotspot targets (behavior-preserving, public APIs frozen):**
- compile_video.py run_chunked_compile (:1417, cc=58), assemble_final_video (:1241, cc=55), load_ai_camera_decisions (:458, cc=54), render_chunk (:988, cc=52)
- run_agency.py main (:111, cc=53)

- [ ] HARDEN: apply all Phase-4 approved fix designs (localhost→127.0.0.1, timeout bounds, shell lockdown, stability-poll gaps); atomic-replace pattern preserved (utils.py:282)
- [ ] OPTIMIZE: only zero-behavior-diff wins
- [ ] Final gate: `python -m pytest tests/ -v` all green; ruff/black/mypy clean
- [ ] Finalize `.docs\TRACE_AND_DATAFLOW_MAP.md` + `.docs\PHASE_5_HARDENING_AND_FINAL_REPORT.md`
- [ ] Commit `refactor(phase5): targeted hardening`

## Interfaces Between Phases

- P1→P2: normalized key/config table + dataflow edges
- P2→P3: defect matrix IDs (`ERR-NN`) drive regression-test targets
- P3→P4: failing/flaky results = confirmed runtime defects
- P4→P5: approved fix designs only — nothing un-reviewed gets implemented

## Risks

- Integration suite shells real ffmpeg lavfi — skips gracefully, non-blocker
- Hotspot refactors risk checkpoint schema drift — mitigated by checkpoint resilience tests landing in Phase 3 BEFORE CheckpointManager is touched
- Windows file locks on temp_clips during tests — tmp_path fixtures only
