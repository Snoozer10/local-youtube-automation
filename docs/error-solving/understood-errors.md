# Understood Errors & Failure Modes

## Error Patterns

### QSV Lookahead Stream Corruption
- **Cause**: Setting `-look_ahead 1` with a non-zero `-look_ahead_depth` on Intel QSV (`h264_qsv`) hardware encoder when feeding software-decoded frames causes frame pool exhaustion in the hardware memory driver. This leads to silent corruption of the output video bitstream (missing pictures in access units, invalid NAL unit sizes) despite FFmpeg exiting with return code 0.
- **Solution**: Disable lookahead by setting `QSV_LOOKAHEAD=0` in the configuration.
- **Prevention**: Ensure lookahead is deactivated when executing hybrid software-to-hardware transcode chains on this hardware/driver baseline.

### Gemini Model Selector Hydration Timing
- **Cause**: Immediately after a Gemini SPA chat reset (`reset_chat_session`), the model selector button may still be mounting in the DOM. An immediate single-pass scan fails to find the button and returns `False`. If `open_ephemeral_session` treats model selection failure as a hard error, the entire orchestration turn aborts with `RuntimeError: [roadmap] failed to deliver initial turn`.
- **Solution**: (1) Add a polling deadline loop (up to 8s) in `select_gemini_model` to allow the SPA UI to hydrate. (2) Make `open_ephemeral_session` soft-fail if model selection still cannot locate the button, continuing with the session's default model as long as the prompt input box is live.
- **Prevention**: Never assume newly navigated or SPA-reset DOM nodes mount instantaneously; poll with a reasonable timeout, and treat non-critical UI customizations (like model dropdown selection) as resilient soft-failures.

### Post-Encode Validation in Mock Subprocess Environments
- **Cause**: Calling real post-encode validation (`ffprobe`) on output targets in unit/integration test suites that mock `subprocess.Popen` via `FakePopen` (which emits no physical video file on disk).
- **Solution**: Guard post-encode probing in assembly: validate strictly when physical files exist; in mock test environments (`PYTEST_CURRENT_TEST` or `MOCK_FFMPEG`), skip probing if no file was emitted on disk, while testing `validate_post_encode` directly in its dedicated unit test suite.
- **Prevention**: Always distinguish physical hardware/subprocess execution from mocked Popen test harnesses.

## Known Failure Modes

### QSV Software-to-Hardware Frame Upload
- **What looks correct**: Setting `-pix_fmt yuv420p` in the encoder arguments or letting FFmpeg auto-convert from filtergraph outputs.
- **Why it's wrong**: Intel QuickSync (`h264_qsv`) native driver requires `nv12` pixel format inputs. Auto-selection or incorrect manual format targets lead to encoding crashes (`Invalid FrameType:0`) or bitstream corruption.
- **Correct approach**: Explicitly append the `format=nv12` filter to the end of the video filter complex when encoding with `h264_qsv`, and let the encoder output `-pix_fmt yuv420p` or `yuvj420p` for standard player compatibility.

### Dynamic Ken Burns Duration Scale Assertion Mismatch
- **What looks correct**: Asserting a fixed `min(1.08` zoom constraint in filtergraph tests when `KEN_BURNS_ZOOM_MAX=1.08` is configured.
- **Why it's wrong**: Per Spec Line 85, dynamic duration scaling (`clamp(1.06 + (duration - 2.5)/2 * 0.04, 1.06, 1.10)`) is active by default. For a 3.0s span (90 frames at 30 fps), dynamic scale evaluates to `1.07`. Fixed bounds are only applied if dynamic scaling is explicitly disabled (`KEN_BURNS_DYNAMIC_SCALE=False`).
- **Correct approach**: Test both the dynamic scaling expression under default settings and the fixed bound under `KEN_BURNS_DYNAMIC_SCALE=False`.

### Gemini Thinking Indicator Substring False-Positive
- **Cause**: Using `[aria-label*='Thinking' i]` in `is_gemini_generating` and `wait_for_gemini_idle_native` causes false-positive generation detections. If a user prompt contains the word "thinking" (e.g. `<thinking>...</thinking>`), Gemini's web UI assigns the entire prompt text to the aria-label of the user prompt's "More options" button and sidebar conversation links (`<a>`). Because `*=` matches any substring, `is_gemini_generating` returns `True` indefinitely, causing `wait_for_gemini_response` to time out after 120s despite Gemini having already completed its response.
- **Solution**: Replace substring selector `*=` with exact matches: `[aria-label='Thinking' i]`, `[aria-label='Thinking...' i]`, `[aria-label='يفكر' i]`, and `[aria-label='يفكر...' i]`.
- **Prevention**: Never use broad substring selectors like `*='Thinking'` on generic DOM elements where user prompt text can be reflected into accessibility attributes; use exact attribute matchers or element-specific selectors.

### Run Folder Relative Path Joining Invariant
- **What looks correct**: Blindly calling `os.path.join(latest_run, audio_file)` whenever `not os.path.isabs(audio_file)`.
- **Why it's wrong**: Paths saved to intermediate manifest checkpoints (e.g. `voice_chapters/Chapter_1.wav` or `youtube_runs/<run>/voice_chapters/Chapter_1.wav`) may already be relative to the repository root or current working directory. If `audio_file` already starts with `youtube_runs/...`, `os.path.isabs()` is `False`, but joining `latest_run` duplicates the run folder path (`youtube_runs/<run>/youtube_runs/<run>/...`), causing file probes (`wave.open`) to silently fail and report `0.0s` durations.
- **Correct approach**: First test if the candidate path exists directly (`if os.path.exists(raw_file)`), then test if joining `latest_run` resolves to an existing file (`elif os.path.exists(os.path.join(latest_run, raw_file))`), before constructing relative manifest paths via `os.path.relpath(abs_path, latest_run)`.

### Audacity Named Pipe Leading Newline Protocol Framing Desynchronization
- **Cause**: In Audacity 3.x's `mod-script-pipe` C++ implementation, the command completion string is formatted as `mOutput += wxT("\nBatchCommand finished: ") + status + wxT("\n\n")`. When a command has no intermediate stdout (e.g. `Import2:`, `SelectAll:`, or effect filters), Audacity sends a leading empty newline (`\n`) as the very first line of the response. If the Python consumption loop breaks on `if line.strip() == "": break` without verifying that `BatchCommand finished:` has been read, it terminates prematurely on the leading `\n`, leaving `BatchCommand finished: OK\n\n` unread in the OS named pipe buffer. Subsequent commands read stale leftover lines, desynchronizing the pipe and eventually deadlocking in `read_pipe.readline()` waiting for unbuffered input.
- **Solution**: Consume lines continuously until the explicit status token `BatchCommand finished:` is observed, followed by the trailing terminating empty line. If running against mock pipes in unit tests, verify whether the pipe has pending data before breaking on raw blank lines.
- **Prevention**: Always design IPC parsers around the server's authoritative completion sentinel rather than assuming an arbitrary leading blank line signifies termination.

