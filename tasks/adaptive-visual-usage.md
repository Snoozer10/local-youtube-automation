# Adaptive production: staged pilot workflow

This feature is opt-in and is not yet approved for unattended full episodes. The production package has offline regression coverage; real Gemini/Flow behavior, reference restoration, Arabic readability and artistic quality still require the three reviewed pilots in [the checklist](adaptive-visual-tasks.md).

## Select identity before analysis

Save one JSON profile per channel outside generated run folders. Select it explicitly; script analysis cannot infer the destination channel or change browser selectors. Example only (replace the voice with an available saved voice):

```json
{
  "version": 1,
  "channel_id": "science-example",
  "name": "Science example",
  "audience": "Curious Arabic-speaking adults",
  "language": "Arabic",
  "dialect": "Modern Standard Arabic",
  "asr_language": "ar",
  "voice": "REPLACE_WITH_SAVED_VOICE",
  "tone": "Clear, curious and measured",
  "style": "Naturalistic editorial illustration; consistent soft lighting and restrained colors",
  "host_mode": "NONE",
  "host_description": "",
  "allowed_treatments": ["subject_scene", "detail", "mechanism", "comparison"],
  "humor": "light",
  "max_zoom": 1.06
}
```

`asr_language` is an optional Whisper language code; null lets the transcriber detect the spoken language. `CUSTOM_AVATAR` requires a stable host description. Omit the `host` treatment for a channel without a host. Profiles separate channel identity from episode topics, narrative form, evidence needs and figurative language. This is policy validation, not a factual or aesthetic guarantee.

## New raw-script run

Run commands from the repository root with the project virtual environment. Create a new run directory and place the original source in `raw_transcript.txt`. Do not retrofit a brief onto old translated output.

```powershell
venv/Scripts/python.exe adaptive_production.py analyze --run-dir "youtube_runs/pilot-science" --channel-profile "channels/science.json"
venv/Scripts/python.exe adaptive_production.py write --run-dir "youtube_runs/pilot-science"
```

For existing URL extraction, `automate_all.py --channel-profile "channels/science.json"` applies one explicitly selected channel to that invocation's URL list. It writes channel/video/profile-specific directories and runs analysis before restructuring, translation and refinement. Other channels require separate invocations. Changed raw input with existing downstream artifacts requires a fresh run, preserving previous output.

## Narration and canonical timing

The existing audio tools accept an explicit run directory: `generate_voice.py`, `automate_audacity.py`, `stitch_chapters.py`, and `faster_whisper_transcribe_audio.py`. Keep the selected run identical across stages. Voice and transcription consume the saved channel; transcription records the actual audio path relative to that run, including the polished audio subfolder. Adaptive voice generation partitions the validated `refined_script.txt` directly into chapters and uses the selected channel voice. It does not run the legacy Egyptian comedy TTS rewrite. A resume blocks if the script/channel recipe or a completed WAV digest differs from its checkpoint.

For adaptive audio, run voice generation, Audacity polishing, then stitching, each with the explicit run directory. Voice generation blocks once any polished chapter or stitched master exists, protecting physical offsets; use a fresh run for a revised voice source. Close any manually opened Audacity first; the adaptive stage refuses to attach to it and terminates only the process it started. Audacity requires the checked-in optimizer preset and an explicit success response for every DSP command. It reprocesses chapters on a resume because older names-only checkpoints cannot prove source identity. It preserves previously valid polished files until replacements verify, retains the checkpoint if any chapter or manifest sync fails, and rejects an incomplete polished set. Stitching never falls back to raw chapters in an adaptive run; it rejects chapters changed since manifest sync, writes a temporary master, and replaces the previous one only after validating the full frame count. `audio_manifest.json` records exact gapless offsets from the polished WAV frames. `voice_generation_manifest.json` remains the raw TTS checkpoint.

Adaptive TTS now shares the browser lease with the other adaptive stages. It opens and closes its own AI Studio tab in an existing CDP session and does not use the legacy Gemini clipboard-paste phase. Start the CDP browser before adaptive TTS; the stage stops if CDP is unavailable. Adaptive TTS also stops on account quota/failover rather than replacing an unowned browser or changing the global profile. The generic browser launcher no longer pins AI Studio to a hard-coded IP address. Browser process ownership for automatic profile rotation and coordination with legacy tools are still tracked work. Do not run the legacy batch supervisor over adaptive runs: it excludes them, and direct `process_folder` calls reject them before changing state. Use a 60–90 second pilot script and validate its narration/timeline before generating visual assets.

