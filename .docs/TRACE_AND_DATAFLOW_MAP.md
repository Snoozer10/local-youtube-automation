# TRACE_AND_DATAFLOW_MAP — Al-Daheeh Pipeline

**Produced**: Phase 1 (2026-08-26) | **Maintained through**: Phase 5 (finalized at hardening)
**Scope**: executable ground truth. Where docs disagree with code, this map follows code.

---

## 1. End-to-End Dataflow Chain

```
youtube_urls.txt
   │
   ▼ [translate] automate_all.py
      in : youtube_urls.txt; cached raw_transcript.txt / breaked_paragraphs.txt / checkpoint.json
      out: raw_transcript.txt, breaked_paragraphs.txt, final_output.txt,
           <Title> - Broken Paragraphs.docx, <Title> - Translation.docx
      gate: skips video work if final_output.txt non-empty AND translation docx exists
   │
   ▼ [refine]  refine_script.py          ← toggle ENABLE_REFINE_SCRIPT=false removes node
      in : final_output.txt, prompts/refine_prompt.txt, daheeh_config.json (lexicon), docs/audit_rubric.md
      out: refined_script.txt/.docx, tts_payload.json, audit_diff.html, audit_feedback.md
      resume: refine_checkpoint.json → paragraph N+1; complete-but-undelivered ⇒ regenerate artifacts first
   │
   ▼ [voice] generate_voice.py
      in : refined_script.txt → fallbacks (refine_script.txt → final_output.txt),
           prompts/TTS_PROMPT.txt, voice_option_notes.txt  (SHADOWS .env TTS model/temp/voice)
      out: voice_chapters/Chapter_N.wav, voice_generation_manifest.json
      resume: manifest gemini_completed flag + per-chapter status=="COMPLETED" && valid WAV; md5 cross-chapter dedup
   │
   ├─(FLIP_AUDACITY_ORDER=false, default)──────────────────────────┐
   ▼ [audacity] automate_audacity.py                                │
      in : full_episode_voice.wav OR voice_chapters/*.wav;          │
           YouTube_Voice_Optimizer.txt(.txt) preset                 │
      out: audacity_voice/full_episode_voice.wav (+ root sync copy) │
           or polished_chapters/Chapter_N.wav                       │
      resume: audacity_checkpoint.json {polished_files[]}           │
   │                                                                │
   ▼ [stitch] stitch_chapters.py ◄──────────────────────────────────┘ (flip swaps order)
      in : polished_chapters/Chapter_*.wav (fallback voice_chapters/)
      out: full_episode_voice.wav        guards: gap detection + format homogeneity
   │
   ▼ [transcribe] faster_whisper_transcribe_audio.py | tools\transcribe_audio.py  ← WHISPER_ENGINE switch
      in : audacity_voice/full_episode_voice.wav → fallback root WAV;
           initial prompt from refined/final script
      out: image_timestamps.txt, timestamped_transcript.txt, timestamped_transcript.srt, subtitle_chunks.srt
   │
   ▼ [images] flow_image_generator.py | script_image_generator.py  ← IMAGE_GENERATOR_TYPE switch
      in : image_timestamps.txt (fallback timestamped_transcript.txt)
      planning layer: pipeline_manifest.py → json_sanitizer.py → validator.py
                      → gemini_controller.py → roadmap_orchestrator.py → prompt_planner.py
      out: master_roadmap.jsonl, flow_prompts.json (flow engine) / pre_planned_prompts.txt (script engine),
           pipeline_manifest.json, generated_images/<MM_SS>.png (+_N multi-frame)
      resume: script_hash invalidation; roadmap pages per-page; chunks VERIFIED/REPAIRED skip;
              frame-level disk-existence check is primary gate
   │
   ▼ [fixtimes] fix_timestamps.py
      in : timestamped_transcript.txt + flow_prompts.json
      out: rewritten flow_prompts.json (authoritative [MM:SS])
      supervisor-side skip: are_images_timestamped() if generated_images already digit-prefixed
   │
   ▼ [video] compile_video.py <folder>     (outer timeout 3600 s from run_agency)
      in : audio (audacity_voice → root fallback), image_timestamps.txt/timestamped_transcript.txt,
           generated_images/, camera maps (flow_prompts.json → pre_planned_prompts.txt → manual_animations.txt)
      out: temp_clips/chunk_NNNN.mp4 + filter_chunk_NNNN.txt, concat_chunks.txt,
           dynamic_subtitles.ass (opt), youtube_ready_video.mp4, video_config.local.txt
      resume: compile_checkpoint.json chunk ledger; encoder purge-and-retry fallback chain QSV→NVENC→libx264
      verify: verify_master_video() post-check
   │
   ▼ [thumbnail] generate_thumbnail.py
      in : titles.txt (fallback folder name), script excerpt[:6000]
      out: thumbnails/title_N_thumbnail.png ×TOP_N=2, thumbnail_prompts.json, thumbnail_critique.json
      gate: skip if thumbnails/ already ≥2 files

NOT WIRED INTO SUPERVISOR: correct_transcript_spelling.py (manual step; rewrites the four timeline artifacts).
Failure path (any phase): CalledProcessError→Telegram "[PIPELINE CRASH]", TimeoutExpired→"[TIMEOUT EXPIRED]",
Ctrl-C→"[USER INTERRUPTION]"; optional per-step push via TELEGRAM_NOTIFY_PER_STEP; clean_browser_tabs() between steps.
Folder fully skipped when pipeline.json has video==thumbnail==true.
```