### Windows CRT Named Pipe File-Lock Deadlock
- **Cause**: Calling `.close()` on a Python file object wrapping a Windows Named Pipe from a control thread while a reader thread is actively blocked inside `readline()` / `ReadFile()` causes a permanent deadlock. The C runtime `_lock_file(f)` mutex is held by `readline()` while waiting for pipe data; calling `fclose()` / `close()` from another thread tries to acquire the same mutex, freezing both threads.
- **Solution**: On Windows named pipes, always terminate or kill the server process (`taskkill /F /IM Audacity.exe`) first. Severing the server pipe handle causes the client's `ReadFile()` to immediately fail with `ERROR_BROKEN_PIPE` (EOF), allowing the reading thread to release `_lock_file(f)` and exit naturally before closing file handles.
- **Prevention**: Never close active blocking pipe streams from a separate thread without first terminating the pipe server or using overlapped non-blocking I/O.

### Audacity GUI Event Loop Initialization Handshake
- **Cause**: When Audacity is launched on Windows, `mod-script-pipe` named pipes become connectable before wxWidgets has finished creating the main project window and pumping the event loop. Sending heavyweight disk commands like `Import2:` immediately can stall waiting for project canvas initialization.
- **Solution**: Execute a fast lightweight handshake (`Help: Command=Help` followed by `SelectAll:`) immediately after connecting named pipes. This forces the message loop to synchronize and guarantees the canvas is ready for audio processing.
### Whisper Spoken Manifest Fallback and Ghost Word Extrapolation Drift
- **Cause**: In `src/youtube_automation/speech/transcriber.py`, `read_initial_prompt()` attempted to deserialize `audio_manifest.json` via `json.load(f)`, but `import json` was omitted from module imports. The resulting `NameError` was caught by a generic `except Exception`, triggering silent fallback to `refined_script.txt` (which contained 3,798 words from an earlier full-length draft instead of the 832 spoken words synthesized into audio). When `align_script_words_with_audio` executed, the 832 spoken words aligned up to 290.14s, but the remaining 2,966 unspoken words were linearly extrapolated into 122 spans out to 455.95s, desynchronizing the downstream timeline by over 165 seconds.
- **Solution**: Explicitly import `json` at the top of `transcriber.py` and ensure `audio_manifest.json` serves as the authoritative single source of truth for spoken text.
### Spelling Corrector Full Script Reference Fallback
- **Cause**: In `src/youtube_automation/speech/spelling_corrector.py`, `correct_transcript()` directly defaulted to `refined_script.txt` as its reference text without checking `audio_manifest.json`. When a run synthesizes a chapter slice (e.g. 15 chapters, 832 words) from a full draft script (110 paragraphs, 3,798 words), `difflib.SequenceMatcher` treats the 2,966 unspoken words as an `insert` opcode, dumping the entire remaining draft into the final subtitle card and timeline text files.
- **Solution**: Check `audio_manifest.json` first as the authoritative spoken text source, extracting only the words actually voiced in the master audio, falling back to `refined_script.txt` only when no audio manifest exists.
- **Prevention**: In multi-stage generative pipelines, never assume an upstream draft script matches downstream synthesized audio; always derive lexical reference text from the authoritative audio manifest.

### PipelineManifest Missing set_planning_status Invalidation Trap
- **Cause**: In `src/youtube_automation/visuals/flow_generator.py`, the prompt reuse optimization checked whether all prompts were complete on disk and attempted to call `manifest.set_planning_status(PhaseStatus.COMPLETED)`. However, `PipelineManifest` only implemented `set_roadmap_status()`, lacking `set_planning_status()`. The resulting `AttributeError` was swallowed by a bare `except Exception: prompts_complete = False` block, causing the generator to silently treat 100% complete storyboards as incomplete and unnecessarily re-trigger Gemini chat planning from chunk 1.
- **Solution**: (1) Add `set_planning_status()` to `PipelineManifest` and update `all_chunks_done()` to return `True` when `planning_phase.status == "COMPLETED"`. (2) In `flow_generator.py`, use `hasattr(manifest, "set_planning_status")` with a direct dictionary fallback and log specific exception details rather than silently resetting state.
- **Prevention**: Never write a bare `except Exception:` that sets a failure flag without logging the actual exception message, and verify dataclass/manifest method signatures before invoking phase setters.

### OCR Text Gate MSER Fallback False-Positive on 2D Vector Art
- **Cause**: When local pytesseract / tesseract-ocr binaries are absent from the host machine, `check_text_collision()` falls back to OpenCV MSER (`_detect_via_mser_fallback`). In stylized 2D vector illustrations (such as Al-Daheeh cartoon explainers), high-contrast outlines and character features are mistakenly categorized as `[MSER_CANDIDATE]`. Because any detected box is treated as a hard text collision, valid generated frames are repeatedly deleted on disk, triggering unnecessary retries and catastrophic browser failovers/process termination.
- **Solution**: Decouple the MSER heuristic from the mandatory pipeline gate with `FLOW_ENABLE_MSER_FALLBACK=false`, and allow `flow_generator.py` to pass an explicit configuration guard so MSER false-positives never delete rendered images when tesseract is unavailable.
- **Prevention**: Never use unvalidated edge/blob heuristics as a destructive gate that deletes generated assets unless actual alphanumeric text has been verified.

### Pipeline Integrity Negative Prompt Forbidden Terms False Positive
- **Cause**: In `src/youtube_automation/prompts/validator.py`, `_collect_schema_and_content_violations` dumped the entire prompt item to a string (`json.dumps(item).lower()`) to check for forbidden positive terms (`\bsubtitles?\b` and `\bmargin\b`). When a structured 8-part visual diffusion schema includes a `negative_prompt` field banning subtitles and margins (e.g. `"negative_prompt": "subtitles, margin, watermark..."`), the whole-item string scan flagged the negative prompt itself as a violation, causing valid 100% complete storyboards to fail pipeline integrity checks.
- **Solution**: Exclude `negative_prompt` from the dictionary copy before running positive prompt forbidden term regular expressions.
- **Prevention**: Distinguish positive prompt content from negative exclusion prompts; never scan negative prompt bans against forbidden positive prompt token lists.

