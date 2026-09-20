# Studio Viewer Architectural Overhaul & Inspection Suite Plan (v3 — Branch Isolated)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul, repair, and upgrade `tools/viewer_generator.py` and `studio_viewer.html` to eliminate empty-frame failures in standard pipeline runs, provide frame-accurate media synchronization (Video/Audio/Virtual clock), add interactive visual QA tools (Split Curtain wipe slider, synchronized pan/zoom, broadcast/platform safe-zone overlays), and replace all hardcoded magic numbers with dynamic data scaffolding.

**Architecture:** A unified 5-tier data ingestion cascade in Python that unions all frame indices across Socratic, baseline prompts, roadmaps, timeline spans, and disk files with two-pass timestamp-validated alignment and dynamic relative path calculations. In the frontend, an air-gapped, zero-dependency broadcast NLE inspection suite featuring a tri-tier chronometric clock authority, single-source audio policy (`video.muted = true`), $O(\log N)$ binary-search frame sync loop, 3-frame asynchronous lookahead pre-decoder, composite-only GPU wipe slider, and dynamic runtime filter harvesting.

**Branch & Git Isolation:** Governed by `git-workflow-and-versioning` skill. Implementation is quarantined on a dedicated branch `feat/studio-viewer-overhaul` branched cleanly off `main`, preventing interference with concurrent AI agent sessions (OpenCode / Antigravity CLI) active on `feat/adaptive-prompt-engineering`.

**Tech Stack:** Python 3.11, Pytest, Git, Vanilla HTML5 / CSS3 (CSS Variables, Clip-Path, Flexbox/Grid), ES6+ JavaScript (`requestAnimationFrame`, Pointer Events, Audio/Video DOM APIs, Cairo/Tajawal RTL Typography), Playwright headless verification.

---

## ⚔️ Multi-Agent Adversarial Cross-Examination & Hardening Matrix

This plan incorporates the formal cross-examination critique delivered by **`adversarial_griller`** (`d6ac6dea`) in Round 2. All 5 lethal vulnerabilities identified during the cross-examination have been hardened into non-negotiable architectural requirements:

### Hardening Summary Matrix

| Vector | Adversarial Vulnerability Identified (Round 2) | Hardened Engineering Contract |
| :--- | :--- | :--- |
| **Q1: Span Alignment** | Naive `i - 1` arithmetic breaks on non-contiguous indices (deleted/merged frames) or 0-indexed prompts. | **Two-Pass Timestamp-Validated Span Alignment**:<br>• *Pass 1 (Chronometric)*: Match parsed prompt timestamp in seconds ($T_{\text{prompt}}$) to span where $T_{\text{start}} \le T_{\text{prompt}} < T_{\text{end}}$.<br>• *Pass 2 (Strict Index Fallback)*: Exact index match. Apply offset *only* if $\min(\text{span\_idx}) == 0$ AND $\min(\text{prompt\_idx}) == 1$ AND counts are equal. Otherwise, preserve keys and flag cardinality mismatch in metadata. |
| **Q2: Media Control** | Scrubber flooding crashes video decoder; dual audio tracks in MP4 and WAV create severe echo. | **Debounced Scrub State Machine & Single-Source Audio**:<br>• During pointer drag: pause media, throttle updates to 30Hz via RAF, use `fastSeek()`, update UI frame immediately via virtual index. Resume on pointer up.<br>• **Strict Single-Source Audio Policy**: Video proxy is **always muted** (`video.muted = true`). Audio is driven 100% by `<audio src="full_episode_voice.wav">` with `video.currentTime = audio.currentTime` on each tick.<br>• Master duration = $\max(\text{audio.duration}, \text{video.duration}, \text{timeline.duration})$ with boundary clamping. |
| **Q3: Performance** | Synchronous image decode triggers 60fps frame drops; unthrottled 1000Hz mouse events overwhelm event loop. | **3-Frame Lookahead Pre-decoder & RAF Gating**:<br>• Asynchronously pre-decode upcoming $\pm 3$ frames (`new Image(); img.src = url; await img.decode();`).<br>• **Change-Detection Gate**: Skip DOM updates if resolved frame index has not changed. Cancel RAF loop entirely when paused.<br>• Buffer mouse pan/zoom coordinates and commit CSS `translate3d(...) scale(...)` strictly on the next RAF tick. |
| **Q4: Split Wipe Misalignment** | Differing intrinsic aspect ratios/resolutions cause letterbox offsets and jumpy wipe comparisons. | **Forced Geometric Normalization & Resolution Inspector**:<br>• Both layers locked in strictly identical coordinate containers (`position: absolute; width: 100%; height: 100%; top: 0; left: 0; object-fit: cover;`).<br>• Python inspects PIL/header dimensions of both images. If aspect ratios/resolutions differ (e.g. 1920x1080 vs 1792x1024), inject `⚠️ Resolution Mismatch: W1xH1 vs W2xH2` warning badge in UI. |
| **Q5: Automated Verification** | Risk of silent regressions and empty frame deployments (`const frames = [];`). | **Comprehensive 3-Tier CI/CD Test Matrix**:<br>• **Tier Ingestion Matrix**: Tests for (A) baseline-only, (B) socratic+baseline, (C) timeline+disk only, (D) error handling on corrupt input.<br>• **Relative Path Disk Audit**: Automated test verifying every non-null path in JSON exists on disk relative to output HTML.<br>• **Headless Smoke Test**: Playwright loads HTML and asserts `frames.length > 0`, filmstrip items match, and 0 uncaught console errors. |

