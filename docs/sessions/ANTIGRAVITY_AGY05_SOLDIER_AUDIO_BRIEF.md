# AGY05 — Soldier raw-audio validation and timing

**Task ID:** AGY05-SOLDIER-AUDIO-OFFLINE  
**Prepared:** 2026-10-13 · **Target deadline:** 2026-10-14  
**Status:** Delegation brief only. The user starts and stops Antigravity; no delegate run is claimed here.

## Goal and scope

Return bounded, reproducible local evidence for Soldier master tasks B1–B3 using the accepted raw narration. Current scope permits WAV inspection, frame-based calculations, lossless stitching, offline ASR and timing work. It does not authorize DSP, Audacity launch/pipe work, browser activity, provider/model sends, downloads, rendering or publication. B1’s polish requirement may therefore remain **OPEN**; do not claim polish or B1 acceptance without a separately authorized processing recipe and evidence.

## Frozen input

- Repository root: `C:/Users/Snoozer/Downloads/Antigravity/Youtube Automation 2/buckup/Version 4 before deepseek implementation plan/image_generation`
- Raw input: `youtube_runs/adaptive-soldiers-ledger-samar-original-20261009/voice_chapters/Chapter_1.wav`
- Expected SHA-256: `bb9e85b9496b292f30e88c810f40ee6c9e3af16a78f1186c558a68670727c38b`
- Accepted duration: 90.52 seconds; spoken words must remain unchanged and total duration must remain at or below 91 seconds.
- Verify the input bytes and hash before work and again at closeout. A mismatch blocks processing; report actual bytes/hash without replacing the expected identity.

## Ownership and output

Write all delegate-created files only under `.runtime/antigravity_offline_queue_20261013/AGY05_attempt01/`. Root, source, Git state and raw input are read-only. Do not edit the branch master, HANDOFF, task documents or canonical run. Put the complete return record at `.runtime/antigravity_offline_queue_20261013/AGY05_attempt01/RETURN.md`; include an in-scratch fresh-session resume note there.

Before each run, freeze the exact helper/source bytes used into a new exclusive-created scratch archive and record their paths, sizes and SHA-256. Never edit a helper after running it. Capture stdout and stderr into separate scratch files; close them before hashing. After all outputs close, write a payload manifest listing each payload path, size and SHA-256. A companion seal records the manifest hash and return-record hash; omit its own hash to avoid a self-hash cycle. Recheck the raw input and manifest inventory after sealing.

## Verified interfaces and execution boundary

Use the repository’s actual modules after inspecting and freezing their exact source versions; do not invent command-line flags or run entrypoints that write into the canonical run.

- `youtube_automation.audio.wav_validation.parse_wav_file(path)` reports parseability, PCM fields, frame count, byte-rate warnings/errors and frame-to-byte offsets without rewriting the WAV.
- `youtube_automation.audio.chapter_stitcher.stitch_files(file_list, output_path)` concatenates whole frames and checks format homogeneity. Any output must go in the attempt directory. If the publication guard or another dependency would write outside that directory, stop and report the blocker.
- `youtube_automation.speech.transcriber` supplies `load_transcribe_config`, `load_whisper_model`, and `align_script_words_with_audio`; its current flow calls `model.transcribe(..., word_timestamps=True, beam_size=…, vad_filter=…)`. Use a confirmed already-cached local model only; prove its local path before loading. If absent, stop without network access or download.
- `youtube_automation.timeline.engine` supplies `build_words_from_whisper`, `build_timeline`, `get_wav_duration`, and `save_timeline_and_shims`. Keep all generated JSON/timing artifacts in scratch; do not call a writer that targets the canonical run.

First freeze the interfaces/config/model path, then run. Record exact interpreter, cwd, import path, relevant config values, model identity and helper hashes.

## Acceptance and stop rules

Report B1, B2 and B3 separately as **PASS**, **PARTIAL**, **BLOCKED** or **NOT RUN**. Preserve the known raw header inconsistency if confirmed; report declared and computed byte rate without modifying accepted source bytes. Record chapter frame counts, exact frame-derived offsets/duration, stitch input/output hashes, transcript coverage findings, word-level timing checks, monotonicity and end-duration reconciliation. Do not call ASR output a reviewed transcript: lexical/audio review remains explicit, and uncertainty or gaps remain open.

