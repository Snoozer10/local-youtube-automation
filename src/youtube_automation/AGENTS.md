# Source package contract

## Purpose
Own Python implementation boundaries and runtime contracts under src/youtube_automation/. Root facade shims that delegate into this package are governed by this contract too.

## Ownership
- core/: shared utilities, fenced resource leases, atomic disk writes, profile management, exact-PID owned-browser registry, native Windows identity and process supervision.
- audio/ and speech/: TTS, Audacity IPC/mastering, chapter stitching, transcription, VAD alignment and spelling correction.
- timeline/ and nlp/: canonical timestamp reconciliation and LLM JSON repair/sanitization.
- prompts/: validated schemas, dynamic loading, negative-prompt injection and installed prompt resources.
- browser/: loopback CDP, tab lifecycle, shared browser/clipboard leases and Gemini web UI controllers.
- visuals/: Flow generation, continuity assets, image extraction and OCR collision gates.
- video/: FFmpeg composition, encoder selection, Ken Burns transforms, filtergraphs and subtitles.
- production/: adaptive channel and episode behavior; production/AGENTS.md owns detailed production contracts.
- orchestrator/: pipeline stages and batch execution coordination.

## Local Contracts

### Shared resources and process ownership
- Browser, clipboard, Audacity and encoder entrypoints acquire their installation-wide lease in adaptive and legacy paths. Cleanup may terminate only the exact pipeline-owned process.
- The owned-browser registry binds process identity and active profile. Revalidate PID, creation identity, executable, listener, profile and lease before recovery; never terminate an unowned browser.
- The injected window-readiness observer requires PID and creation identity, stable unique main-window observations and bounded callbacks. Recovery, welcome and unknown states fail closed without dismissing dialogs.
- Spawn child processes with shell=False and argument lists. Preserve dependency precedence and environment in direct-interpreter bootstraps; a venv path alone does not prove correct interpreter ownership.
- The supervisor parent is distinct from its worker. The supervisor-owned process PID must equal the actual payload interpreter PID; launcher-wrapper PID is insufficient. Prove native Job containment includes that exact process before live use.
- Worker launch ordering is strict: start the isolated direct interpreter, then wait for a PID-bound acknowledgment proving its own native Job contains the actual worker payload; initialize the worker venv only after that acknowledgment. The acknowledged PID must identify the payload interpreter, not a launcher wrapper.
- Run the stdlib receipt sealer as a separate child in its own native Job. Establish its actual payload PID and exact Job membership before acknowledgment; a launcher-wrapper PID is never a substitute.
- core/process_supervisor.py uses fixed monotonic phase limits: pipes 25 seconds and worker 120 seconds. Account conservatively for interrupted sends. Only the explicitly owned Audacity launch may break away; worker/helper cleanup targets exact owned handles.
- Native Audacity inspection and owned-HWND BMP capture use timeout-bound isolated helpers. Verify exact FILETIME, PID, executable and ownership before/after; no desktop fallback. Production lifecycle does not clear SessionData or AutoSave.
- Audacity lifecycle gates pipe opening and each Help/SelectAll handshake. The inert one-Help probe holds the audio lease in its parent, validates a fresh bounded grant, verifies both pipe-server PIDs and requires current image-bound inspection; it performs no SelectAll or DSP. Offline checks do not authorize live use.
- For packaged Windows Python, distinguish reported sys.executable alias from native process image. Verify the image through the owned process handle; preserve alias metadata and PID/Job checks.
- One-Help phases retain a 120-second worker watchdog, 0.25-second worker reap, 5-second killable receipt sealing and 0.25-second sealer reap: 125.5 seconds of nominal timed components plus separately recorded setup, I/O and scheduling overhead. The identity phase keeps the five-second pre-first-event bound and resets once at the first validated identity; keep the outer 120-second worker deadline unchanged. Parent acknowledgment fsync is startup metadata overhead, not a foreground receipt fallback. The stdlib sealer is a separate child with its own native Job and PID-bound startup acknowledgment.
- Both production Audacity pipe-server PIDs must match the expected Audacity PID before any command. Windows frames commands as command + CRLF + NUL and opens both text handles with newline=''; POSIX frames commands with LF. Accept a reply only after explicit BatchCommand completion: status and terminal blank boundary. Preserve RuntimeError with the did not confirm success prefix for operational strict-reply failures; invalid timeout and response-size validation remain ValueError; deadline expiry remains TimeoutError. Help is bounded readiness evidence, not proof later GUI commands are ready.

### Audio, transcription and browser boundaries
- TTS uses the shared browser lease. AI Studio requires exact HTTPS origin https://aistudio.google.com, one unique visible current prompt and the semantic Create new dialog → Text path.
- Before script fill or Run, verify requested model, configured channel voice, settings panel and selector from current DOM/ARIA state. Missing, ambiguous, stale, mismatched or unreadable state fails closed before typing/sending. Reopen settings after changes and reverify required model/voice. Attempt temperature fill/readback when supported; optional quality-setting misses are warnings.
- Preserve the public legacy model-selector helper. Production TTS uses the guarded semantic flow, never coordinate selection or chat fallback. A quota-bound adaptive Run dispatches once; false or ambiguous acknowledgment is conservatively accounted and stops without retry. An explicit null synthesis voice or source-audio receipt continues to block TTS.
- On an explicit Gemini App quota-exhaustion report, preserve a quota_exhausted receipt and finish that failed attempt. Switch only the pipeline-owned CDP browser after listener/profile verification, recompute the profile-bound recipe, then retry the exact request within the bounded failover ring.
- Browser target enumeration returns a verified list or redacted TargetProbeError. Transport, JSON or schema errors stop adaptive TTS before CDP attach.
- Gemini completion requires a new response node, semantic Stop absent, then three stable 500 ms observations. Generic spinners/SVG buttons do not prove active generation or completion.

