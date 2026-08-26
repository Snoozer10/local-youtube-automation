# 🔬 RESEARCH & AUDIT REPORT: Phase 2 — Static Verification & Guardrails (SCAN → LINT → VALIDATE → VERIFY)

**Active Subagent**: Subagent Beta | **Deployed Model**: `MiMo V2.5 Free` (unavailable — **substituted**: inline tooling execution + targeted static hunts, per user-approved routing decision)
**Timestamp**: 2026-08-26 (UTC) · **Follows**: `.docs\PHASE_1_INGESTION_REPORT.md`
**Target Modules Inspected**: all active-tree `.py` (21 root + tools + tests + hidden `.tests\`), configs; **Modified**: none (verification-only phase)
**Phase Status**: COMPLETED & VERIFIED ✅

---

## 1. 🎯 Executive Execution Ledger

| Gate | Command | Result |
|---|---|---|
| Baseline unit | `python -m pytest tests/unit -q` | **170 passed** in 11.72 s ✅ |
| Hidden tree | `python -m pytest .tests/unit -q` | **115 passed, 1 FAILED, 1 skipped** in 48.64 s ❌ |
| Ruff | `ruff check .` | **266 errors** (202 auto-fixable) |
| Black | `black --check --line-length 100 .` | **28 files would reformat** |
| mypy strict | `mypy .` | **688 errors in 16 files** |
| Bandit | `python -m bandit …` | **tool absent** from env → substituted with targeted security greps |

Hunt sweeps executed: `shell=True`, forbidden SDK imports, bare `except:`, `eval/exec/pickle.load/yaml.load/os.system/__import__`, subprocess-without-timeout census, `time.sleep` polling census (~200 sites catalogued), daheeh_config consumer validation.

## 2. 🔍 Deep Discoveries & Architectural Findings

1. **The repo fails its own declared quality gates.** AGENTS.md mandates ruff/black/mypy as standard; current state: 266+28-file+688-error debt. The "green baseline" phrase covers pytest only. Debt concentration: W293 whitespace 150, E701 multi-statement 24, F841 unused-var 13, E722 bare-except 3.
2. **Hidden `.tests\` tree contains a live product-bug detector that CI never sees** — and it is currently RED: `test_gap_in_sequence_reported_not_silent`.
3. **Root cause of the red test (ERR-03):** `scan_sequential_chapters` (`stitch_chapters.py:52-64`) loops `range(start_index, max_idx+1)` and appends **post-gap orphans into `found`** (Chapters 1,2,4 ⇒ found=[1,2,**4**]). Its docstring promises gap identification; its caller `main()` aborts on non-empty `missing`, masking the contract breach today. Any future caller trusting `found` alone would silently stitch a truncated episode skipping real chapter content — precisely what the test docstring documents as a past incident ("Chapter_3 missing silently dropped chapter 4 content").
4. **Subprocess timeout census (prod sites lacking bounds):**
   - `compile_video.py:391` — `ffprobe check_output` on arbitrary WAV input, **no timeout** → hang risk on corrupt/truncated WAV (High).
   - `run_agency.py:119`, `run_agency.py:310` — supervisor child launches with **no timeout** (translate/refine legitimately long-running, but zero ceiling means a wedged CDP session stalls the whole batch forever; only video step has 3600 s cap :304).
   - `utils.py:134/147/155` netstat/taskkill/fuser, `automate_audacity.py:224/317/425` taskkill — fast tools, Low severity, still unbounded.
5. **Bare `except:` ×3** at `automate_audacity.py:129,158,226` — swallow KeyboardInterrupt/SystemExit during checkpoint load/preset ops.
6. **Security sweep clean:** zero `shell=True` (only a docstring mention utils.py:128), zero forbidden SDK imports, zero eval/exec/os.system/pickle/yaml.load. Subprocess inventory (Phase 1 §5) re-verified: all list-args.
7. **time.sleep topology:** modern planning layer (`gemini_controller`) polls inside bounded loops with configurable intervals — compliant pattern. Legacy clones (`flow_image_generator` ~140 sleeps, `generate_voice` ~60, `gemini_utils`, `script_image_generator`) mix bounded waits with fixed blind sleeps (e.g. flow:2137 "Give Gemini time…", script_image_generator:958 `sleep(10)`); selector-drift documented Phase 1 compounds this.
8. **VALIDATE mechanical checks:** `daheeh_config.json` ratios sum to exactly 1.0 (0.30+0.70); all 11 tashkeel lexicon entries non-empty strings; single reader path confirmed (refine engine + automate_all baseline applier). Unused sections carry no executable weight — doc-drift only.
9. **Duplicate pytest config** (`pytest.ini` ≡ `pyproject [tool.pytest.ini_options]`) confirmed byte-equivalent — silent divergence hazard when one side is edited.

## 3. 🚨 Comprehensive Defect & Vulnerability Matrix

| Defect ID | Severity | File & Line | Description & Root Cause | Trigger Condition |
| :--- | :--- | :--- | :--- | :--- |
| `ERR-01` | Critical | `requirements.txt:1` | Markdown ``` fence breaks `pip install -r` (carried from Phase 1 CFG-seed) | Fresh environment setup |
| `ERR-02` | High | `pytest.ini:2` vs `.tests\` | Parallel hidden test tree invisible to CI; carries unique coverage (audacity IPC, gemini stability, checkpoint idempotency) + the red test | Any CI run / local `pytest` |
| `ERR-03` | High | `stitch_chapters.py:52-64` | `scan_sequential_chapters` includes post-gap chapters in `found`, breaching stitchable-prefix contract; proven red by hidden test | Caller consumes `found` without checking `missing` |
| `ERR-04` | High | `compile_video.py:391` | ffprobe duration probe has no timeout → indefinite hang on malformed WAV | Corrupt audio file mid-pipeline |
| `ERR-05` | High | `automate_all.py:863-881`, `script_image_generator.py:614-623` | Non-atomic plain-write checkpoints (vs atomic pattern elsewhere) | Crash/power-loss mid-write |
| `ERR-06` | Medium | 10 connect sites (map §4) | Hardcoded `9222`; 4 use `localhost` (IPv6 resolve risk) | Non-default CDP_PORT; IPv6 hosts |
| `ERR-07` | Medium | `faster_whisper_transcribe_audio.py:63` + txt | 9 documented directives silently dropped by whitelist parser | Operator edits pacing keys |
| `ERR-08` | Medium | `run_agency.py:119,:310` | Supervisor children have no timeout ceiling | Wedged browser session |
| `ERR-09` | Medium | `compile_video.py:28-109` vs `video_config.txt:113-115` | BGM trio parser-dropped → sidechain branch unreachable | Enabling BGM via file |
| `ERR-10` | Medium | repo-wide | Lint/type debt vs own gates: ruff 266 / black 28 files / mypy 688 (top: generate_voice 133, compile_video 88, flow 80) | Any quality-gate run |
| `ERR-11` | Medium | `generate_voice.py:165,186-189` | Mojibake-matched Arabic literals | Upstream encoding change |
| `ERR-12` | Medium | `flow_image_generator.py` (~140), `generate_voice.py` (~60), legacy pollers | Blind fixed-sleep polling clones diverge from bounded modern handshake | Slow DOM/Gemini turns |
| `ERR-13` | Low | `automate_audacity.py:129,158,226` | Bare `except:` swallows BaseException | Ctrl-C during load/save |
| `ERR-14` | Low | `.env.example` | 5 dead vars + 11 undocumented live vars | Reading example config |
| `ERR-15` | Low | `video_config.txt` dead keys; `daheeh_config.json` unused sections | Config/doc surface lies about behavior | Trusting docs |
| `ERR-16` | Low | `pytest.ini` vs `pyproject.toml:117` | Duplicate pytest config, byte-equal today | Future partial edit |

## 4. 🛠️ Resolution Strategy & Applied Fixes

No production fixes applied (phase gate: fixes land in Phase 5 after Phase 4 review). Scheduled dispositions:
- ERR-01: strip fences → plain pinned reqs (Phase 5, trivial).
- ERR-02: port mandated suites + mocks into visible `tests\` (Phase 3 scope per user lock); dot-tree remains reference.
- ERR-03: align `scan_sequential_chapters` to contract — truncate `found` at first gap (exact semantics the red test asserts). Design reviewed Phase 4.
- ERR-04/08: add timeout bounds consistent with existing patterns (`FFMPEG_CLIP_TIMEOUT`-style constants).
- ERR-05: migrate two writers to the tmp+fsync+replace helper pattern already proven in-repo.
- ERR-06: route every connect through `127.0.0.1:{CDP_PORT}`.
- ERR-10: `ruff check --fix` + `ruff format` auto-tranche in Phase 5 behind green-test gate; hand-fix remainder.
- ERR-13: narrow to `except Exception`.

## 5. 🚫 Discarded Approaches & Failed Alternatives

- **Attempted: `bandit` security scan.**
  - *Why rejected*: binary and module absent from both global python and venv; installing mid-audit would alter the environment under measurement. Substituted equivalent-coverage greps (dangerous-API census clean).
- **Considered: fixing ERR-03 immediately (one-line break).**
  - *Why rejected*: directive ordering forbids pre-Phase-4 mutation; also `found` semantics change deserves REVIEW sign-off since `main()`'s error message enumerates `missing` — truncation alters user-visible output shape.
- **Considered: treating ~200 time.sleep sites uniformly as defects.**
  - *Why rejected*: bounded-interval sleeps inside completion loops are the repo's sanctioned anti-flake mechanism against Gemini DOM jitter (AGENTS.md hard-won facts); blanket removal would regress stability. Only unbounded/blind sleeps queued.

## 6. 🛡️ Invariants & Safety Compliance Audit

- [x] **Zero Paid Cloud SDK Rule** — grep `(import|from) (google.generativeai|openai|anthropic)`: **0 hits** (active tree)
- [x] **Checkpoint Idempotency** — all resume paths intact; ERR-05 flagged, no state files touched
- [x] **Subprocess Safety** — `shell=True`: **0 hits**; full call-site census list-args verified (17 prod sites)
- [x] **Zero-Drift Sync Math** — frame-budget functions untouched; math sites re-cited in trace map §6
- [x] **UTF-8 Console Integrity** — reconfigure guards confirmed present incl. stitch_chapters header block
- [ ] *(new gate proposed)* Quality-tooling gate currently FAILING — tracked as ERR-10 for Phase 5 closure

## 7. 📈 Telemetry, Test Execution & Downstream Hand-off

- Executed: 170 passed (visible) + 116 ran (hidden: 115P/1F/1S). Combined known-good floor: 285 passing.
- **Handoff to Gamma (Phase 3)**: build mandated suites in `tests\unit` + `tests\mocks`; regression-target ERR-03 explicitly; mocks must mirror `mock_cdp_session.py`/`mock_named_pipe.py` names from directive; reuse `tests\conftest.py` fixtures; keep suite runtime <60 s.
- **Handoff to Delta (Phase 4)**: root-cause queue = ERR-03 (primary, has failing repro), ERR-04, ERR-05, ERR-08, ERR-12; design-review gate before any Phase 5 edit.
