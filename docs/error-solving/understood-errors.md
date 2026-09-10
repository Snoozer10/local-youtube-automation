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