### Timeline, prompts and media
- timeline.json is the single source of truth. Reconcile timestamps against it; persist UTF-8 data through a temporary file, fsync and os.replace.
- Runtime .txt prompt templates mirror canonical root prompts/ bytes recursively, including turns/fragments. Verified checkouts use root assets; installed packages use package-local resources.
- Installed no-channel defaults project only canonical daheeh_config.json dialect ratios and ordered pronunciation lexicon into default_prompt_config.json. Preserve explicit CONFIG_PATH and channel/model overrides; unrelated prefix configuration is not a default source.
- The roadmap planner keeps its fixed 25-row window; do not tail-merge pages. Its validator's weak TS[i] ≤ TS[i+1] ordering requires strict index and frame_index tie handling.
- Use file-backed FFmpeg filter graphs for long graphs: -/filter_complex from the retained file path. The deprecated -filter_complex_script option is not available in the CI FFmpeg. Preserve zero-drift frame_count=round(duration×30), clip 0 at frame 0 and CFR fps_mode cfr.
- QSV keeps QSV_LOOKAHEAD=0 and nv12 upload surfaces. Probe preference is QSV → NVENC → CPU; a hardware failure during compilation moves to an isolated CPU generation while retaining prior clips, journals and failure evidence.
- video/engine.py owns compilation validation and publication. Require contiguous spans starting at frame 0, a supported target and source audio within one frame of the timeline. Reject output paths that resolve or hard-link to narration, image or subtitle inputs. Validate the pending video against decoded dimensions, exact FPS, yuv420p/tv and independent audio/video durations before atomic promotion; preserve the prior output and rejected candidate on failure.
- video/receipt.py owns bounded final-artifact JSON receipts and their public verification API. Prepare immutable .compilation-receipts/<artifact-sha256>.json before the single video rename; interrupted work preserves the old or complete new pair and retains orphan evidence. Verify current artifact hash/size, measured media facts and one-frame audio/video drift; consumers also match the current render target and frame budget. Receipts establish technical evidence, not editorial approval or authentication.
- External ASS is copied byte-for-byte and rendered at episode-global timestamps within the shared per-span filtergraph; subtitle bytes participate in cache identity. The legacy adapter prefers an existing ASS over automatically derived dialogue; explicit public requests may supply both layers.
- The current Flow UI watchdogs, when active for an authorized run, remain 120 seconds without progress, 360 seconds hard limit and 20 seconds for card spawn. These limits do not authorize a run.
- Offline PCM WAV validation separates parseability from compliance, reports byte-rate warnings without rewriting audio, and bounds offsets to complete frames or the explicit data-end boundary.

### Production and compatibility
- Select a saved channel explicitly. Analyze raw scripts before translation. Each pasted source URL compiles its own content-bound episode visual strategy before translation or planning.
- Professor Yashrah uses Achird; Soldier's Sledger uses Charon; Snoozer Anime's explicit null voice remains valid profile data and blocks TTS. Soldier's Sledger starts from researched current/trending topics, then Gemini script creation and refinement; it does not require a copied source URL. Owner backup videos are comparison material, not automatic narration or factual sources.
- Adaptive topics have an absolute 400-image ceiling; short videos receive lower duration budgets. The Professor pilot is capped at 20 images. Inspect each rendered shot for narration relevance, coherent progression, continuity and readability; no stage after visuals advances before the current visual audit passes.
- Opt-in Flow canaries require an explicit run and one to three distinct current shot IDs with all scene-reference dependencies. Use only the current validated plan and complete critic cache; never open Gemini or request new model work. Preserve canonical order, stop on first failure and verify only the selected scope.
- Bind human rejection to verified preview/plan hashes, preserve prior evidence, revoke its visual audit and require a revised preview with fresh complete review before publication. Professor visual criteria live in tasks/professor-visual-playbook.md; progress is tracked in tasks/adaptive-visual-tasks.md.
- Root facade proxies remain transparent and keep legacy CLI invocation plus bidirectional monkeypatch synchronization for compile_video.py, flow_image_generator.py, generate_voice.py, automate_audacity.py, stitch_chapters.py, faster_whisper_transcribe_audio.py, correct_transcript_spelling.py, fix_timestamps.py, text_gate.py, timeline_engine.py, validator.py, json_sanitizer.py, utils.py and gemini_utils.py.
- flow_image_generator.py and visuals/flow_generator.py are the primary visual engine; roadmap_orchestrator.py, prompt_planner.py and asset_studio.py govern prompt planning and asset presets. script_image_generator.py is the legacy alternative and exclusively owns prompts/visual_style.txt and prompts/visuals_plan.txt.

## Work Guidance
- Follow feature, debugging and release routes in docs/agents/workflows.md.
- For production changes, also read production/AGENTS.md and preserve its interfaces and recovery contracts.

## Verification
- Use the repository checks routed in docs/agents/workflows.md. Do not narrow mypy discovery or scope, add suppressions or stub overlays to pass a gate.

## Child DOX Index
- production/AGENTS.md: adaptive channel, episode, editorial, asset and durable production-state contracts.