### Google Flow Backend Prompt Safety Rejections & Second-Pass Sweep
- **Cause**: Google Flow's generative diffusion backend can trigger automated safety rejections (`Sorry, this image failed to generate`) on otherwise benign conceptual phrases containing sensitive triggers (e.g. "locked padlock", "dark red tea" misconstrued as bio-fluids, or "infinite vortex").
- **Solution**: (1) Allow the generator to gracefully skip failed frames during Pass 1 so the broad batch is not blocked. (2) Apply lexical softening to ambiguous trigger words (e.g., "closed vault lock symbol", "amber hot tea", "clean geometric pathways"). (3) Execute an automated second sweep with disk-existence skipping (`if os.path.exists(save_path): continue`), targeting only the missing frames.
- **Prevention**: In prompt engineering for automated diffusion APIs, favor neutral descriptive synonyms over high-intensity figurative or physical confinement verbs.

### Compiler Main Argument Unwrapping TypeError
- **Cause**: In `compile_video.py`, the facade wrapper invoked `compiler_mod.main(sys.argv[1:])`. When CLI arguments were supplied (e.g. `python compile_video.py "youtube_runs/..."`), `run_folder` was received as a `list` (`['youtube_runs/...']`) instead of a `str`. In `src/youtube_automation/video/compiler.py`, calling `os.path.join(run_folder, ...)` immediately raised `TypeError: expected str, bytes or os.PathLike object, not list`.
- **Solution**: Normalize `run_folder` at entry in `compiler.main(run_folder)`: `if isinstance(run_folder, (list, tuple)): run_folder = run_folder[0] if run_folder else None`.
- **Prevention**: CLI entrypoint wrappers must sanitize polymorphic arguments (`list` vs `str`) or unpack `sys.argv[1:]` before passing downstream to domain libraries.

### TTS Harvest Truncation and Blind N-of-M Header Trust
- **Cause**: In `src/youtube_automation/audio/tts_generator.py`, the entire multi-thousand-word script was dumped into Gemini Web Chat in a single prompt for breakdown planning. Faced with long context, Gemini planned only 15 blocks covering ~21% of the script and marked Block 15 with an arbitrary "Existential Outro" (`TTS BLOCK [15] of [15]`). Because character/word coverage ratio checks were removed in favor of purely matching `N >= M` in `extract_total_blocks_count`, `tts_generator.py` blindly trusted Gemini's `15 of 15`, set `gemini_completed = True`, and permanently abandoned the remaining ~79% of the script (paragraphs 25–110).
- **Solution**: (1) Enforce a strict minimum script coverage gate (`total_harvested_words >= 0.90 * script_words`) before allowing `check_is_gemini_complete` to return True. (2) Replace unbounded monolithic prompt dumping with deterministic chunk ingestion from `tts_payload.json` (windowed slices by paragraph index). (3) Add an automated pre-flight coverage audit in the agency runner before advancing from Phase 3 to Phase 4.
- **Prevention**: Never let an LLM's self-reported progress header (`[N] of [Total]`) serve as the sole termination criteria for multi-step content harvesting without asserting physical coverage against the input payload.

### Google AI Studio Speech Playground Free Tier Quota Saturation (HTTP 403)
- **Cause**: Google AI Studio Speech Playground (`/generate-speech?model=gemini-2.5-pro-preview-tts`) enforces a daily burst and token budget on free tier Google accounts via `alkalimakersuite-pa.clients6.google.com`. After generating ~30 audio chapters in rapid succession, the backend rejects subsequent requests with HTTP 403 ("Link a paid API key"). If the runner exhausts fast retries (e.g. 3 retries in <30 seconds), it halts.
- **Solution**: (1) Checkpoint all synthesized chapters atomically to disk so completed audio is never lost. (2) Provide seamless resumption: running `generate_voice.py` skips all completed WAV files and resumes directly from the first un-synthesized chapter. (3) Allow quota replenishment via rolling time window, account rotation, or paid Google Cloud API key linkage.
- **Prevention**: Recognize HTTP 403 from `alkalimakersuite-pa` as an upstream quota saturation rather than a code defect; persist all intermediate progress and provide clear resume pathways.

### Google Flow Post-Reload SPA Hydration Race Condition & Native Window Occlusion Throttling
- **Cause**: After `page.goto(url, wait_until='domcontentloaded')`, Google Flow's React SPA requires 5–10s to hydrate `div[contenteditable='true']`. Testing `loc.is_visible()` with zero timeout immediately after navigation fails instantly, triggering false account failovers. Compounded by Windows DWM calculating native occlusion (`CalculateNativeWinOcclusion`) which throttles background timers/rAF to 1Hz when the browser window is occluded or minimized, causing `time.sleep()` to freeze the Playwright CDP WebSocket transport.
- **Solution**: (1) Poll with `wait_for_flow_input_box(page, timeout_seconds=15.0)` using `page.wait_for_timeout(300)` between retries. (2) Add `--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling` and `--disable-background-timer-throttling` to Chrome launch flags in `utils.py`. (3) Replace all `time.sleep()` in Playwright polling loops with `page.wait_for_timeout(ms)`. (4) Scope generation watchdog to `active_card` (last child container) to avoid false-positive loading detection from historical cards.
- **Prevention**: Never check SPA-mounted DOM elements immediately after navigation; always poll with a deadline. Never use `time.sleep()` in Playwright greenlet event loops. Scope DOM queries to the newest container to avoid cross-card interference.

### Google Flow Cross-Origin Canvas Tainting & Blank Image Extraction
- **What looks correct**: Falling back to `ctx.drawImage(img, 0, 0)` and `canvas.toDataURL('image/png')` when in-page `fetch()` fails due to CORS or CDN credentials restrictions.
- **Why it's wrong**: In Google Flow's React SPA, generated images are served from `flow-content.google/image/...` or GPU-backed WebGL contexts. Drawing cross-origin hardware-accelerated images onto an untainted canvas produces an entirely transparent/black image. When serialized as PNG, this empty buffer generates a 23,581-byte file that passes standard `min_size_kb=20` validation despite containing zero visible pixels (`extrema = ((0, 0), (0, 0), (0, 0), (0, 0))`).
- **Correct approach**: (1) Prioritize Playwright's `page.request.get(absolute_src)` network stream before any in-page fetch or canvas fallback, as Playwright's APIRequestContext runs outside the browser's CORS sandbox and inherits full session authentication to stream raw high-resolution binaries directly. (2) In `validate_image_file()`, inspect Pillow's `img.getextrema()` to reject files where all channels are `(0, 0)`. (3) Rely on atomic de-hovered Playwright element screenshots (`locator.screenshot()`) as the ultimate fallback.

