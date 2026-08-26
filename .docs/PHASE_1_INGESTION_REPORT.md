# 🔬 RESEARCH & AUDIT REPORT: Phase 1 — Data Inflow & Ingestion (PARSE → NORMALIZE → MAP)

**Active Subagent**: Subagent Alpha | **Deployed Model**: `Nemotron 3.5 Lightinging Free` (unavailable in environment — **substituted**: opencode `explore` specialist agent, very-thorough mode, per user-approved routing decision)
**Timestamp**: 2026-08-26 02:09:01 UTC
**Target Modules Inspected/Modified**: all 21 repo-root `.py` modules, `tools\` (2), `tests\` (14), `.tests\` dot-tree (9 suites + 2 mocks + conftest — *discovered this phase, invisible to `pytest.ini`*), `.env.example`, `video_config.txt`, `transcribe_config.txt`, `daheeh_config.json`, `pytest.ini`, `pyproject.toml`, `requirements.txt`, `voice_option_notes.txt`
**Phase Status**: COMPLETED & VERIFIED ✅ (read-only phase; no production code touched)

---

## 1. 🎯 Executive Execution Ledger (What Was Done)

- **PARSE**: Ingested every Python module (21 root scripts, 2 tools, full test trees) with symbol-level extraction: public functions/classes + line numbers + import graph. Parsed all four config surfaces (`.env.example`, `video_config.txt`, `transcribe_config.txt`, `daheeh_config.json`) plus tooling configs (`pytest.ini`, `pyproject.toml`, `requirements.txt`).
- **NORMALIZE**: Built a unified env-var ↔ code-reader ↔ default-value matrix (§2 of trace map). Discovered the whitelist-parser pattern shared by both txt config parsers (`compile_video.py:127`, `faster_whisper_transcribe_audio.py:63`) — keys absent from the in-code `DEFAULTS` dict are **silently dropped**, which is the root cause of an entire class of "documented but inert" settings.
- **MAP**: Constructed the end-to-end dataflow contract chain (`youtube_urls.txt` → 10-phase supervisor state machine → final MP4/thumbnail), the checkpoint/state schema registry (12 state files), and the IPC/browser touchpoint inventory. Full artifacts live in companion doc `.docs\TRACE_AND_DATAFLOW_MAP.md`.

## 2. 🔍 Deep Discoveries & Architectural Findings (What Was Uncovered)

1. **Two parallel test trees exist.** A hidden dot-dir `.tests\` (9 unit suites, own `conftest.py`, mocks incl. `audacity_stub.py` + `fake_gemini.py`, `__pycache__` proves it has been executed under pytest 9.1.1 / CPython 3.11) is **invisible** to `pytest.ini` (`testpaths = tests`). CI green baseline ("170 unit passed") counts only the visible tree. Mandated Phase-3 targets partially overlap it (`test_tashkeel_lexicon.py`, `test_checkpoint_idempotency.py`, audacity IPC mock).
2. **Config shadowing chain (precedence surprise):** `voice_option_notes.txt` overrides `.env` TTS values (`generate_voice.read_voice_options:79-108`) and pins the Whisper model size for both ASR engines via `read_whisper_preset_fallback`. Current file forces `Temperature: 0.8` over env `1.1`.
3. **Silent-drop parser semantics:** `transcribe_config.txt` documents a 2.2/3.5/4.8 s pacing metronome (`IMAGE_MIN/TARGET/MAX`) and `IMAGE_PAUSE_SPLIT_SEC=0.40` — **none are read**. Actual cadence = punctuation-forced splitting + `SILENCE_SPLIT_GAP_SEC=0.45` (code default, not present in txt). The documented pipeline behavior in AGENTS.md does not match executable reality.
4. **BGM branch unreachable:** `video_config.txt` carries `ENABLE_BGM/BGM_FILE/BGM_DEFAULT_VOLUME`, but they are not in `load_video_config.DEFAULTS` → dropped → `assemble_final_video:1294-1304` reads only hardcoded defaults. Sidechain-duck BGM feature is dead from file config.
5. **CDP_PORT is a lie at 10 sites:** hardcoded `9222` connect URLs in `automate_all` (:250,:463), `generate_voice` (:1044,:1050), `generate_thumbnail` (:467,:474), `flow_image_generator` (:2568,:2572), `script_image_generator` (:667,:674); plus `localhost` (IPv6-resolve risk the project's own docs warn about) at 4 sites.
6. **Checkpoint atomicity split:** newer stores are tmp+fsync+`os.replace` atomic (`run_agency`, `refine_script`, `generate_voice`, `automate_audacity`, `pipeline_manifest`, `utils.set_runtime_state`); two legacy writers use plain `open(...,"w")` — translate `checkpoint.json` (`automate_all.py:863-881`) and `planning_checkpoint.json` (`script_image_generator.py:614-623`). Crash-window corruption risk concentrated exactly there.
7. **Crash-window recovery exists in refine:** if deliverable missing but checkpoint complete, artifacts regenerate from checkpoint before deletion (`refine_script.py:866-877`) — good pattern worth replicating.
8. **Helper drift:** ≥4 divergent copies each of `get_latest_run_folder` (9 impls), `find_input_box`, `find_send_button`, `is_gemini_generating`, `wait_for_gemini_response`, `select_gemini_model`; `RESPONSE_SELECTOR` differs per module (`gemini_utils:22` vs `generate_voice:24` vs bare `"model-response"` elsewhere).
9. **Mojibake remnants:** `generate_voice.extract_total_blocks_count` matches CP1256-double-encoded Arabic literals (`"ط§ظ„ط¬ط²ط،"`, `"ظ…ظ†"`) at :165, comments :186-189 — works today only because Gemini's output happens to mojibake identically.
10. **`requirements.txt` markdown-fence defect is LIVE:** file begins with ``` fence — `pip install -r requirements.txt` fails as shipped (matches AGENTS.md warning; verified by direct read).
11. **Duplicate pytest config:** `pytest.ini` ≡ `[tool.pytest.ini_options]` byte-equivalent — drift hazard.
12. **Frame math verified sound (pre-audit):** integer budget `int(round(audio_duration*fps))` :725, clip-0 anchor :735, clamp guaranteeing ≥1 frame + no overflow :745, CFR args :211-219, zoompan exact trim :385-386.

