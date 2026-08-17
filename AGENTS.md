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

1. **State Update & Progress Log**: Refined prompt created and saved to `docs/Prompts/REFINED_RUN_FLOW_IMAGE_GENERATOR_PROMPT.md`.
2. **Next Action Roadmap**: Ready for user to review prompt or invoke OpenCode agent with new prompt.
3. **Session Memory Preservation**: Prompt incorporates strict CDP-only rules, dual-logging contract, deterministic healing tree, JSON recovery, and binary validation.
4. **Discovery Artifacts**: `docs/Prompts/REFINED_RUN_FLOW_IMAGE_GENERATOR_PROMPT.md`.
5. **Pivot & Error Log**: None.
6. **Verification Anchor**: Verified file presence and length on disk via filesystem check.