### Subprocess Pipe Stdout Block Buffering on Windows
- **Cause**: On Windows, when standard output (`sys.stdout`) is redirected to a subprocess pipe or log file (`sys.stdout.isatty() == False`), the Python C runtime defaults to 4KB/8KB block buffering instead of line buffering. Status logs and print statements appear completely empty in real-time until buffer flush or process exit.
- **Solution**: Explicitly configure `sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)` and `sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)` at module entry, and invoke python runners with `-u` and `-X utf8`.
- **Prevention**: Never rely on default stdout buffering when streaming long-running task progress to file descriptors; always enforce line-buffering.

### Google Flow Angular Material Component Hierarchy & Context Menu Matching
- **Cause**: Google Flow uses custom Angular Material tags (`flow-grid-tile-container`, `flow-image-tile`, `flow-ingredient-chip`). Generic CSS selectors (`div[data-card-index]`, `.generation-card`) evaluate to 0 elements, causing card spawn handshakes to fail. Furthermore, right-click context menus are portaled to `div.cdk-overlay-container`, and the Arabic label for "Add to Favorites" (`إضافة إلى "المفضّلة"`) shares a common substring with "Add to Prompt" (`الإضافة إلى الطلب`). Using loose substring matching triggers the wrong menu action.
- **Solution**: (1) Target `flow-grid-tile-container` (with fallback to `flow-image-tile` and `div[data-card-index]`). (2) Query `div.cdk-overlay-container` directly and use exact regex `(add to prompt|الإضافة إلى الطلب|إضافة إلى الطلب)` to click the prompt ingredient option. (3) Attach the newest previous primary card (`primary_cards[-count_to_attach:]`) instead of the oldest.
- **Prevention**: Inspect live SPA DOM component hierarchies and exact localization strings rather than assuming legacy or translated generic names.

### Benchmark Progress False PASS on Missing Render Artifacts
- **Cause**: In benchmark progress loops, checking `not has_collision and upper_clear` when `save_image_path` does not exist on disk evaluates to `True` if collision defaults are false and clear defaults are true, falsely logging 0-byte non-existent images as `status: PASS`.
- **Solution**: Strictly assert `os.path.exists(save_image_path) and os.path.getsize(save_image_path) > 0` before allowing a `status: PASS` and counting completed frames.
- **Prevention**: Physical disk artifact existence must always be a precondition for pass status in file processing pipelines.

### Google Flow Global Quota Regex False Positive from Historical Tile Glitches
- **Cause**: In Google Flow, when an individual tile fails to render or load an image, it renders transient failure text (`تعذَّر إكمال المعالجة` / `تعذَّر تحميل الصورة`). If `check_flow_quota_or_errors()` scans the whole page DOM without scoping to the active card, this historical failed tile remains in the DOM forever, causing all subsequent frames to immediately fail during `card_spawn_handshake` with a false-positive `RuntimeError`.
- **Solution**: (1) Scope card-level generation failure patterns (`couldn't generate`, `failed to generate`, `تعذَّر إكمال المعالجة`) strictly to `target_locator` (the active card container). (2) In global unscoped checks (`target_locator=None`), match only true fatal account-level quota exhaustion or policy locks (`الحدّ الأقصى للاستخدام`, `reached your usage limit`, `policy violation`).
- **Prevention**: Never query transient card-level error text across the whole document root; separate global account quota checks from scoped card rendering checks.

### Google Flow Grid Prepending & Reverse Candidate Scraper Order
- **Cause**: Google Flow's project workspace prepends newly generated cards/tiles to the top of the feed (lowest `y` coordinate). When sorting candidate images by bounding box `y` and picking `candidates[-1]`, the scraper mistakenly selects the bottom-most, oldest historical images on the page rather than the newly generated asset. This triggers stale scrape collisions in the SHA-256 ledger.
- **Solution**: Sort candidate images ascending by `y` and pick `candidates[0]` (the top-most, newest prepended tile), verifying that its hash is not in the recent rolling ledger.
- **Prevention**: In web scrapers targeting reverse-chronological feeds, verify whether new items are prepended or appended before selecting candidates by coordinate sorting.

### Google Flow Cookie Consent Banner Pointer Event Interception
- **Cause**: Google's cookie notification bar (`#glue-cookie-notification-bar-1`) floats at the bottom of the viewport directly over the prompt input textarea and submit button. Any attempt to click the generate button or focus the input box fails or triggers pointer interception exceptions.
- **Solution**: Add an automated dismissal routine in `dismiss_blocking_flow_modals()` targeting `.glue-cookie-notification-bar__accept` to click and accept cookies before input interaction.
- **Prevention**: Always intercept and dismiss sticky bottom cookie/consent banners during browser setup.

### Google Flow Angular CDK Character Drawer Virtualization & Auto-Dismiss Attachment Handshake
- **Cause**: In Google Flow's ingredient drawer (`div.cdk-overlay-container`), the Character preset list under `الشخصيات` (`Characters`) uses a virtualized list where assets outside the initial view (such as `CHARACTER_HOST_MAIN`) remain unmounted until scroll triggers occur. Furthermore, clicking a character button (`button.asset-item`) can immediately attach the character chip directly into the prompt box and dismiss the overlay. If the summoning automation strictly waits for a secondary detail confirmation button (`الإضافة إلى الطلب` / `Add to prompt`) that was already closed upon direct attach, it times out or issues an `Escape` keypress that cancels or deselects the attached chip, falsely reporting `FAILED/SKIPPED`.
- **Solution**: (1) Add two-way mouse wheel scroll pumping (`overlay_pane.hover()`, `page.mouse.wheel(0, -600)`, `page.mouse.wheel(0, 600)`) to force Angular CDK to mount all project characters. (2) Assert prompt bar chip count before and after clicking `char_btn` to detect single-click auto-attach. (3) If the detail panel is opened, click `Add to prompt`, and finally verify that the chip count increased before returning `True`.
- **Prevention**: Always account for virtualized DOM rendering in dropdowns/drawers and verify the true destination state (prompt bar chips) rather than assuming a mandatory multi-step modal interaction.

### Over-Neutralization Aesthetic Degradation & Sequential Frame Character Discontinuity
- **Cause**: Blanket surface noun stripping and aggressive prompt neutralization (e.g., converting scientific diagrams, chalkboard equations, and brass instruments into generic phrases like "blank unmarked wooden board with zero writing" or "clean unwritten white paper sheet") drained visual storytelling interest and stripped characters out of sequential explanation scenes (e.g. Frame 14 had the host, but Frame 15 jumped to a sterile wooden board, breaking visual continuity).
- **Solution**: (1) Enforce sequential character continuity across adjacent thematic beats (e.g., Frames 14 & 15 both feature Al-Daheeh host with consistent `centered medium close-up shot, clean centered 16:9 widescreen framing` and summoned `CHARACTER_HOST_MAIN` preset chips). (2) Respect human visual review by restoring baseline explainer prompts for technical analogies (Frames 3, 12, 29, 33, 34, 44, 49) where baseline compositional density was superior.
- **Prevention**: In prompt transformation pipelines, never neutralize surface nouns so aggressively that semantic context and sequential character anchors are destroyed.