Use no more than two attempts for the same failing command; after the second failure stop. Stop on input drift, missing local model, unexpected filesystem writes, scope drift or first unanticipated dependency. Preserve failure stdout/stderr and a concise diagnosis. Do not update master checkboxes or claim acceptance.

**Return:** exact attempt directory and `RETURN.md` path; task status; artifact inventory/hashes; commands with cwd/exit status; verified results vs claims/unknowns; failures; remaining B1/B2/B3 gates; and fresh-session resume order. Antigravity leads as coordinator, uses only bounded independent implementer/verifier subagents inside this scratch directory, and reports their IDs/roles/owned paths. No tool installation, configuration changes or new worktrees. Codex independently reviews returned evidence.

Strict WAV contract: inspect and record the raw declared-versus-computed byte rate without modifying accepted bytes. A known header-rate diagnostic is not silently a strict PASS. Losslessly stitch whole original frames into scratch;then strict-validate the derived WAV and compare payload frame hashes/counts. Format/extent/alignment errors or unexplained mismatch block the lane. No trim,resample,EQ,compression or DSP is authorized. Force HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1,disable telemetry,and use an explicit already-existing local model snapshot with local_files_only where supported;missing weights block without download.

## Binding execution controls (Codex review)

ROOT = "C:/Users/Snoozer/Downloads/Antigravity/Youtube Automation 2/buckup/Version 4 before deepseek implementation plan/image_generation". Quote every path containing spaces. Read root AGENTS.md, GEMINI.md and owning contracts, but this user-approved scratch-only scope overrides generic project-document closeout writes: propose changes in RETURN.md; do not edit HANDOFF, AGENTS or master. Run helpers with PYTHONDONTWRITEBYTECODE=1 and Python -B;redirect temporary files,logs,caches and every artifact to this lane's scratch. If an API cannot respect that boundary,stop instead of bypassing its resource guard.

Lead Antigravity as coordinator; use bounded native implementer and independent verifier subagents with disjoint scratch ownership. Verify byte/hash identities first; record original and derived data separately. No launch of Audacity or browser,no provider sends/web fetches/model downloads,rendering,source changes,Git mutations,graph updates or installs. Native Antigravity reasoning is authorized; task-initiated external calls are not. Use only existing tools and local assets. Input drift or attempted scope violation stops the lane immediately.

Freeze helper source/version and SHA-256 BEFORE use; verify that hash immediately before each invocation. Capture exact argv,cwd,exit status and unmodified stdout/stderr into raw log files under scratch. Do not treat compressed tool text as executable code,raw file bytes or successful evidence.

Close every output and log before sealing. Hash closed payload files into OUTPUT_MANIFEST.json; then close RETURN.md and the manifest. Finally write SEAL.json containing hashes of those two closed files (exclude SEAL.json itself from its hash domain). Freeze all sealed files; no edits after seal. If a change is necessary,create a new additive correction and new seal retaining originals. Missing evidence is UNVERIFIABLE/PARTIAL,never a pass. Return the complete scratch path,counts,per-task findings,remaining blockers and seal;Codex independently reviews before any promotion or checkbox closure.

Create this lane attempt directory exclusively; if it exists,stop and report rather than overwrite or silently choose another attempt. All task statuses remain staged claims until Codex review.

ASR language: en. Verify reference-script correspondence before lexical alignment. Reference script "C:/Users/Snoozer/Downloads/Antigravity/Youtube Automation 2/buckup/Version 4 before deepseek implementation plan/image_generation/youtube_runs/adaptive-soldiers-ledger-samar-original-20261009/refined_script.txt", SHA-256 4743a3369b7b3c0bf9d2016e0ecf36a350a7f5c011241384f1066d206db4811e. Record raw and aligned words separately;verify monotonic starts/ends,positive durations,in-bounds timestamps and unexplained overlaps against current timeline contract. Label silence;never fabricate spoken coverage to reach the audio endpoint.

Required scratch payloads: INPUTS.json, raw_wav_report.json, chapter_manifest.json, stitched.wav (if safe lossless stitch succeeds), derived_wav_report.json, asr_raw.json, aligned_words.json, timeline.json, timing_validation.json, TASK_STATUS.json and raw invocation logs. Missing-stage outputs are explicitly NOT RUN/BLOCKED,not fake placeholders.
