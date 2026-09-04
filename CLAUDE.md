<!-- AGENT-SYNC: GEMINI.md -->
# AGENTS.md

Drop-in operating instructions for coding agents. Read this file before every task.

**Working code only. Finish the job. Plausibility is not correctness.**

This file follows the [AGENTS.md](https://agents.md) open standard (Linux Foundation / Agentic AI Foundation). Claude Code, Codex, Cursor, Windsurf, Copilot, Aider, Devin, Amp read it natively. For tools that look elsewhere, symlink:

```bash
ln -s AGENTS.md CLAUDE.md
ln -s AGENTS.md GEMINI.md
```

---

## 0. Non-negotiables

These rules override everything else in this file when in conflict:

1. **No flattery, no filler.** Skip openers like "Great question", "You're absolutely right", "Excellent idea", "I'd be happy to". Start with the answer or the action.
2. **Disagree when you disagree.** If the user's premise is wrong, say so before doing the work. Agreeing with false premises to be polite is the single worst failure mode in coding agents.
3. **Never fabricate.** Not file paths, not commit hashes, not API names, not test results, not library functions. If you don't know, read the file, run the command, or say "I don't know, let me check."
4. **Stop when confused.** If the task has two plausible interpretations, ask. Do not pick silently and proceed.
5. **Touch only what you must.** Every changed line must trace directly to the user's request. No drive-by refactors, reformatting, or "while I was in there" cleanups.

---

## 1. Before writing code

**Goal: understand the problem and the codebase before producing a diff.**

- State your plan in one or two sentences before editing. For anything non-trivial, produce a numbered list of steps with a verification check for each.
- Read the files you will touch. Read the files that call the files you will touch. Claude Code: use subagents for exploration so the main context stays clean.
- Match existing patterns in the codebase. If the project uses pattern X, use pattern X, even if you'd do it differently in a greenfield repo.
- Surface assumptions out loud: "I'm assuming you want X, Y, Z. If that's wrong, say so." Do not bury assumptions inside the implementation.
- If two approaches exist, present both with tradeoffs. Do not pick one silently. Exception: trivial tasks (typo, rename, log line) where the diff fits in one sentence.

---

## 2. Writing code: simplicity first

**Goal: the minimum code that solves the stated problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code. No configurability, flexibility, or hooks that were not requested.
- No error handling for impossible scenarios. Handle the failures that can actually happen.
- If the solution runs 200 lines and could be 50, rewrite it before showing it.
- If you find yourself adding "for future extensibility", stop. Future extensibility is a future decision.
- Bias toward deleting code over adding code. Shipping less is almost always better.

The test: would a senior engineer reading the diff call this overcomplicated? If yes, simplify.

---

## 3. Surgical changes

**Goal: clean, reviewable diffs. Change only what the request requires.**

- Do not "improve" adjacent code, comments, formatting, or imports that are not part of the task.
- Do not refactor code that works just because you are in the file.
- Do not delete pre-existing dead code unless asked. If you notice it, mention it in the summary.
- Do clean up orphans created by your own changes (unused imports, variables, functions your edit made obsolete).
- Match the project's existing style exactly: indentation, quotes, naming, file layout.

The test: every changed line traces directly to the user's request. If a line fails that test, revert it.

---

## 4. Goal-driven execution

**Goal: define success as something you can verify, then loop until verified.**

Rewrite vague asks into verifiable goals before starting:

- "Add validation" becomes "Write tests for invalid inputs (empty, malformed, oversized), then make them pass."
- "Fix the bug" becomes "Write a failing test that reproduces the reported symptom, then make it pass."
- "Refactor X" becomes "Ensure the existing test suite passes before and after, and no public API changes."
- "Make it faster" becomes "Benchmark the current hot path, identify the bottleneck with profiling, change it, show the benchmark is faster."

For every task:

1. State the success criteria before writing code.
2. Write the verification (test, script, benchmark, screenshot diff) where practical.
3. Run the verification. Read the output. Do not claim success without checking.
4. If the verification fails, fix the cause, not the test.

---

## 5. Tool use and verification

- Prefer running the code to guessing about the code. If a test suite exists, run it. If a linter exists, run it. If a type checker exists, run it.
- Never report "done" based on a plausible-looking diff alone. Plausibility is not correctness.
- When debugging, address root causes, not symptoms. Suppressing the error is not fixing the error.
- For UI changes, verify visually: screenshot before, screenshot after, describe the diff.
- Use CLI tools (gh, aws, gcloud, kubectl) when they exist. They are more context-efficient than reading docs or hitting APIs unauthenticated.
- When reading logs, errors, or stack traces, read the whole thing. Half-read traces produce wrong fixes.

---

## 6. Session hygiene

- Context is the constraint. Long sessions with accumulated failed attempts perform worse than fresh sessions with a better prompt.
- After two failed corrections on the same issue, stop. Summarize what you learned and ask the user to reset the session with a sharper prompt.
- Use subagents (Claude Code: "use subagents to investigate X") for exploration tasks that would otherwise pollute the main context with dozens of file reads.
- When committing, write descriptive commit messages (subject under 72 chars, body explains the why). No "update file" or "fix bug" commits. No "Co-Authored-By: Claude" attribution unless the project explicitly wants it.

---

## 7. Communication style

- Direct, not diplomatic. "This won't scale because X" beats "That's an interesting approach, but have you considered...".
- Concise by default. Two or three short paragraphs unless the user asks for depth. No padding, no restating the question, no ceremonial closings.
- When a question has a clear answer, give it. When it does not, say so and give your best read on the tradeoffs.
- Celebrate only what matters: shipping, solving genuinely hard problems, metrics that moved. Not feature ideas, not scope creep, not "wouldn't it be cool if".
- No excessive bullet points, no unprompted headers, no emoji. Prose is usually clearer than structure for short answers.

---

## 8. When to ask, when to proceed

**Ask before proceeding when:**
- The request has two plausible interpretations and the choice materially affects the output.
- The change touches something you've been told is load-bearing, versioned, or has a migration path.
- You need a credential, a secret, or a production resource you don't have access to.
- The user's stated goal and the literal request appear to conflict.

**Proceed without asking when:**
- The task is trivial and reversible (typo, rename a local variable, add a log line).
- The ambiguity can be resolved by reading the code or running a command.
- The user has already answered the question once in this session.

---

## 9. Self-improvement loop

**This file is living. Keep it short by keeping it honest.**

After every session where the agent did something wrong:

1. Ask: was the mistake because this file lacks a rule, or because the agent ignored a rule?
2. If lacking: add the rule under "Project Learnings" below, written as concretely as possible ("Always use X for Y" not "be careful with Y").
3. If ignored: the rule may be too long, too vague, or buried. Tighten it or move it up.
4. Every few weeks, prune. For each line, ask: "Would removing this cause the agent to make a mistake?" If no, delete. Bloated AGENTS.md files get ignored wholesale.

Boris Cherny (creator of Claude Code) keeps his team's file around 100 lines. Under 300 is a good ceiling. Over 500 and you are fighting your own config.

---

## 10. Project context

**Fill this in per project. Keep it specific. Delete sections that don't apply.**

### Stack
- Language and version: Python >=3.10 (pyproject.toml:11) — project `youtube-automation-pipeline` 4.1.0, setuptools backend, Windows-only target.
- Framework(s) / key deps: playwright>=1.40, youtube-transcript-api, python-docx, faster-whisper, openai-whisper, torch>=2.0, tqdm. Runtime deps in `venv\`; ruff/black/mypy/pytest global.
- Package manager: pip + venv (no uv/poetry/Makefile/package.json — verified absent).
- Runtime / deployment target: Windows-only desktop/browser-automation pipeline (CDP, named pipes, hardware FFmpeg).

### Commands
- Install: `python -m venv venv; .\venv\Scripts\Activate.ps1; pip install -r requirements.txt; pip install -r requirements-dev.txt; python -m playwright install --with-deps`. NOTE: requirements-dev.txt currently has TODO literal ``` fence lines (rows 1, 44) that break pip — flag but do not fix.
- Build: none (no build step; setuptools package).
- Test (all): `python -m pytest tests/ -v` (full) / `python -m pytest tests/unit -v` (CI scope); must run from repo root.
- Test (single file): `python -m pytest tests/unit/test_timeline.py -v`
- Lint: `ruff check . --fix` ; `ruff format --check .`
- Typecheck: `mypy .` (strict + ignore_missing_imports)
- Run locally: `python run_agency.py` (supervisor) or per-phase entrypoints.
- Also: `pre-commit run --all-files`

Prefer single-file or single-test runs during iteration. Full suites are for the final verification pass.

### Layout
- Source lives in: root-entrypoint `.py` scripts (run_agency.py supervisor + per-phase: automate_all.py, refine_script.py, generate_voice.py, stitch_chapters.py, automate_audacity.py, faster_whisper_transcribe_audio.py, correct_transcript_spelling.py, flow_image_generator.py, script_image_generator.py, fix_timestamps.py, compile_video.py, generate_thumbnail.py) + planning layer modules (pipeline_manifest.py, json_sanitizer.py, validator.py, gemini_controller.py, roadmap_orchestrator.py, prompt_planner.py, gemini_utils.py, utils.py).
- Tests live in: `tests/` (unit/, integration/, mocks/, conftest.py root).
- Do not modify: youtube_runs/, venv/, .git, __pycache__, legacy_and_utilities/, Implementation plans/, Security Division Analysis/, .agents/, .gemini/, .opencode/, .specify/, .superpowers/, graphify-out/, docs/, .env, *.json checkpoints, *.log, browser profiles (gitignored / ruff-excluded).

### Conventions specific to this repo
- Naming: snake_case modules, single-package flat layout at root.
- Import style: strict DAG — planning layer flow_image_generator → pipeline_manifest → json_sanitizer → validator → gemini_controller → roadmap_orchestrator → prompt_planner; never import upward.
- Error handling pattern: subprocess list args + shell=False; all JSON/text encoding="utf-8" ensure_ascii=False; atomic config writes NamedTemporaryFile+os.replace+fsync; never bare pytest.
- Testing pattern and framework: pytest, testpaths=tests, markers unit/integration, addopts -v --strict-markers --tb=short; conftest.py adds repo root to sys.path.

### Forbidden
- Never add cloud SDKs google-generativeai/openai/anthropic; all AI via Playwright CDP 127.0.0.1:9222.
- Never taskkill /IM chrome.exe (kill only PID on port).
- Never input_value() on contenteditable; follow Flow selector rules.
- Never destructive-overwrite checkpoints; schema changes need backward-compatible migration.
- QSV_LOOKAHEAD=0 mandatory.
- Never commit .env, runtime_state.json, *_checkpoint.json, pipeline.json, video/WAVs.


### This project: YouTube Al-Daheeh Automation Pipeline


> Scope: `image_generation/` — `youtube-transcript-api` → Gemini CDP → AI Studio TTS → Audacity Named Pipes → Faster-Whisper → Google Flow → FFmpeg QSV/NVENC. Windows-only (`ctypes.windll`, `\\.\pipe\ToSrvPipe`, `CREATE_NEW_CONSOLE`). Python 3.10+ (`pyproject.toml:11`). No cloud SDKs — never add `google-generativeai`/`openai`/`anthropic`; all AI via Playwright CDP `127.0.0.1:9222`.

## Stack & repo boundaries

- **Single-package monorepo.** Entrypoints: `run_agency.py` (supervisor) or single-phase: `automate_all.py` → `refine_script.py` → `generate_voice.py` → `stitch_chapters.py`/`automate_audacity.py` → `faster_whisper_transcribe_audio.py` → `correct_transcript_spelling.py` → `flow_image_generator.py` (or `script_image_generator.py`) → `fix_timestamps.py` → `compile_video.py` → `generate_thumbnail.py`. See `README.md:207` + `Project-workflow.md:5`.
- **State in `youtube_runs/<Title>/` (gitignored).** Never commit `.env`, `runtime_state.json`, `*.json` checkpoints (`pipeline.json`, `*_checkpoint.json`, `voice_generation_manifest.json`, `compile_checkpoint.json`, `planning_checkpoint.json`). Batch: `run_agency.py` scans for `final_output.txt` and drives `pipeline.json` (`translate, refine, voice, audacity, stitch, transcribe, images, fixtimes, video, thumbnail` in `run_agency.py:66`).
- **Planning layer DAG (2026-08):** `flow_image_generator.py` → `pipeline_manifest.py` → `json_sanitizer.py` → `validator.py` → `gemini_controller.py` → `roadmap_orchestrator.py` → `prompt_planner.py`. Strictly acyclic — never import upward. `validator.py` owns pure utils `flatten_visual_prompt_to_diffusion_text`/`enforce_arabic_in_prompt`/`purge_subtitle_phrases`.

## Setup — Windows PowerShell, order matters

```powershell
python -m venv venv; .\venv\Scripts\Activate.ps1   # repo uses venv\, not .venv
pip install -r requirements.txt
pip install -r requirements-dev.txt   # ruff, black, mypy, pytest-cov (pyproject.toml:34)
python -m playwright install --with-deps
# Externals: FFmpeg/FFprobe on PATH (winget install Gyan.FFmpeg), Audacity 3.x → Preferences→Modules mod-script-pipe=Enabled, Chrome/Opera --remote-debugging-port=9222 --user-data-dir=C:\ChromeDebugProfile
copy .env.example .env   # fill TELEGRAM_*, CDP_PORT, model routing; ACTIVE_PROFILE_INDEX in runtime_state.json (utils.py:269)
```

- Runtime deps in `venv\`; `ruff/black/mypy/pytest` in global python. `pydantic>=2.0` required both places (2026-08).

## Verify — run before concluding any refactor

```powershell
python -m pytest tests/unit -v                         # CI scope; full = python -m pytest tests/ -v
python -m pytest tests/unit/test_timeline.py -v        # single-file example
python -m pytest tests/ --cov=. --cov-report=term-missing
ruff check . --fix
ruff format --check .          # pre-commit uses ruff-format, not black directly
black --check --line-length 100 .  # pyproject.toml:55 line-length 100, exclude youtube_runs/venv
mypy .                         # strict + ignore_missing_imports (pyproject.toml:93)
pre-commit run --all-files
```

- Always `python -m pytest` from repo root — bare `pytest` fails (`tests/conftest.py` needs cwd on `sys.path`). Baseline 2026-08-26: unit 170 / integration 17 passed; integration needs real `ffmpeg lavfi`.

## Pipeline execution & idempotency

- **Supervisor:** skips completed `pipeline.json` flags, `clean_browser_tabs()` between phases, Telegram on crash/timeout. `compile_video.py` chunk 300s / final 3600s; `video`+`thumbnail` done → skip folder (`run_agency.py:154`).
- **Never destructive-overwrite** checkpoints without confirmation; schema changes need backward-compatible migration (`CLAUDE.md:242`).
- **Toggles (`.env`):** `ENABLE_REFINE_SCRIPT`, `FLIP_AUDACITY_ORDER`, `IMAGE_GENERATOR_TYPE=flow|script`, `WHISPER_ENGINE=faster_whisper|hard_whisper` (`run_agency.py:164`).
- **Images state machine:** `pipeline_manifest.json` gates resume. `script_hash=SHA256(transcript+template+presets)` mismatch invalidates caches. Chunk `{PENDING, VERIFIED, REPAIRED, FAILED}` — `FAILED` dumps `debug/malformed_chunk_N.json` then `ChunkPlanningError`. `master_roadmap.jsonl` source of truth (migrates `master_roadmap.txt`); paging `ROADMAP_WINDOW_SIZE=25`, planning `FLOW_CHUNK_SIZE=15`.

## Config sources of truth (executable > prose)

- **`.env` + `.env.example`:** `SCRIPT_BREAKER_MODEL=Flash` `SCRIPT_TRANSLATOR_MODEL=Pro` `VOICE_GENERATOR_MODEL=Flash` `IMAGE_PLANNER_MODEL=Flash` `REFINE_MODEL=Flash` `THUMBNAIL_MODEL=Pro`; `TTS_MODEL=gemini-2.5-pro-preview-tts` `TTS_VOICE_NAME=Achird` `TTS_TEMPERATURE=1.1` `TTS_PROACTIVE_RELOAD_INTERVAL=40`; Flow `FLOW_IMAGE_MODEL=Nano Banana 2 Lite` `FLOW_IMAGE_COUNT=1x` `FLOW_ASPECT_RATIO=16:9` `FLOW_DISABLE_AGENT=true` `FLOW_CHUNK_SIZE=15` `GEMINI_SESSION_RESET_THRESHOLD=100`; `CDP_PORT=9222` `BROWSER_TYPE=chrome` `FAILOVER_RETRY_LIMIT=3`; `ACTIVE_PROFILE_INDEX` in `runtime_state.json` via `utils.rotate_profile_index()` (`utils.py:303`).
- **`video_config.txt`:** `2560x1440@30` `yuv420p` `high@5.1`, `CHUNK_SIZE=20`, `QSV_LOOKAHEAD=0`, Ken Burns `1.0-1.08 smoothstep upscale 1.12` VBV `35000k/70000k` `FFMPEG_THREADS=4` `AUDIO 320k/48k I-14 TP-1 LRA11`. CPU fallback `libx264 veryfast crf17 tune animation`.
- **`transcribe_config.txt`:** `WHISPER_MODEL_SIZE=small` `WHISPER_LANGUAGE=ar` `VAD true`, `IMAGE 2.2s/3.5s/4.8s 5-12 words`, `SUB 4/2 words gap 0.35s`, `IMAGE_PAUSE_SPLIT 0.40s` (`transcribe_config.txt:26`), `image_timestamps.txt` is sync anchor.
- **`daheeh_config.json:8` + `audit_rubric.md`:** 30/70 Fusha/Amiya, 1-3-1 Provost cadence, Tashkeel `كِدَه, بِيُقول, هُوبَّا, قِسط`, 10-point audit. `refine_script.py` strips `<thinking>`/`<slang_ledger>`.

## Gotchas — would miss without help

- **QSV:** `QSV_LOOKAHEAD=0` mandatory (`compile_video.py:46`, `video_config.txt:41`) — `>0` starves pool on sw-decoded inputs. `format=nv12` for QSV else `yuv420p`; fallback `h264_qsv → h264_nvenc → libx264` via `ffmpeg -encoders` (`compile_video.py:227`).
- **FFmpeg 32KB limit:** graphs >1K chars → `temp_clips/filter_chunk_*.txt` + `-filter_complex_script` (`compile_video.py:1000`). Zero-drift `frame_count=round(duration*30)`, clip 0 at frame 0, CFR `fps_mode cfr` (`compile_video.py:726`). WinGet FFmpeg via `%LOCALAPPDATA%\Microsoft\WinGet\Links` (`compile_video.py:15`).
- **CDP:** `127.0.0.1:9222` not `localhost` (IPv6 fails). Kill only PID on port via `kill_cdp_chrome(port)` (`netstat -ano` + `taskkill /F /T /PID>100`, poll 4s) — never `taskkill /IM chrome.exe` (`utils.py:123`). `launch_browser_with_profile` wipes `SingletonLock` and verifies `http://127.0.0.1:{port}/json/version` (`utils.py:255`).
- **Gemini injection/completion:** via `gemini_controller.inject_prompt_via_cdp` ladder (`insert_text`→clipboard Ctrl+V→`execCommand`→`fill()` only <500 chars) + ≥95% `inner_text()` gate before submit; never `input_value()` on contenteditable. Completion = tri-factor `wait_for_gemini_turn_completion`: stop-absent + 3× stability@500ms HARD, action-bar SOFT. Ephemeral chat per roadmap page + per chunk (+jitter 1.5-3s). Pages fixed 25 lines — never tail-merge. Validator WEAK `TS[i]≤TS[i+1]`; equal TS ⇒ strict `index`+`frame_index`.
- **Gemini polling:** never `time.sleep`. `gemini_utils.wait_for_gemini_response` stop absent + 5× stable reads (~5-6s) + last `model-response` `len>=1`; fast-fail on error card (`gemini_utils.py:372`). Strip `Gemini said`/`قال Gemini`, handle `Analyzing/Thinking/Visualizing`.
- **Audacity:** `\\.\pipe\ToSrvPipe`/`FromSrvPipe`, every cmd ends `\n`, read until empty line. Always `SelectAll:` before DSP. Sync presets `YouTube_Voice_Optimizer.txt`→`%APPDATA%\audacity\macros\`; wipe `SessionData`/`AutoSave` before open (`CLAUDE.md:105`).
- **Flow selectors (validated 2026-08-20):** cascade only. `wait_for_flow_app_ready` 3s post-hydration. Submit `button:has(i.google-symbols:text-is('arrow_forward'))` (+ Enter fallback). `Describe your character` = `textarea[placeholder*='Describe your character']` or contenteditable `innerText`; `+ New Character` only empty-gallery. Body popup = LAST `contenteditable` floating card. Never fill workspace bar `What do you want to create?`. Mount verified via `/character/<id>` + `Done`. Assets memoized `flow_assets_profile_*.json` + `flow_workspace_url_profile_*.txt`; `SUMMON_ASSET` via `Search assets`→`Add to Prompt`.
- **Images:** tiered `base64 data: → page.request.get() → blob fetch in-page → de-hovered screenshot` (`flow_image_generator.py:226`). Never `<canvas>` primary (CORS-tainted); use `img_locator.screenshot(type="png")` after `mouse.move(100,15)`. Validate `>20KB`, PIL verify, `>100px`, PNG `89 50 4E 47`/JPEG `FF D8`.
- **Voice:** Bezier mouse, MD5 dedup across `Chapter_N.wav` (delete+reload if `N==N-1`), proactive reload every `TTS_PROACTIVE_RELOAD_INTERVAL=40` (`generate_voice.py`).
- **Subprocess & UTF-8:** list args + `shell=False`; all JSON/text `encoding="utf-8"` `ensure_ascii=False`; `sys.stdout.reconfigure(encoding='utf-8')` + `chcp 65001`.
- **Config writes:** atomic `NamedTemporaryFile`+`os.replace`+`fsync` (`utils.py:282`).

## Subagent task matrix

| Task | Script | Checklist |
| --- | --- | --- |
| Linguistic Transcreation | `automate_all.py` | 30/70 ratio + academic fallback on safety block |
| Script Doctor Polish | `refine_script.py` | `daheeh_config.json` Tashkeel; strip `<thinking>`/`<slang_ledger>` |
| Voice Synthesis | `generate_voice.py` | Bezier mouse; MD5 dedup; `voice_generation_manifest.json` |
| DSP Mastering | `automate_audacity.py` | Named Pipes alive; `SelectAll:` before effects |
| Audio Stitching | `stitch_chapters.py` | lossless Wave frames, zero drop |
| ASR & Cadence Pacing | `faster_whisper_transcribe_audio.py` | 3-6 words/chunk; VAD `0.40s`; `transcribe_config.txt` |
| Lexical Spellcheck | `correct_transcript_spelling.py` | `difflib.SequenceMatcher` vs `refined_script.txt`, timestamps untouched |
| Roadmap Paging | `roadmap_orchestrator.py` | fixed 25-row pages; anchor = last row K-1; atomic jsonl rewrite/page |
| JSON Planning | `prompt_planner.py` | slice ±1 buffer; ephemeral session; self-heal ≤2 same-session |
| Visual Generation | `flow_image_generator.py` | `@asset` chip injection; native screenshot; continuity |
| Thumbnail | `generate_thumbnail.py` | self-critique scoring, 2 variants |
| Video Compositing | `compile_video.py` | zero-drift frames; `filter_complex_script`; QSV→NVENC→CPU |

## Style & workflow

- **Formatter/linter/type:** `black --line-length 100` (exclude `youtube_runs,venv,.git,__pycache__` — `pyproject.toml:54`), `ruff` `E,W,F,I,B,C4,UP` (`pyproject.toml:72`), `mypy --strict --ignore-missing-imports` (`pyproject.toml:93`). Fix `ruff check --fix` + `ruff format`.
- **OpenCode:** `opencode.json` → `default_agent: AGENTS-PROJECT`; lean-ctx shadow mode; `AGENTS.md` via `instructions`. Caveman mode for agent comms; code/commits normal.
- **Git:** `youtube_runs/`, `Implementation plans/`, `Security Division Analysis/`, `.agents/`, `.opencode/`, `graphify-out/` gitignored. Never auto-commit video/WAVs.

## References

- `CLAUDE.md` — 425-line architecture, DOM recovery matrix, Ken Burns math, Audacity protocol
- `README.md` — quickstart, pipeline flow, output hierarchy
- `Project-workflow.md` — ADRs, IPC diagram, fault-tolerance table
- `audit_rubric.md` — 10-point broadcast quality gate

---

## Agent skills

### Issue tracker

GitHub Issues in Snoozer10/local-youtube-automation. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context (one `CONTEXT.md` + `docs/adr/` at repo root). See `docs/agents/domain.md`.

---

## 11. Project Learnings

**Accumulated corrections. This section is for the agent to maintain, not just the human.**

When the user corrects your approach, append a one-line rule here before ending the session. Write it concretely ("Always use X for Y"), never abstractly ("be careful with Y"). If an existing line already covers the correction, tighten it instead of adding a new one. Remove lines when the underlying issue goes away (model upgrades, refactors, process changes).

- (empty)

---

## 12. How this file was built

This boilerplate synthesizes:
- Sean Donahoe's IJFW ("It Just F\*cking Works") principles: one install, working code, no ceremony.
- Andrej Karpathy's observations on LLM coding pitfalls (the four principles: think-first, simplicity, surgical changes, goal-driven execution).
- Boris Cherny's public Claude Code workflow (reactive pruning, keep it ~100 lines, only rules that fix real mistakes).
- Anthropic's official Claude Code best practices (explore-plan-code-commit, verification loops, context as the scarce resource).
- Community anti-sycophancy patterns (explicit banned phrases, direct-not-diplomatic).
- The AGENTS.md open standard (cross-tool portability via symlinks).

Read once. Edit sections 10 and 11 for your project. Prune the rest over time. This file gets better the more you use it.