## Plan, generate and inspect

```powershell
venv/Scripts/python.exe adaptive_production.py plan --run-dir "youtube_runs/pilot-science"
venv/Scripts/python.exe adaptive_production.py generate --run-dir "youtube_runs/pilot-science"
venv/Scripts/python.exe adaptive_production.py report --run-dir "youtube_runs/pilot-science"
venv/Scripts/python.exe adaptive_production.py preview --run-dir "youtube_runs/pilot-science"
```

Gemini and Flow use the existing authenticated browser/CDP setup. No new cloud SDK or API key is introduced; the browser services still need network access. Background OCR requires working Tesseract. Missing OCR, assets, references or frame coverage block the stage.

Review `adaptive_review/index.html` and the video path inside `adaptive_preview.json`. Confirm subject relevance, factual meaning, consistent identities, meaningful cuts, crops, local Arabic labels and restrained motion. Contact sheets contain original assets; the rendered preview is necessary to review crops and overlays. Shape/font availability and mobile readability require visual inspection.
The review table shows each shot's focal point and zoom. The renderer uses that point for the initial aspect crop and confines pans to travel that keeps it visible. Push/pull/pan with zoom 1 and pans without safe travel now fail planning/render validation; choose a hold or revise the composition. Re-preview and approve after a camera recipe change because cached clips and approval lineage are invalidated.

An edit attaches only the receipt's exact source URL in the same Flow project, verifies its decoded pixel hash, and checks the attachment chip. Missing references block generation. Automatic restoration into a new project/account is not implemented. Provider UI changes and live attachment behavior remain unverified.

## Thumbnail packaging

For an adaptive run with validated writing, `venv/Scripts/python.exe generate_thumbnail.py "youtube_runs/pilot-science"` uses the channel brief for title concepts and image prompts. It uses the shared browser lease, saves accepted landscape images under `thumbnails/accepted/`, and records their paths, hashes and passed OCR gate in `adaptive_thumbnail_receipt.json`. Missing OCR or detected bitmap text blocks acceptance. A repeat verifies the receipt and skips browser work. Changed script, brief, titles or model requires a fresh run. The old webcomic thumbnail path remains for legacy runs. Text is reserved as negative space in the generated bitmap; optional local typography and visual quality still need pilot review.

## Explicit approval and master activation

After an actual human review, record the reviewer's name:

```powershell
venv/Scripts/python.exe adaptive_production.py approve --run-dir "youtube_runs/pilot-science" --reviewer "Reviewer name"
venv/Scripts/python.exe adaptive_production.py render --run-dir "youtube_runs/pilot-science"
venv/Scripts/python.exe adaptive_production.py status --run-dir "youtube_runs/pilot-science"
```

Approval requires a current rendered preview. Changes to the plan, assets, audio or render settings require a new preview and approval. Technical checks never approve editorial quality. `active_master.json` is the activation pointer; read its path and hash rather than assuming `youtube_ready_video.mp4` exists. This command renders a local file, not a YouTube upload.

## Resume, lineage and rollback

- Repeating a stage reuses validated writing, plans and assets. Invalid or stale inputs fail visibly; there is no automatic legacy fallback.
- `accepted_assets/` preserves image bytes by SHA-256 independently of provider scratch files. Receipts record prompt, model recipe, dimensions, reference hash and technical status.
- `adaptive_renders/<generation>/` separates render recipes. Clip receipts validate bytes as well as frame count. Final filenames include content hashes, so interruption before pointer activation leaves the previous master intact.
- `.runtime/adaptive.sqlite3` records resource claims, attempts, lease heartbeats and terminal events. Current locking covers adaptive writing/generation and rendering in this installation. It is not a complete durable per-stage scheduler or a lock for legacy tools.
- Stop the active process before maintenance. Preserve the run, receipts and prior `active_master.json` to restore an earlier accepted generation; never rename unrelated assets to satisfy a receipt.
- Returning to the legacy workflow means using a separate legacy run without `episode_brief.json`. Do not remove the brief to force adaptive artifacts through legacy stages.

## Remaining rollout gates

Automatic reference restoration, semantic subject crop checks, complete audio/clipboard ownership, durable stage scheduling and the prior reliability backlog remain in the checklist. Three contrasting channel pilots and user acceptance precede full-episode production. No historical production runs have been regenerated as part of these implementation checks.