---

## User Review Required

> [!IMPORTANT]
> **Branch Isolation & Concurrency Guard (`feat/studio-viewer-overhaul`):**
> The current repository working tree is on `feat/adaptive-prompt-engineering` and contains uncommitted modifications from a concurrent AI agent session working on prompt engineering. Under the `git-workflow-and-versioning` skill, Task 0 will create and switch to a dedicated, isolated branch `feat/studio-viewer-overhaul` branched cleanly off `main` (stashing concurrent uncommitted changes or using a git worktree). Zero work will be committed to `feat/adaptive-prompt-engineering`.

> [!IMPORTANT]
> **Single-Source Audio Authority (`video.muted = true`):**
> When `youtube_ready_video_720p.mp4` and `full_episode_voice.wav` are both present, the video element is strictly muted. Audio is rendered exclusively from the uncompressed master WAV file. This prevents phase-delayed echo from AAC export delay.

> [!NOTE]
> **Zero Breaking Changes for Existing Pipelines & Tests:**
> `tools/viewer_generator.py` preserves exact public interfaces:
> - `build_frame_records(run_dir: str, canary_dir: str | None = None, html_dir: str | None = None) -> list[dict[str, Any]]`
> - `generate_comparison_viewer_html(run_dir: str, canary_dir: str | None = None, output_html: str | None = None) -> str`
> The payload remains backward-compatible with legacy array consumers (`const frames = Array.isArray(payload) ? payload : payload.frames;`).

---

## Proposed Changes

```
tools/
└── viewer_generator.py           [MODIFY: 5-tier cascade, 2-pass alignment, media resolver, NLE engine]
tests/unit/
└── test_viewer_generator.py      [MODIFY: Add multi-run tests, media sync tests, wipe tests, path audit]
```

---

### Component 1: Data Ingestion & Media Resolution (`tools/viewer_generator.py`)

#### [MODIFY] `tools/viewer_generator.py`
- Add `parse_timestamp_seconds(ts_str: str) -> float | None` to parse `[MM:SS.mmm]` or `MM:SS` into absolute seconds.
- Add `format_visual_prompt(prompt_data: Any) -> str` to handle both structured dicts (`subject`, `action`, `setting`, `style`) and string prompts.
- Add `resolve_media_assets(run_dir: str, html_dir: str) -> dict[str, Any]` to find `full_episode_voice.wav` and `youtube_ready_video_720p.mp4` / `1080p.mp4` / `youtube_ready_video.mp4` and derive relative paths.
- Rewrite `build_frame_records()`:
  - Union indices across `flow_prompts_socratic.json`, `flow_prompts.json`, roadmap files, timeline spans, and disk files.
  - Implement **Two-Pass Timestamp-Validated Span Alignment** (Pass 1 Chronometric, Pass 2 Strict Index).
  - Calculate `start_time`, `end_time`, `duration`, `frame_count`, `punch_frame`, `camera_action`, `eye_line_elevation`.
  - Resolution inspection: Read image dimensions via PIL or PNG header, flag resolution mismatches.
  - Resolve paths: If file exists, `os.path.relpath(...)`. If missing, set to `None` for canary or fallback to baseline.
  - Compute SHA-256 hashes and flag duplicate hash collisions.