### Google Flow Account Quota Wall & Runner Failover Defect
- **Cause**: Google Flow free accounts enforce a daily/burst generation limit (~20–25 renders per session). When saturated, Flow displays `لقد بلغت الحدّ الأقصى للاستخدام. يُرجى إعادة المحاولة لاحقًا.` across all subsequent prompts. In earlier canary runner code, fatal quota errors caught in the per-frame retry loop logged the error, marked the frame as FAIL, and blindly iterated through all remaining frames, burning 3 futile reload attempts per frame and marking the entire batch as failed.
- **Solution**: (1) Implement `is_fatal_flow_quota_error()` matching fatal quota exhaustion strings (`الحدّ الأقصى للاستخدام`, `reached your usage limit`, `quota exceeded`). (2) Break immediately from the batch execution loop on fatal quota rather than iterating over remaining frames, preserving all existing completed frames on disk. (3) Support multi-account failover via Chrome profile rotation (`rotate_profile_index()` cycling Profile 1 -> Profile 2 -> Profile 3 -> Profile 4) on port 9222.
- **Prevention**: Fatal resource saturation must immediately halt batch iteration or trigger authenticated account rotation; never allow quota locks to cascade into failure cascades across remaining jobs.

### Google Flow Conversational Agent Interception & UI Mode Desynchronization
- **Cause**: In Google Flow, an "Agent" toggle mode (`button:has-text('Agent')`) can be enabled on the prompt bar or a side chat panel can be open. In Agent mode, submitting text prompts triggers a conversational video generation confirmation modal ("Would you like me to kick off this 1 video generation, costing 15 credits? Approve / Reject") instead of directly generating images.
- **Solution**: Implement `dismiss_blocking_agent_and_modals()` to: (1) click "Reject" on any conversational confirmation prompt, (2) close the agent side panel via `close_btn`, and (3) detect if the "Agent" pill button is active (`backgroundColor` is white or `aria-pressed='true'`) and click it to toggle Agent mode OFF, restoring pure Nano Banana 2 image generation.
- **Prevention**: In multi-modal browser web automation, always assert and enforce the target operational mode before injecting generation prompts.