## 2. State & Checkpoint Schema Registry

| File | Producer | Consumers | Fields | Resume semantics |
|---|---|---|---|---|
| `pipeline.json` | run_agency.save_pipeline_state:97 (atomic) | get_pipeline_state:73; skips :168/:285 | 10 bools: translate…thumbnail; missing `refine` coerced True | Per-flag skip; folder skip on video∧thumbnail; flags written AFTER child exit |
| `checkpoint.json` (translate) | automate_all.py:863 (**non-atomic**) | :662-681 | `{translated_paragraphs:[str]}` | Skip paragraphs ≤ len(list); deleted on success; final_output count-match recovery :682-700 |
| `refine_checkpoint.json` | refine_script.save_checkpoint:139 (atomic) | load_checkpoint:105 (accepts legacy str-list); delete:174 | `{refined_paragraphs:[{index,original_text,refined_text,word_count,rhythm_variance,is_outro}]}` | Resume at N+1 :862; complete-but-missing-artifacts regenerates BEFORE delete :866-877 |
| `voice_generation_manifest.json` | generate_voice.save_manifest:136 (atomic) | throughout main | `{voice_config{model,temp,voice}, archetype_plan, gemini_completed, chapters[{chapter_num,text,audio_file,status,md5}]}` | Phase-1 skip :1059; per-chapter COMPLETED+valid-WAV skip :1253; md5 dedup w/ disk fallback :1394-1411 |
| `audacity_checkpoint.json` | save_checkpoint:134 (atomic) | load:122; loop skip :301 | `{polished_files:[names]}` | Named files skipped; failure keeps checkpoint & continues :408-413; deleted after all targets |
| `planning_checkpoint.json` | script_image_generator:614 (**non-atomic**) | loaded :432 | `{completed_chunks:int, chunk_responses:[str], all_parsed_prompts:[[idx,prompt]]}` | Chunks ≤ completed skipped; continuity anchor = last 2 prompts |
| `pipeline_manifest.json` | pipeline_manifest.PipelineManifest.save:98 (atomic) | flow main; roadmap_orchestrator; prompt_planner | `{project_id, script_hash, roadmap_phase{status,total_lines,completed_pages,last_processed_index}, planning_phase{status,chunk_size,total_chunks,chunks{chunk_N{indices,status,attempts}}}, rendering_phase{completed_indices}, last_updated}` | script_hash=SHA256(transcript+preamble+presets); mismatch⇒phase reset; FAILED dumps debug/malformed_chunk_N.json then raises ChunkPlanningError; ChunkStatus ∈ PENDING/VERIFIED/REPAIRED/FAILED |
| `master_roadmap.jsonl` (+legacy .txt) | roadmap_orchestrator._atomic_rewrite_files:351 | load_or_migrate_roadmap:196; compile camera readers prefer flow_prompts.json | RoadmapRow.to_dict(): index,timestamp,script_line,sequence_type,layout_classification,camera_specification,visual_concept,color_and_arabic_text | Continuity = indices exactly 1..total; corrupt ⇒ legacy-txt migration else regeneration; fixed-size 25-row pages, never tail-merged |
| `runtime_state.json` | utils.set_runtime_state:286 (atomic) | get_runtime_state:275 (.env fallback) | kv (`ACTIVE_PROFILE_INDEX`) | Rotation persists across restarts without touching .env |
| `flow_assets_profile_<idx>.json` | flow.mark_profile_assets_initialized:692 (atomic) | is_profile_assets_initialized:680 | `{assets_initialized,profile_index,project_url,last_updated}` | Written ONLY on full preset success :1513-1522 |
| `flow_workspace_url_profile_<idx>.txt` | flow:2709 | setup_flow_ui(project_url) :2329 | URL | Unhealthy resume ⇒ fresh workspace creation |