- Rewrite HTML/CSS/JS template in `generate_comparison_viewer_html()`:
  - Tri-tier media clock with `requestAnimationFrame` and binary search.
  - Scrubbing debounce and state machine with `fastSeek()`.
  - Single-source audio (`video.muted = true`, audio driven through WAV).
  - 3-frame asynchronous lookahead pre-decoder (`await img.decode()`).
  - Change-detection gate in RAF loop (skip DOM writes if frame unchanged; cancel on pause).
  - Split curtain wipe slider with forced geometric normalization (`position: absolute; object-fit: cover;`).
  - Synchronized pan & zoom with RAF-throttled pointer event buffering.
  - Broadcast safe zone overlays (SVG).
  - Dynamic chunk partitioning ($\lceil N/50 \rceil$) and dynamic filter facets.
  - Arabic RTL typography with Cairo/Tajawal and `<bdi>` isolation.
  - Batch Re-Gen CLI range syntax compressor.

---

### Component 2: Comprehensive Test Suite (`tests/unit/test_viewer_generator.py`)

#### [MODIFY] `tests/unit/test_viewer_generator.py`
- Preserve existing 3 tests:
  - `test_build_frame_records_and_duplicate_detection`
  - `test_baseline_backup_resolution_and_relative_paths`
  - `test_orthographic_feature_detection`
- Add new test: `test_universal_ingestion_without_socratic_prompts` (Case A: baseline-only like `What Do Animals Think Of Humans`).
- Add new test: `test_two_pass_timestamp_span_alignment` (verifies chronometric matching and non-contiguous index protection).
- Add new test: `test_media_assets_resolution` (verifies audio and video proxy resolution).
- Add new test: `test_resolution_mismatch_detection` (verifies aspect ratio mismatch badge generation).
- Add new test: `test_relative_path_disk_audit` (verifies that non-null paths in JSON resolve to physical files on disk).
- Add new test: `test_dynamic_scaffolding_in_generated_html` (verifies zero hardcoded "293" or "Chunk 1-6" in HTML).

---

## Implementation Tasks

### Task 0: Isolated Git Branch Creation & Workspace Protection
<!-- id: task-0-git-branch -->
**Rationale:** The current workspace is on `feat/adaptive-prompt-engineering` with uncommitted changes from a concurrent prompt engineering agent. In accordance with `git-workflow-and-versioning`, all studio viewer overhaul work must be quarantined on a dedicated branch.

- [ ] Safely preserve the concurrent agent's uncommitted changes on `feat/adaptive-prompt-engineering`:
  ```powershell
  git stash push -m "WIP: prompt engineering concurrent agent state" --include-untracked
  ```
- [ ] Create and check out dedicated branch `feat/studio-viewer-overhaul` off `main`:
  ```powershell
  git checkout -b feat/studio-viewer-overhaul main
  ```
- [ ] Verify clean working tree and active branch before editing code:
  ```powershell
  git branch --show-current
  git status
  ```

### Task 1: Universal Data Cascade & Two-Pass Alignment Engine
<!-- id: task-1-data-cascade -->
**Files:**
- Modify: `tools/viewer_generator.py:1-240`
- Test: `tests/unit/test_viewer_generator.py`

- [ ] Add `parse_timestamp_seconds` and `format_visual_prompt` helper functions.
- [ ] Implement `resolve_media_assets` to locate WAV audio and 720p/1080p MP4 proxies.
- [ ] Implement 5-tier index unioning across all prompt, roadmap, timeline, and disk sources.
- [ ] Implement Two-Pass Timestamp-Validated Span Alignment (Pass 1 Chronometric, Pass 2 Index Fallback).
- [ ] Implement image dimension inspection for resolution mismatch warning badges.
- [ ] Write unit tests in `tests/unit/test_viewer_generator.py`:
  - `test_universal_ingestion_without_socratic_prompts`
  - `test_two_pass_timestamp_span_alignment`
  - `test_media_assets_resolution`
  - `test_resolution_mismatch_detection`
- [ ] Run `python -m pytest tests/unit/test_viewer_generator.py -v` and confirm 100% pass.
- [ ] Atomic git commit: `git commit -m "feat(viewer): implement 5-tier data cascade and two-pass span alignment"`

