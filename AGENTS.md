# 🤖 AGENTS.MD — Autonomous Subagent Execution & Safety Directives

This document governs the behavior, constraints, and tool invocation rules for autonomous subagents and LLM coding assistants operating inside the **YouTube Video Automation Pipeline (Al-Daheeh Engine)** repository.

---

## 🎯 Primary Operational Directive

When executing, debugging, or extending any pipeline component:

1. **Never Introduce Cloud API SDKs**: Do not import `google-generativeai`, `openai`, `anthropic`, or paid cloud API client libraries. All AI interactions must flow exclusively through Playwright CDP over port `9222` (`127.0.0.1:9222`).
2. **Preserve Checkpoint Idempotency**: Never write destructive overwrite logic that discards existing `pipeline.json`, `checkpoint.json`, `refine_checkpoint.json`, `voice_generation_manifest.json`, or `compile_checkpoint.json` files without explicit user confirmation.
3. **Respect Al-Daheeh Dialect Rules**: Maintain the 30% Academic Fusha : 70% Cairene Amiya Golden Ratio, 1-3-1 Gary Provost cadence, and phonetic Tashkeel diacritics defined in `daheeh_config.json` and `audit_rubric.md`.
4. **Preserve Windows Subprocess Integrity**: Always use list-based subprocess arguments with `shell=False`. Keep `QSV_LOOKAHEAD=0` on Intel QuickSync encoders to avoid bitstream starvation.

---

## 📋 Subagent Task Execution Matrix

| Agent Task                   | Target Script / Module               | Mandatory Verification Checklist                                                                                                                    |
| :--------------------------- | :----------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Linguistic Transcreation** | `automate_all.py`                    | Verify 30/70 ratio; ensure academic fallback prompt activates on safety block.                                                                      |
| **Script Doctor Polish**     | `refine_script.py`                   | Apply `daheeh_config.json` Tashkeel lexicon; strip XML `<thinking>` and `<slang_ledger>` tags.                                                      |
| **Voice Synthesis**          | `generate_voice.py`                  | Ensure Bezier curve mouse physics active; verify MD5 hash on downloaded WAV to prevent duplicate buffers.                                           |
| **DSP Mastering**            | `automate_audacity.py`               | Ensure Named Pipes connect (`\\.\pipe\ToSrvPipe`); issue `SelectAll:` before applying DSP effects.                                                  |
| **Audio Stitching**          | `stitch_chapters.py`                 | Lossless Wave frame stitching; verify zero frame dropping.                                                                                          |
| **ASR & Cadence Pacing**     | `faster_whisper_transcribe_audio.py` | Enforce 3–6 words per chunk; verify VAD silence splits (`PACING_MIN_GAP_SPLIT=0.45`).                                                               |
| **Lexical Spellcheck**       | `correct_transcript_spelling.py`     | Use `difflib.SequenceMatcher` against `refined_script.txt` without drifting timestamp bounds.                                                       |
| **Visual Generation**        | `flow_image_generator.py`            | Inject "Add to prompt" DOM attachments for multi-frame sets; capture via native Playwright screenshot.                                              |
| **Thumbnail Optimization**   | `generate_thumbnail.py`              | Run self-critique scoring matrix; generate top 2 variants.                                                                                          |
| **Video Compositing**        | `compile_video.py`                   | Enforce zero-drift integer frames; write filter graphs >32 KB to `-filter_complex_script`; test QSV $\rightarrow$ NVENC $\rightarrow$ CPU fallback. |

---

## 🔍 Selector & DOM Safety Rules (Browser CDP)

- **Selector Cascades**: Never rely on a single CSS selector. Always query across cascading fallback tuples.
- **Text Stability Polling**: In `gemini_utils.py`, never replace dynamic polling with static `time.sleep()`. A turn is only complete when text length is non-zero and stable across 4 consecutive sample cycles (~5–6 seconds) while no thinking indicators or stop buttons are present.
- **Socket Cleanup**: If Chrome/Opera hangs on port `9222`, invoke `kill_cdp_chrome(port)` to query `netstat` and terminate only the specific listening PID.

---

## 🧪 Testing Invariants

Before concluding any refactor:

1. Run `python -m pytest tests/ -v` to ensure all unit and integration tests pass.
2. Run `ruff check .` and `black --check --line-length 100 .` to verify formatting standards.
3. Verify that `youtube_runs/` directories remain untracked in Git.

---

## 🚨 Mandatory State Preservation Checkpoint

1. **State Update & Progress Log**: `flow_image_generator.py` Character Creation + Create Body flow FULLY FIXED and validated live. e2e dry-run PASSED (2026-08-20 03:38-03:40) on `test_run_01` (workspace 0cde18ab): both characters created end-to-end (New Character card → Describe-your-character input → editor mount → rename → info → portrait → Create Body triptych 100% rendered → Done), 4 scenes created+renamed, manifest saved. `test_e2e_live` (workspace 694ed946): presets cached, Frame 00_04.png extracted via Network Stream, 1376x768 verified. Real folder `youtube_runs/متلازمة المحتال` RESTORED from temp.
2. **Next Action Roadmap**: Optional: fix `'Add to Prompt' button not found in asset dialog` warning during @asset summoning (chars/scenes still render — non-blocking); reduce resume crash noise on workspace 694ed946 (Application-error reload, cosmetic); commit `flow_image_generator.py` changes (user-initiated only).
3. **Session Memory Preservation**: Character flow selector facts (validated live): submit = Material Symbol `arrow_forward` (ZERO svg buttons on screen; `button:has(svg)` fails — Enter fallback mandatory); `Describe your character` view input = `textarea/input[placeholder*='Describe your character' i]` OR contenteditable whose inner_text contains it; `+ New Character` card only on empty-gallery state, templates screen on non-empty workspace; body popup input = `div[contenteditable='true']` LAST (floating card); workspace bar = `What do you want to create?` (NEVER fill — creates regular image, not character). Editor-mount verified ≤3s via `/character/<id>` URL + Done button. Workspace 694ed946 crashes on load → resume reload recovers. MCP chrome-devtools/playwright connect to SEPARATE browser (not :9222) — CDP probes (`connect_over_cdp`) required for Flow inspection.
4. **Discovery Artifacts**: `docs/Prompts/REFINED_RUN_FLOW_IMAGE_GENERATOR_PROMPT.md` (existing); selector-fact notes in this checkpoint; probe scripts in `C:\Users\Snoozer\AppData\Local\Temp\opencode\probe_*.py`.
5. **Pivot & Error Log**: `div[contenteditable='true']:not([placeholder*=...])` fallback typed into workspace bar → replaced with placeholder/contenteditable-text verification-gated input; `Create my avatar` card = webcam modal (avoid); `wait_for_flow_app_ready` (3s stability window) required after goto/reload (clicks swallowed during hydration); re-click spam breaks 25-130s render-blocked navigation — patient waits only.
6. **Verification Anchor**: Lint = 11 pre-existing errors only; py_compile clean; ruff format clean; image 1376x768 ≥1280x720; telemetry log present; NO new debug_snapshots from 03:3x runs (all 4 pre-existing = 02:42-03:19 pre-fix).