## 3. Normalized Configuration Matrix (key facts)

**Reader**: `utils.get_config_value` via `load_dotenv(.env, override=True)`.
**Parser rule (both txt configs)**: only keys present in in-code `DEFAULTS` survive; all others silently dropped.

### 3.1 Model routing (.env → reader)
`SCRIPT_BREAKER_MODEL=Flash`→automate_all:586 · `SCRIPT_TRANSLATOR_MODEL=Pro`→automate_all:707 · `VOICE_GENERATOR_MODEL=Flash`→generate_voice:977 (code default Flash-Lite) · `IMAGE_PLANNER_MODEL=Flash`→flow:2592 / script:712 (defaults differ: Flash-Lite / Pro) · `REFINE_MODEL=Flash`→utils:54 (default Pro) · `THUMBNAIL_MODEL=Pro`→thumbnail:452 (fallback REFINE_MODEL)

### 3.2 TTS/Flow
`TTS_MODEL/TTS_VOICE_NAME/TTS_TEMPERATURE`→generate_voice:82-84 — **shadowed by voice_option_notes.txt** · `TTS_PROACTIVE_RELOAD_INTERVAL=40`:1267 · `FLOW_IMAGE_MODEL=Nano Banana 2 Lite`:2593 · `FLOW_IMAGE_COUNT=1x`:2594 · `FLOW_ASPECT_RATIO=16:9`:2520 · `FLOW_DISABLE_AGENT=true`:2477 · `FLOW_CHUNK_SIZE=15`:2642 · `ROADMAP_WINDOW_SIZE=25`:2641

### 3.3 video_config.txt → load_video_config dict (consumers)
OUTPUT_*:20-26→encoder cfg/KenBurns/ASS PlayRes/checkpoint signature · CHUNK_SIZE=20:36→run_chunked_compile:1449 · QSV_LOOKAHEAD=0:42→:170-173 (**starvation guard, mandatory**) · NVENC_*:44-49→:180-185 · KEN_BURNS_ZOOM_MIN/MAX:52-53→build_ken_burns_filter:326-327 · KEN_BURNS_UPSCALE_FACTOR=1.12:55→:328 · AUDIO_*:66-68→assembly:1362-1364 · LOUDNORM_I/TP/LRA=-14/-1/11:69-71→measure+apply · VBV 35000k/70000k:82-83→encoder args · FFMPEG_THREADS=4:86→:220 · CLIP/FINAL_TIMEOUT 300/5400:87-88→render/assembly · ENABLE_SFX/SFX_DIR/SFX_DEFAULT_VOLUME:118-120→assemble+SFXEngine
**Dropped by parser**: ENABLE_BGM/BGM_FILE/BGM_DEFAULT_VOLUME (:113-115) → sidechain branch :1294-1304 unreachable from file.
**Parsed-but-dead keys**: OUTPUT_PROFILE, CPU_TUNE, LOUDNORM_LINEAR, LOUDNORM_PRINT_FORMAT, CHECKPOINT_SAVE_INTERVAL, ENABLE_SINGLE_PASS, MIN/DEFAULT/MAX_CLIP_DURATION, KEN_BURNS_EASING/INTERP_ALGO/PAN_SPEED/ZOOM_SPEED, EXPORT_SFX_STEM, BURN_SFX_INTO_VIDEO, DEBUG_DRY_RUN, DEBUG_FILTER_GRAPH_DUMP. Duplicate SUB_FONT_NAME/SIZE/MARGIN_V declared twice in txt (later wins).