### Chrome CDP Tab Selection Broad Substring Misrouting
- **Cause**: In `run_canary_benchmark.py`, the CDP tab discovery logic used `if "flow" in page.url or "google.com" in page.url:` to locate the active Google Flow page. Because Google accounts frequently have `gemini.google.com` or `aistudio.google.com` open in the same Chrome debug profile, matching `"google.com"` inadvertently bound `flow_page` to Gemini, causing the generator to attempt Flow DOM interactions inside Gemini's web interface.
- **Solution**: Strictly prioritize exact domain matches (`"flow.google"` or `"/flow"`) in tab resolution, and assert `if "flow" not in flow_page.url: flow_page.goto("https://flow.google.com/")`.
- **Prevention**: Never use generic root domains (e.g. `google.com`, `microsoft.com`) for sub-service tab matching in browser automation when multiple sibling tools share the same top-level domain.
### Google Flow Multi-Account Rotation Character Preset Library Scope & Graceful Mode A Fallback
- **Cause**: Google Flow maintains custom character presets (`CHARACTER_HOST_MAIN`, `CHARACTER_CLERK_BUREAUCRAT`, etc.) strictly scoped to individual Google accounts and specific workspace projects. When multi-account rotation occurs (e.g. rotating from Profile 2/3 to a fresh Profile 4 account due to quota saturation), the new account library does not inherit previously created character presets; the Characters tab in the asset drawer (`div.cdk-overlay-container`) reports `No assets found.`. If an automation runner attempts `summon_character_chip()`, it fails to find the character card and logs `FAILED/SKIPPED`. Furthermore, the asset drawer button in Flow's English UI uses `aria-label="Add ingredients to the prompt box"`, while Arabic uses `aria-label="إضافة المكوّنات"`.
- **Solution**: (1) Harden the asset drawer locator in `flow_generator.py` to match both English and Arabic labels: `button[aria-label*='Add ingredient' i], button[aria-label*='إضافة المكوّنات' i], button[aria-label*='Add asset' i], button[aria-label*='إضافة مورد' i], button:has-text('add')`. (2) Design an automated fallback in `build_dual_mode_prompt`: whenever `summon_character_chip` returns `False`, automatically fall back to **Mode A (Master Setup)** where `expand_asset_tokens()` injects the complete 2D cartoon visual DNA description (e.g., *Al-Daheeh Egyptian cartoon educational host, dark curly hair, black round glasses, animated expressive comedic facial expression, 2D graphic vector animation style, clean white background #FFFFFF*). (3) For cross-account consistency, run the pre-flight routine `setup_flow_characters_and_scenes` when bootstrapping a newly rotated profile so character presets are created in the target account's `/characters` library.
- **Prevention**: In multi-account rotating architectures, never assume that account-scoped cloud entities (presets, saved assets, templates) exist in freshly rotated profiles; always implement graceful text-based fallback and automated pre-flight asset initialization.

### Comparison Studio Viewer Baseline Path Collision after Socratic Consolidation
- **Cause**: Prior to video compilation (`compile_video.py`), newly generated Socratic frames were consolidated into `generated_images/` while original baseline frames were safely backed up to `generated_images_baseline/`. However, `viewer_generator.py` hardcoded the baseline image relative URL to `../generated_images/{fname}`. When opening `studio_viewer.html` in `generated_images/` or any chunk subfolder (`chunk_1_images/` through `chunk_6_images/`), both the left panel (Baseline) and right panel (Socratic Canary) loaded the exact same Socratic frame from `generated_images/`, causing all viewers to preview identical duplicate images.
- **Solution**: (1) In `build_frame_records()`, inspect whether `generated_images_baseline/` exists in `run_dir` and prioritize it as the authoritative baseline directory, falling back to `generated_images/` only when no backup directory exists. (2) Compute all baseline and canary image links dynamically using `os.path.relpath(target_path, html_dir)` so relative paths are always mathematically valid regardless of viewer location. (3) Support seamless fallback to `socratic_master_frames/` for frames outside a local chunk folder. (4) Add interactive dropdown filters for chunks (`Chunk 1: Frames 1–50`, etc.), enhanced frames, and restored frames, automatically initializing the viewer at the first local chunk frame (`initIdx = frames.findIndex(f => f.in_local_dir && f.canary_exists)`).
### Linear Push Pushpop & Division-by-Zero in Procedural Kinematics
- **Cause**: Standard linear interpolation formulas like `((on-1)/(d-1))` evaluate to negative values at frame `on=0` (triggering an instantaneous -1 pop in libavfilter) and crash with zero division when a clip duration is 1 frame (`d=1`).
- **Solution**: Enforce zero-safe clamped evaluation `min(1.03, 1.0 + 0.03 * (clip(on, 0, N) / max(1, N)))` for all holds >= 3.5s.
- **Prevention**: In video filtergraph mathematical expressions, always clamp frame indices with `clip(on, 0, N)` and guard denominators with `max(1, N)`.

### Hardware Video Encoder Stepped Scale Punch Macroblocking
- **Cause**: On hardware video encoders (such as Intel QSV `h264_qsv` with `lookahead=0` and `format=nv12`), attempting to execute instantaneous scale jumps within a single continuous clip causes severe P-frame macroblocking and PTS timeline desync.
- **Solution**: Subdivide long holds (>= 4.0s) at the detected audio transient into two discrete clips (`static_hold` setup + `scale_punch` close-up) in `prepare_synchronized_timeline`, preserving identical asset occurrence integers and anchoring vertical elevation to upper-third eye-line ($Y=360\text{px}$).
- **Prevention**: Never perform stepped filter transitions inside a single hardware-encoded stream; always subdivide into discrete clips across clean keyframe boundaries.

### In-Place `timeline.json` Modification Sidecar Desynchronization
- **Cause**: Updating `timeline.json` without updating the `.sha256` sidecars causes `verify_shim()` to fail with `ValueError: Stale timeline shim detected`.
- **Solution**: Always invoke `save_timeline_and_shims()` or atomically re-calculate `timeline_sha` and rewrite all 4 sidecar files (`image_timestamps.txt.sha256`, `timestamped_transcript.txt.sha256`, etc.).
- **Prevention**: Never edit canonical timeline JSON without synchronously regenerating and validating its cryptographic sidecars.

### Runtime State Profile Index String vs Integer Mismatch
- **Cause**: `runtime_state.json` stores `ACTIVE_PROFILE_INDEX` as the full string `"Profile 4"` (written by `rotate_profile_index()` during multi-account failover). Scripts that read via `get_runtime_state()` and pass directly to `int()` crash with `ValueError: invalid literal for int() with base 10: 'Profile 4'`. Scripts using `get_config_value()` (reads `.env`, always `"2"`) are unaffected.
- **Solution**: Extract digit via `re.search(r"\d+", str(raw))` with fallback default — matching the canonical pattern in `utils.py:rotate_profile_index()`.
- **Prevention**: Never call `int()` directly on `get_runtime_state("ACTIVE_PROFILE_INDEX", ...)`. Always use `re.search(r"\d+", str(raw))` to handle both `"2"` and `"Profile 2"` forms.

### Audacity Named Pipe Cold-Boot Timeout (Zero-Touch Pipeline Failure)
- **Cause**: `launch_audacity_session()` waited only 3s grace + 30×0.5s = 15s retry before raising `ConnectionError`. On a cold-boot where `mod-script-pipe` loads from scratch, the pipe takes 10–20s to appear — beyond the 15s budget. Users were required to pre-open Audacity manually, breaking zero-touch automation.
- **Solution**: Increase grace period to 6s and retry to 80×1.0s (80s total). `ensure_audacity_script_pipe_enabled()` already writes `mod-script-pipe=1` to `audacity.cfg` before launch. Only the polling window was too short.
- **Prevention**: For daemon processes loading plugins at startup, always allow 60–80s for IPC endpoints to become available. Log wait progress every N attempts so the pipeline log remains informative and the user can distinguish a slow-boot from a true failure.

### Google AI Studio QUIC Protocol & Dead Edge IP Navigation Timeouts
- **Cause**: Browser navigations to `https://aistudio.google.com/generate-speech` failed with `ERR_QUIC_PROTOCOL_ERROR` (ISP drops UDP port 443 packets) and `ERR_CONNECTION_TIMED_OUT` (local DNS resolved `aistudio.google.com` to `142.250.181.206`, an unroutable Google IP on local networks, while Google frontends like `142.251.154.2` respond in 50ms).
- **Solution**: Add Chrome launch flags `--disable-quic` and `--host-resolver-rules="MAP aistudio.google.com 142.251.154.2"` into `launch_browser_with_profile()` in `utils.py`.
- **Prevention**: In automation targeting third-party web apps over CDP, never rely on default OS DNS or opportunistic QUIC. Pin domain host mappings to verified healthy frontends and disable UDP HTTP/3 when running in restricted ISP networks.

### LLM Script Truncation and Conversational Meta-Banter Contamination in TTS
- **Cause**: Dumping an entire multi-thousand-word transcript into an LLM chat prompt causes the model to hallucinate arbitrary chapter partitions (e.g. planning only 7 blocks and jumping from Paragraph 12 to Paragraph 40, losing 66% of the script). Additionally, conversational prompts like "how would you like to proceed?" can be refined into spoken dialogue.
- **Solution**: (1) Partition chapters deterministically from `tts_payload.json` into ~180-220 word chunks (100% coverage guaranteed). (2) Enforce an automated script coverage gate ($\ge 85\%$) in `calculate_script_coverage()`. (3) Add regex metadata stripping in `sanitize_script_text()` to purge markdown headers, casting reports, and conversational chatter before text enters the TTS prompt box.
- **Prevention**: Never trust an LLM chat agent to reliably chunk large text corpora without physical word coverage assertion. Prefer deterministic chunking using structured pre-tokenized payloads (`tts_payload.json`).

### Phase 1 Script Transcreation English Chatter Contamination & Dropped Hook
- **Cause**: In `automate_all.py`, the transcreation loop injected each paragraph as `f"paragraph {i} outof {total_paragraphs} paragraphs of the script:\n\n{paragraph}"`. On Paragraph 1, Gemini interpreted the prompt as an editorial critique request and responded with English chat review ("That is a fantastic hook... Since this is just the first of 19 paragraphs, how would you like to proceed?"). On Paragraph 19, Gemini included an English preamble and outro question ("Do you want to add a classic sign-off..."). Because `automate_all.py` lacked an Arabic language ratio check and chatter sanitizer, it appended the English text directly to `final_output.txt`, causing Paragraph 1 to be completely lost and contaminating the script.
- **Solution**: (1) Enforce strict imperative command armor: `DIRECTIVE: Transcreate Paragraph {i}... Output ONLY the Arabic transcreated text. Do NOT include any English preamble, commentary, review feedback, or questions.`. (2) Implement `is_valid_arabic_transcreation()` requiring $\ge 35\%$ Arabic characters (`[\u0600-\u06FF]`), triggering an immediate clean reset fallback if non-Arabic chatter is returned. (3) Implement `sanitize_gemini_chatter()` to strip preambles, sign-off questions, and markdown quotes.
- **Prevention**: In LLM text transformation pipelines, never ingest turn responses without validating positive target-script language density ($\ge 35\%$ Arabic) and purging conversational meta-text.

### Google Flow Active Card Selection Order (.first vs .last)
- **Cause**: In `flow_generator.py`, selecting the active generation tile via `.locator(...).last` selects the card at the bottom of the feed. In Google Flow, newly submitted generation tiles are **prepended to the TOP** of the feed (lowest $y$-coordinate). Consequently, `.last` locked onto historical cards whose image `src` attributes were already in `pre_image_srcs`, causing the script to miss the newly rendered top cards and falsely assume rendering had stalled for 120s.
- **Solution**: Change `active_card` selection to `.first`, query candidate images across `flow-image-tile img, flow-grid-tile-container img, img`, filter `src not in pre_image_srcs`, sort ascending by `(y, x)`, and select `candidates[0]`.
- **Prevention**: In web application feeds that prepend new cards at the top, never select the active item using `.last`; always assert top-of-feed sorting (`.first` or sort by `(y, x)` ascending).

### Google Flow Stale Workspace URL Checkpoint 404 Cascading Failover
- **Cause**: When switching accounts or after project deletion, `flow_workspace_url_profile_X.txt` retains the old project UUID. Navigating to a project from a different profile lands on `https://flow.google.com/404?reason=project`. On retry attempts, navigating back to `active_project_url` without checking for `"404"` re-navigates to the 404 page where the prompt input box does not exist, triggering cascading attempt failures.
- **Solution**: (1) In `setup_flow_ui`, if the saved project URL fails health checks, delete the stale checkpoint immediately and create a fresh project from the homepage. (2) When clicking "New project", wait explicitly for `"project"` in `page.url` before returning. (3) During retry loops, if `active_project_url` is invalid or 404, fall back to `flow_page.reload()`.
- **Prevention**: Always validate that restored workspace URLs resolve to active, healthy projects; clean up stale serialized pointers immediately upon navigation failure.

### Mode B Empty Surgical Delta Attention Vacuum
- **Cause**: In `build_dual_mode_prompt`, when `visual_delta` was resolved only from top-level `raw_dict["action"]` (while the actual delta was nested inside `raw_dict["visual_prompt"]["action"]`), `delta_target` evaluated to an empty string. This produced a malformed Mode B prompt: `"In the attached reference image, maintain identical subject, background, and lighting. Add  centered."`, causing Google Flow to reject or fail image generation.
- **Solution**: Check nested `raw_dict.get("visual_prompt", {}).get("action")` and `subject_action_increment`. If `delta_target` is empty, immediately fallback to Mode A (Master Setup) with full visual DNA instead of submitting a hollow Mode B delta.
- **Prevention**: Never emit relative differential instructions without validating that a positive, non-empty delta target exists.

### False Account Rotation on Transient Non-Quota Errors
- **Cause**: Treating any 3-attempt failure as a fatal error triggering account failover (`rotate_profile_index()`). When a UI selector misses or a transient network glitch occurs, rotating accounts burns healthy profiles while inheriting the exact same UI issue on the next profile.
- **Solution**: Strictly isolate fatal quota strings (`الحدّ الأقصى للاستخدام` / `reached your usage limit`) via `classify_flow_error()`. For transient errors (`TRANSIENT_ERROR`), preserve the active profile, reset the workspace checkpoint, re-initialize from the homepage, and continue.
- **Prevention**: Account rotation mechanisms must require cryptographic or exact string proof of quota exhaustion before triggering irreversible profile switching.

## Known Failure Modes
### Blind Ingestion of Conversational LLM Responses in Code Generation/Translation
- **What looks correct**: Checking `if response and not is_safety_blocked(response): output.append(response)`.
- **Why it's wrong**: Chat models frequently return polite commentary, review praise, or clarification questions ("How would you like to proceed?") when prompts lack negative prohibition armor, poisoning downstream stages or dropping source content.
- **Correct approach**: Validate linguistic/schema density, apply regex conversational sanitizers, and re-prompt with strict imperatives if the model outputs conversational meta-text.

### Scoping Progress / Loading Checks Globally Across Google Flow Page
- **What looks correct**: Checking `flow_page.locator("[role='progressbar']").is_visible()` to determine if generation is still in progress.
- **Why it's wrong**: Modern complex SPAs like Google Flow often have global status spinners, header sync indicators, or sidebar elements with `role="progressbar"`. Global checks cause `is_loading` to evaluate to `True` forever, preventing the script from recognizing that candidate images have completed rendering.
### Hardcoded Persona & Substrate Entanglement in Diffusion Pipelines
- **Cause**: Embedding character names, cultural dialect relics, or specific studio fixtures (`Al-Daheeh`, `Ahwa cafe`, `tea cup`, `Abo Hmeed`) directly into root-level prompt builder utilities and fallback branches. When producing videos for new topics or other channels (science, finance, history), the prompt builder continues injecting these hardcoded persona tokens, contaminating the generated visuals.
- **Solution**: (1) Decouple persona, substrate, and chromatic palette into a dynamic `ChannelProfile` and `NICHE_PRESETS` registry (`science_tech`, `finance_economics`, `history_geopolitics`, `philosophy_essay`, `general_explainer`). (2) Support `host_mode: "NONE"` for pure conceptual graphics without human figures. (3) Remove all hardcoded persona fallback strings from `flow_generator.py` and `prompt_enhancer.py`.
- **Prevention**: Never hardcode character or cultural environment constants into general diffusion compiler utilities; pass them dynamically from channel profiles or storyboard roadmap definitions.

### Contradictory Typography Instructions in Diffusion Prompt Planning Preambles
- **What looks correct**: Instructing the LLM to output quoted text examples (e.g., "STAGE 1", "CLASSIFIED", "OPTION A vs OPTION B") to provide clean typographic labeling in educational diagrams.
- **Why it's wrong**: Diffusion models (such as Imagen 3/Nano Banana) struggle with multi-character text rendering, frequently outputting warped, garbled, or pseudo-Latin letterforms. These illegible glyphs degrade production quality and trigger OCR text collision gates.
- **Correct approach**: Enforce a `STRICT ZERO-TEXT INVARIANT` in prompt planner preambles. Instruct the LLM to convey technical processes purely through non-linguistic data telemetry: abstract proportion bars, percentage glyphs (e.g. 75%), node linkages, directional trajectory arrows, and comparative split quadrants.

### Gemini Web HTML Rendered Table Tab-Delimitation vs Pipe Assumptions
- **Cause**: In `roadmap_orchestrator.py:parse_markdown_table_line`, the parser asserted `if not stripped.startswith("|"): return []`. When Gemini web generates a markdown table, the Angular SPA UI automatically renders it into a native HTML `<table>` element. Playwright's `el.innerText` standard converts table cells inside `<tr>` into horizontal tab-delimited (`\t`) text rather than retaining markdown pipes (`|`). Consequently, `parse_markdown_table_line` discarded all 25 rows, logging 0 rows parsed and falsely triggering empty turn failures and retry loops.
- **Solution**: Update `parse_markdown_table_line` to detect and split by `\t` if present, while retaining pipe-delimited (`|`) support for unrendered or code-fenced markdown.
- **Prevention**: Never assume browser `innerText` contains source markdown syntax when an SPA automatically formats markdown into rich HTML elements; support both raw markdown tokens and rendered whitespace/tab conventions.

### Over-Specified Diffusion Specs in Text Planning Prompts Triggering Multi-Modal Refusal
- **Cause**: In `roadmap_orchestrator.py`, dumping low-level diffusion model coordinates (`X: 180 to 1740, Y: 90 to 980`), hex codes (`#2D3444`, `#F8F8FA`), and pixel specs into the table generation prompt caused Gemini Flash's guardrail classifiers to misinterpret the request as a multi-modal image rendering task rather than a text table planning task. Gemini responded with refusal cards: `"أنا مجرد ذكاء اصطناعي مستند إلى النصوص ولا أستطيع المساعدة في ذلك."` ("I am just a text-based AI and cannot help with that.") or `"I seem to be encountering an error. Can I try something else for you?"`.
- **Solution**: Keep roadmap prompt directives concise, high-level, and focused on narrative/staging concepts (e.g. shot scale, continuous animation arcs, subject focus). Reserve exact pixel coordinates, hex palettes, and diffusion negative tokens for downstream diffusion compilers (`prompt_enhancer.py`, `flow_generator.py`).
- **Prevention**: In multi-stage agentic pipelines, isolate diffusion-specific syntax to diffusion stages; never pollute upstream text planning LLMs with rendering engine parameters.

### Google Flow Initial Queue Stall Bypass & Single-Pass Gap Backfill
- **Cause**: In Google Flow web automation, cold-starting fresh projects or submitting prompt cards during backend queue congestion occasionally exceeds the 45s card-spawn deadline (`Card spawn timed out after 45s. Forcing reload...`). If a runner treats transient queue stalls as fatal crashes or gets stuck in infinite retry loops on a single frame, the entire multi-hour batch halts.
- **Solution**: (1) Allow transient 3-attempt queue timeouts to log as `TRANSIENT_ERROR`, preserve active account profiles (quota not exhausted), recycle the workspace into a fresh healthy project, and safely bypass the blocked frame. (2) Track completed frames in `pipeline_manifest.json` and persist valid PNGs on disk. (3) After completing the main sequential pass, launch a dedicated single-pass backfill that uses disk-existence skipping (`if os.path.exists(save_path) and os.path.getsize(save_path) > 100: continue`) to render only the missing frames.
- **Prevention**: In long-running batch diffusion generation, decouple frame progression from transient API latency by adopting resilient gap-skipping with deterministic post-batch backfill sweeps.

### Thumbnail Text Collision Self-Healing & Strengthened Negative Prompt Retry
- **Cause**: In generative thumbnail workflows, asking Gemini Imagen for high-contrast webcomic or visual assets frequently results in subtle text artifacts embedded into scene props, backgrounds, or character attire (e.g. garbled Latin signage or MSER edge candidate clusters). If ingested uncritically, these contaminated plates degrade click-through rates and violate channel zero-text typography standards.
- **Solution**: (1) Immediately scan newly downloaded thumbnail bitmaps with `check_text_collision(filepath)`. (2) If text or MSER contours are detected on Attempt 1, purge the contaminated file from disk, log the detection coordinates, and automatically retry on Attempt 2 appending `STRENGTHENED_NEGATIVE_PROMPT`. (3) If Attempt 2 also fails, dump debug telemetry (`dump_text_collision_debug`) and purge the corrupt image.
- **Prevention**: Always enforce an automated post-generation OCR text collision gate on candidate thumbnails with deterministic negative prompt retry armor.

### Deterministic Target Folder Resolution in CLI Automation Entrypoints
- **Cause**: Helper scripts like `generate_thumbnail.py` previously relied exclusively on `get_latest_run_folder(runs_path)`. When running automated batch scripts or processing specific historical runs, any background file access or file modification in an unrelated run folder causes `os.path.getmtime` to misidentify the target directory, processing the wrong video project.
- **Solution**: Check `if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]): folder = os.path.abspath(sys.argv[1])` before falling back to `get_latest_run_folder()`.
- **Prevention**: CLI scripts in multi-project pipelines must always accept explicit directory paths via `sys.argv[1]` and prioritize them over directory timestamp sorting.

## Known Failure Modes
### Monolithic All-or-Nothing Batch Halts on Transient Web Queue Delays
- **What looks correct**: Halting the entire generation process or switching Google accounts whenever a single frame fails after 3 attempts.
- **Why it's wrong**: Transient network hiccups or backend diffusion queue spikes on Google Flow do not indicate account quota exhaustion. Aborting the entire batch stops progress on dozens of pending frames, while rotating accounts burns fresh profiles unnecessarily.
- **Correct approach**: Distinguish transient queue delays from fatal quota exhaustion (`الحدّ الأقصى للاستخدام` / `reached your usage limit`). Skip transiently stalled frames to let the remaining 95%+ of the batch complete smoothly, then backfill the small handful of missing frames in a fast 2-minute targeted sweep.

### Silent Text Artifact Bleed in AI Thumbnail Generation
- **What looks correct**: Trusting negative prompt strings in image generation queries without physical verification of downloaded images.
- **Why it's wrong**: Modern diffusion models frequently disregard negative tokens when composing complex narrative scenes with objects (books, boxes, signs, monitors). Latin pseudo-words or blurred typography leak into the output unnoticed, ruining professional YouTube packaging.
- **Correct approach**: Treat prompt negative tokens as advisory and post-generation OCR verification as mandatory. Gate all thumbnail outputs through a hard zero-text inspection pass.