### Task 2: Broadcast NLE Frontend HTML/CSS/JS Engine
<!-- id: task-2-frontend-engine -->
**Files:**
- Modify: `tools/viewer_generator.py:241-880`
- Test: `tests/unit/test_viewer_generator.py`

- [ ] Implement Tri-Tier Media Clock Authority (Video Proxy -> Master Audio WAV -> Virtual Clock).
- [ ] Enforce single-source audio policy (`video.muted = true`, audio driven through WAV).
- [ ] Implement debounced scrubber state machine with `fastSeek` and 30Hz RAF throttling.
- [ ] Implement 60fps RAF loop with $O(\log N)$ binary search and change-detection DOM gate.
- [ ] Implement 3-frame asynchronous lookahead pre-decoder (`await img.decode()`).
- [ ] Implement Split Curtain Wipe Slider with forced geometric normalization (`object-fit: cover;`).
- [ ] Implement Synchronized Pan/Zoom with pointer coordinate buffering.
- [ ] Implement SVG Broadcast Safe Zones (Action/Title safe, Foveal box, YouTube UI blackout simulator).
- [ ] Implement Dynamic Chunk Partitioning ($\lceil N/50 \rceil$) and dynamic facet harvesting.
- [ ] Implement Cairo/Tajawal Arabic RTL typography with `<bdi>` token isolation.
- [ ] Implement Batch Re-Gen CLI range syntax compressor (`--frames 1-4,12,18-19`).
- [ ] Write unit tests:
  - `test_dynamic_scaffolding_in_generated_html`
  - `test_relative_path_disk_audit`
- [ ] Run `python -m pytest tests/unit/test_viewer_generator.py -v` and confirm 100% pass.
- [ ] Atomic git commit: `git commit -m "feat(viewer): build broadcast NLE inspection engine with wipe slider and media sync"`

### Task 3: Full Run Regeneration & Multi-Episode Validation
<!-- id: task-3-validation-regeneration -->
**Files:**
- Output: `youtube_runs/What Do Animals Think Of Humans/studio_viewer.html`
- Output: `youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!/studio_viewer.html`

- [ ] Execute `python tools/viewer_generator.py --run-dir "youtube_runs/What Do Animals Think Of Humans"`.
- [ ] Inspect generated `studio_viewer.html` in `What Do Animals`:
  - Assert `const payload = ...;` contains 139 frames (NOT 0).
  - Verify audio path points to `full_episode_voice.wav` and video points to `youtube_ready_video_720p.mp4`.
- [ ] Execute `python tools/viewer_generator.py --run-dir "youtube_runs/Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!"`.
- [ ] Inspect generated `studio_viewer.html` in `Terrence Howard`:
  - Assert 293 frames loaded, chunks partitioned dynamically (Chunks 1–6), kinetic badges present.
- [ ] Run full unit regression suite: `python -m pytest tests/unit -v`.
- [ ] Run exercise pedagogy linter: `python tools/lint_exercises.py`.
- [ ] Atomic git commit: `git commit -m "chore(viewer): regenerate viewers and validate multi-episode compatibility"`

---

## Verification Plan

### Automated Tests
1. **Targeted Unit Tests:**
   ```powershell
   python -m pytest tests/unit/test_viewer_generator.py -v
   ```
2. **Full Unit Regression Suite:**
   ```powershell
   python -m pytest tests/unit -v
   ```
3. **Pedagogy Scaffold Linter:**
   ```powershell
   python tools/lint_exercises.py
   ```

### Manual Verification
1. Open `youtube_runs/What Do Animals Think Of Humans/studio_viewer.html` in browser:
   - Confirm 139 frames appear in filmstrip and counter shows `Frame 1 / 139`.
   - Press Spacebar: confirm master audio plays and scrubber moves smoothly at 60fps.
   - Drag scrubber: verify instant frame seek without audio crackle or decoder stall.
   - Press `W`: drag Split Curtain wipe slider across baseline and generated images; verify zero pixel offset.
   - Press `S`: verify Broadcast Action/Title safe zones and YouTube UI blackout overlay render crisply.
   - Select multiple frames and click `📋 Copy Re-Gen`: verify clipboard contains clean range (e.g. `--frames 1-5,12`).