### 3.4 transcribe_config.txt reality
Effective cadence = punctuation-forced split (ALL trailing punct :310-311) + silence gap `SILENCE_SPLIT_GAP_SEC=0.45` (code default :36). **Inert in txt**: SUB_MAX_WORDS/SUB_TARGET_WORDS/SUB_MIN_GAP_SPLIT, IMAGE_MIN/TARGET/MAX_DURATION_SEC, IMAGE_MIN/MAX_WORDS, IMAGE_PAUSE_SPLIT_SEC=0.40, EXPORT_TIMELINE_TXT. WHISPER_MODEL_SIZE shadowed by voice_option_notes "Whisper Model:".

### 3.5 daheeh_config.json consumers
Only path consumed: `dialect_profile.tashkeel_lexicon` → DialectTashkeelEngine (refine_script:209-249, longest-token-first regex, prefix-aware و/ف/ب/ك/ل) + automate_all.apply_tashkeel_from_config:228. **Unused sections**: version, target_channel, fusha/amiya ratios (30/70 hardcoded in prompt prose), pacing_metrics, tts_acoustic_tags, visual_diffusion_engine.

## 4. IPC & Browser Touchpoints

### CDP connect sites (port discipline)
| Site | URL form |
|---|---|
| utils.launch_browser_with_profile:259 | `http://127.0.0.1:{CDP_PORT}/json/version` ✅ env-honoring probe |
| refine_script:886,1017 | `127.0.0.1:{cdp_port}` ✅ |
| run_agency.clean_browser_tabs:57 | `localhost:{CDP_PORT}` ⚠ IPv6 risk, env-honoring |
| automate_all:250,463 | `localhost:9222` ❌ hardcoded+localhost |
| generate_voice:1044,1050 | `localhost:9222` ❌ |
| generate_thumbnail:467,474 | `127.0.0.1:9222` ⚠ hardcoded (IPv4-safe) |
| flow_image_generator:2568,2572 | `127.0.0.1:9222` ⚠ hardcoded |
| script_image_generator:667,674 | `localhost:9222` ❌ |

Kill path: utils.kill_cdp_chrome:127 — netstat PID lookup → taskkill /F /T (PID>100) → ≤4 s release poll. Launcher wipes Singleton* before spawn, 15×1 s health poll.

### Injection ladder (modern — gemini_controller.inject_prompt_via_cdp:82)
clear(Ctrl+A/Backspace) → T1 keyboard.insert_text → T2 clipboard grant+writeText+Ctrl+V → T3 execCommand insertText → T4 fill() **only ≤500 chars**; every tier gated by ≥95% inner_text readback (_READBACK_MATCH_PERCENT:48). Completion = Tri-Factor (wait_for_gemini_turn_completion:143): A HARD stop-absent, B HARD 3× stability@500ms non-empty, C SOFT action-bar logged-only; error-card fast-fail; ephemeral chat per page/chunk + jitter 1.5-3.0 s.
Legacy ladder: GeminiSessionClient.dispatch_prompt:289 polled by wait_for_gemini_response:372 (90 s start window, 5 stable reads, placeholder rejection). Clones exist in voice/script/thumbnail/flow generators (drift hazard — see PHASE_1 report §2.8).

### Audacity pipes (automate_audacity)
`\\.\pipe\ToSrvPipe`(w)/`FromSrvPipe`(r) UTF-8, ≤20 open attempts :335-341. Frame = command+`\n`, read until empty line :30-49. `SelectAll:` before every effect :106. Pre-launch: kill Audacity.exe, wipe `%LOCALAPPDATA%\Audacity\SessionData` + `%APPDATA%\audacity\AutoSave` :186-214, force-write mod-script-pipe=1 :161-184. Export bounded 900 s. Export2 NumChannels=1 (forced mono downmix :368).