## 3. 🚨 Comprehensive Defect & Vulnerability Matrix (Issues Found)

| Defect ID | Severity | File & Line | Description & Root Cause | Trigger Condition |
| :--- | :--- | :--- | :--- | :--- |
| `CFG-01` | High | `faster_whisper_transcribe_audio.py:63` + `transcribe_config.txt:20-31` | 9 documented directives silently ignored (SUB_*, IMAGE_* pacing, EXPORT_TIMELINE_TXT) — whitelist parser drops unknown keys without warning | Any operator edit to those keys expecting behavior change |
| `CFG-02` | Medium | `compile_video.py:28-109` vs `video_config.txt:113-115` | BGM trio dropped by DEFAULTS whitelist → sidechain-duck branch :1294-1304 unreachable from file | Enabling BGM in txt |
| `ENV-01` | Medium | 10 sites (see §2.5) | Hardcoded `9222` bypasses `CDP_PORT`; 4 sites additionally use `localhost` (IPv6 risk) | Non-default `CDP_PORT`; IPv6-resolving hosts |
| `ENV-02` | Low | `.env.example` | 5 dead vars (`ENABLE_ACADEMIC_SAFETY_FALLBACK`, `REFINE_MAX_SLANG_PER_SENTENCE`, `TTS_DOWNLOAD_TIMEOUT`, `FLOW_RENDER_TIMEOUT`, `FLOW_STALL_TIMEOUT`) mislead operators | Reading docs/config |
| `ENV-03` | Low | `.env.example` | 11 code-read vars missing from example (e.g. `FLOW_CUMULATIVE_CHAINING_ENABLED`, `RUNNING_GAG_MOTIF`, `SCRIPT_IMAGE_*` family) | Fresh setup |
| `DEP-01` | Critical (setup-blocking) | `requirements.txt:1` | Markdown ``` fence makes pip fail | `pip install -r requirements.txt` |
| `CHK-01` | High | `automate_all.py:863-881`, `script_image_generator.py:614-623` | Non-atomic checkpoint writes (plain `open("w")`) vs atomic pattern everywhere else | Crash/power-loss mid-write |
| `TST-01` | High | `pytest.ini:1` vs `.tests\` | Parallel hidden test tree uncounted by CI; mandated coverage partially duplicated there | Running pytest / CI |
| `DOC-01` | Medium | `AGENTS.md`/`CLAUDE.md` pacing claims vs `SILENCE_SPLIT_GAP_SEC=0.45` reality | Documented cadence ≠ implemented cadence | Trusting docs |
| `MOJI-01` | Medium | `generate_voice.py:165,186-189` | Mojibake-matched Arabic literals — fragile to any upstream encoding change | Gemini output encoding shift |

Full inventory tables (module registry, normalized config matrix, state-schema registry, dataflow contracts, subprocess inventory) → `.docs\TRACE_AND_DATAFLOW_MAP.md`.

## 4. 🛠️ Resolution Strategy & Applied Fixes (How It Was Solved)

Phase 1 is ingestion-only — **no fixes applied by design** (directive: upstream verification before modification). Findings above seed the Phase 2 defect matrix (`ERR-NN` IDs assigned there). Architectural rationale: mapping before measuring prevents the audit itself from invalidating its own baseline (green 170-test run must precede any change).

## 5. 🚫 Discarded Approaches & Failed Alternatives

- **Attempted: brace-glob `{.tests,.docs}/**/*` discovery.**
  - *Why it failed*: glob engine skipped dot-directories → false negative ".tests does not exist". Caught because explore agent independently reported the opposite; resolved via `Get-ChildItem -Force`.
  - *Lesson*: hidden-dir enumeration on this repo requires `-Force` / explicit dot-path globs.
- **Considered: treating `.tests\` as canonical merge target for Phase 3.**
  - *Why rejected*: user decision locked tests into visible `tests\` tree (CI scope, pytest.ini already wired); dot-tree stays as historical reference, relevant coverage gets ported forward.

## 6. 🛡️ Invariants & Safety Compliance Audit

- [x] **Zero Paid Cloud SDK Rule**: import scan found zero `google-generativeai`/`openai`/`anthropic` imports in active tree (only legacy `tools/transcribe_audio.py` uses openai-whisper *package*, not OpenAI API — allowed)
- [x] **Checkpoint Idempotency**: all 12 state files mapped; no writes performed; resume semantics documented per-file
- [x] **Subprocess Safety**: complete call-site inventory compiled (17 prod sites) — zero `shell=True` found anywhere
- [x] **Zero-Drift Sync Math**: verified present (`prepare_synchronized_timeline:725-747`); unchanged
- [x] **UTF-8 Console Integrity**: reconfigure calls confirmed across entrypoints; untouched

## 7. 📈 Telemetry, Test Execution & Downstream Hand-off

- No tests executed (read-only phase); existing green baseline assumed: 170 unit / 17 integration (2026-08-26 AGENTS.md record).
- `.tests\` hidden tree discovered but NOT yet counted/run — flagged for Phase 2 SCAN.
- **Handoff to Beta**: defect seeds `CFG-01…MOJI-01`; normalized config matrix; subprocess site list for VERIFY step; requirement to reconcile both test trees.