## 5. Subprocess Inventory (VERIFY baseline — zero shell=True anywhere)

| Site | Binary/purpose |
|---|---|
| run_agency:119,304-308(timeout 3600),310 | python children |
| utils:134 netstat · :147 taskkill /F /T /PID · :155 fuser(posix) · :256 browser Popen | infra |
| automate_all:269-284 chrome Popen (CREATE_NEW_CONSOLE\|DETACHED) | CDP bootstrap |
| automate_audacity:224,317,425 taskkill · :332 Audacity Popen | DSP host |
| compile_video:154 encoder probe(t=5) · :391 ffprobe duration · :920 loudnorm measure(t=120) · :1030 chunk render Popen(cwd=run_folder) · :1375 assembly Popen · :1526 master verify(t=60) | ffmpeg/ffprobe |
| WinGet PATH injection: faster_whisper:12-14, tools/transcribe:12-14, compile_video:18-20 | %LOCALAPPDATA%\Microsoft\WinGet\Links |

## 6. Zero-Drift Math Sites (protected during refactor)

- Budget: `total_audio_frames = max(1,int(round(audio_duration*fps)))` prepare_synchronized_timeline:725
- Clip-0 anchor frame 0 :735; clamp `max(start+1, min(ideal, total−remaining))` :745; surplus-fold when clips>frames :731-733
- CFR: `-fps_mode cfr -video_track_timescale fps*1000 -g fps*2 -keyint_min fps +cgop avoid_negative_ts make_zero +genpts` :211-219
- zoompan exactness: `d=<frame_count> trim=end_frame=<frame_count>,setpts=PTS-STARTPTS` :385-386
- Ken Burns: smoothstep ease :343-345, trunc-centered window :351-352, lanczos rescale :340
- Acoustic snap: AudioSyncAligner 20 ms RMS windows, ±0.20 s dip search :643-667, interior cuts only :689,:698
- Loudnorm: measure JSON→DOTALL regex :884-908 → measured string `linear=true` applied post `aresample=async=1:min_hard_comp=0.100000:first_pts=0` + 0.10 s tail fade :1317-1327

## 7. Drift Register — FINAL STATUS (post Phase 5, 2026-08-26)

| # | Item | Status |
|---|---|---|
| 1 | Hardcoded `9222` ×19 + `localhost` ×4 | ✅ FIXED — all sites `http://127.0.0.1:{cdp_port}` (commit c273e09) |
| 2 | Non-atomic checkpoint writers ×2 | ✅ FIXED — shared `utils.atomic_write_json` (c273e09) |
| 3 | Helper-family duplication ×≥4 | ⏸ OPEN — consolidation needs live selector calibration; modern layer authoritative |
| 4 | Mojibake literals generate_voice:165,186-189 | ⏸ DEFERRED — behavior-load-bearing; needs live calibration run |
| 5 | requirements.txt markdown fence | ✅ FIXED (c273e09); pip dry-run green |
| 6 | Dead config/env surface | ⏸ DOCUMENTED — trace map §3 is ground truth until operator rules wire-vs-prune |
| 7 | Hidden `.tests\` tree uncounted by CI | ✅ RESOLVED — mandated coverage ported to visible `tests\`; dot-tree excluded from tooling scope (53a347b) |
| 8 | Lint/type gates failing vs own pyproject | ✅ ruff+format ZERO (53a347b); mypy 714 documented residual (annotation campaign = future project) |
| 9 | Checkpoint signature gap (audio/encoder) | ✅ FIXED+WIRED with drift logging (c273e09) |
| 10 | Stitch contiguity contract | ✅ FIXED, pinned by tests (c273e09) |

**Zero-drift math sites (§6) and all IPC protocols (§4) verified unchanged through the program — pinned by `tests\unit\test_timeline_sync.py`, `test_checkpoint_resilience.py`, `test_audacity_pipe_protocol.py`.**
Final suite state: **320 passed** (303 unit + 17 integration). Full audit trail: `.docs\PHASE_1…PHASE_5 reports.`
