# Adaptive production: staged pilot workflow

This feature is opt-in and is not yet approved for unattended full episodes. The production package has offline regression coverage, and the approved Snoozer pilot has exercised live Flow generation, exact reference restoration, Arabic rendering, local preview composition and immutable master activation. Three reviewed pilots are still required in [the checklist](adaptive-visual-tasks.md).

The three selected profiles are in `channels/`. The prepared pilot runs under `youtube_runs/adaptive-pilot-*` contain caption-derived `raw_transcript.txt`, `pilot_source.json` provenance and validated `episode_brief.json`. Snoozer has a hash-bound source narration excerpt, canonical timeline, accepted visuals and an approved master. A separate ignored `adaptive-pilot-professor-yashrah-local-narration` run now has a matched owner-archived voice track and canonical timeline. The archived voice track has not been proven identical to the published upload because the owner edited many final videos in CapCut. The originally selected 0–69.08-second caption pilot remains untouched; the local voice-track cut is 0–76.55 seconds to include its last spoken word. Soldier's selected Ardennes media remains unmatched in the supplied archive. Keep source video/audio files read-only.

| Channel | Existing upload used for pilot | Caption/audio window | Narration policy |
|---|---|---:|---|
| [Professor Yashrah](https://www.youtube.com/watch?v=AvTeNM10wZQ) | Six attention exercises, opening Schulte-grid challenge | Published-caption pilot: 0–69.08 s; separate local voice-track pilot: 0–76.55 s | Use the owner-archived pipeline voice track for the separate pilot; do not label it the published audio. Achird remains the saved synthesis voice. |
| [Soldier's Sledger](https://www.youtube.com/watch?v=IyrbpV8-AQ4) | English Ardennes command-room opening | 0–69.4 s | Preserve published audio; profile is English for this episode. Arabic uploads need an explicitly selected language/voice variant later. |
| [Snoozer Anime](https://www.youtube.com/watch?v=sViXav5CHlM) | Egyptian Arabic romance-comedy recap scene | 19.9–89.72 s | Preserve published audio; use original character continuity rather than screenshot imitation. |

These excerpts are source material, not verified facts. Professor's claimed benefits of the Schulte grid and the Soldier's Sledger's historical reconstruction need human editorial checks. The anime recap is classified as fictional: its source-stated names, relationships and setting are continuity anchors rather than external evidence needs. Do not draw quantitative claims, historical specifics or character details that the brief cannot substantiate, and do not turn figurative phrases into literal visuals by default.

## Select identity before analysis

Save one JSON profile per channel outside generated run folders. Select it explicitly; script analysis cannot infer the destination channel or change browser selectors. Example only (replace the voice with an available saved voice):

```json
{
  "version": 2,
  "channel_id": "science-example",
  "name": "Science example",
  "audience": "Curious Arabic-speaking adults",
  "language": "Arabic",
  "dialect": "Modern Standard Arabic",
  "asr_language": "ar",
  "voice": "REPLACE_WITH_SAVED_VOICE",
  "tone": "Clear, curious and measured",
  "style": "Naturalistic editorial illustration; consistent soft lighting and restrained colors",
  "visual_directives": [
    "Ground every scene in a specific observable situation",
    "Use clean local diagrams only when they clarify the narration"
  ],
  "forbidden_motifs": [
    "glowing brain",
    "floating icon collage"
  ],
  "host_mode": "NONE",
  "host_description": "",
  "allowed_treatments": ["subject_scene", "detail", "mechanism", "comparison"],
  "humor": "light",
  "max_zoom": 1.06
}
```

`asr_language` is an optional Whisper language code; null lets the transcriber detect the spoken language. `CUSTOM_AVATAR` requires a stable host description. Omit the `host` treatment for a channel without a host. Version 2 profiles require positive `visual_directives` and exact `forbidden_motifs`; name concrete visual phrases rather than vague quality words. New shots also declare `narrative_role`, and a host-free channel rejects the `presenter` role. Profiles separate channel identity from episode topics, narrative form, claim basis, fact-check questions, continuity anchors and figurative language. A fictional analysis must have no external evidence needs. These deterministic gates do not prove factual or aesthetic quality.

## New raw-script run

Run commands from the repository root with the project virtual environment. Create a new run directory and place the original source in `raw_transcript.txt`. Do not retrofit a brief onto old translated output.

Each adaptive CLI stage is a durable content-bound job. A successful stage with unchanged source files, selected profile/model and effective render settings skips only after its output revalidates. Missing or corrupt output reruns automatically. Existing output is registered without repeating work only when its own receipts/pointers prove the current input lineage; the unbound HTML report reruns after a recipe change. Changed inputs create a fresh attempt lineage. An expired worker is reclaimed with a higher fence, and a stale worker cannot publish. Three consecutive failures for one unchanged recipe open its circuit; correct the cause, then repeat that command with `--force-retry`. Do not use force retry to bypass validation or editorial approval.

```powershell
venv/Scripts/python.exe adaptive_production.py analyze --run-dir "youtube_runs/pilot-science" --channel-profile "channels/science.json"
venv/Scripts/python.exe adaptive_production.py write --run-dir "youtube_runs/pilot-science"
```

For an existing-narration pilot, **skip `write` and TTS**. After `analyze`, import the matching original local media with the caption window above:

```powershell
venv/Scripts/python.exe adaptive_production.py source-audio --run-dir "youtube_runs/adaptive-pilot-professor-yashrah" --media-file "D:/owner-media/professor-video.mp4" --start-seconds 0 --end-seconds 69.08
venv/Scripts/python.exe adaptive_production.py source-audio --run-dir "youtube_runs/adaptive-pilot-soldiers-ledger" --media-file "D:/owner-media/soldiers-video.mp4" --start-seconds 0 --end-seconds 69.4
venv/Scripts/python.exe adaptive_production.py source-audio --run-dir "youtube_runs/adaptive-pilot-snoozer-anime" --media-file "D:/owner-media/anime-video.mp4" --start-seconds 19.9 --end-seconds 89.72
venv/Scripts/python.exe faster_whisper_transcribe_audio.py "youtube_runs/adaptive-pilot-professor-yashrah"
```

Replace the example media paths with the owner's actual full uploads or matching narration tracks. Each import probes the source duration, verifies the exact local file hash, extracts mono 48 kHz PCM, checks the excerpt length, and publishes source/audio/writing receipts. A repeat reuses identical bytes; changed media or boundaries require a fresh run. `verify_written_episode` rejects a missing/tampered WAV or any changed source-preserved text. Run transcription separately for all three directories before planning shots. The source-audio receipt marks the narration mode; a null profile voice blocks synthesis until a real AI Studio voice is selected.

For existing URL extraction, `automate_all.py --channel-profile "channels/science.json"` applies one explicitly selected channel to that invocation's URL list. It writes channel/video/profile-specific directories and runs analysis before restructuring, translation and refinement. Other channels require separate invocations. Changed raw input with existing downstream artifacts requires a fresh run, preserving previous output.

## Narration and canonical timing

The existing audio tools accept an explicit run directory: `generate_voice.py`, `automate_audacity.py`, `stitch_chapters.py`, and `faster_whisper_transcribe_audio.py`. Keep the selected run identical across stages. Voice and transcription consume the saved channel; transcription records the actual audio path relative to that run, including the polished audio subfolder. Adaptive voice generation partitions the validated `refined_script.txt` directly into chapters and uses the selected channel voice. It does not run the legacy Egyptian comedy TTS rewrite. A resume blocks if the script/channel recipe or a completed WAV digest differs from its checkpoint.

For adaptive audio, run voice generation, Audacity polishing, then stitching, each with the explicit run directory. Voice generation blocks once any polished chapter or stitched master exists, protecting physical offsets; use a fresh run for a revised voice source. Close any manually opened Audacity first; the adaptive stage refuses to attach to it and terminates only the process it started. Audacity requires the checked-in optimizer preset and a bounded, explicitly successful response for every DSP command. It reprocesses chapters on a resume because older names-only checkpoints cannot prove source identity. It preserves previously valid polished files until replacements verify, retains the checkpoint if any chapter or manifest sync fails, and rejects an incomplete polished set. Stitching never falls back to raw chapters in an adaptive run; it rejects chapters changed since manifest sync, writes a temporary master, and replaces the previous one only after validating the full frame count. `audio_manifest.json` records exact gapless offsets from the polished WAV frames. `voice_generation_manifest.json` remains the raw TTS checkpoint.

Adaptive TTS shares the browser lease with every browser entrypoint. It opens and closes its own AI Studio tab in an existing CDP session and does not use the legacy Gemini clipboard-paste phase. Start the CDP browser before adaptive TTS; the stage stops if CDP is unavailable. Adaptive TTS also stops on account quota/failover rather than replacing an unowned browser or changing the global profile. The generic browser launcher records the exact CDP listener PID; rotation refuses an unregistered or replacement listener and never pins AI Studio to a hard-coded IP address. Clipboard writes use a separate short lease. Do not run the legacy batch supervisor over adaptive runs: it excludes them, and direct `process_folder` calls reject them before changing state. Use a 60–90 second pilot script and validate its narration/timeline before generating visual assets.

## Plan, generate and inspect

```powershell
venv/Scripts/python.exe adaptive_production.py plan --run-dir "youtube_runs/pilot-science"
venv/Scripts/python.exe adaptive_production.py generate --run-dir "youtube_runs/pilot-science"
venv/Scripts/python.exe adaptive_production.py report --run-dir "youtube_runs/pilot-science"
venv/Scripts/python.exe adaptive_production.py preview --run-dir "youtube_runs/pilot-science"
```

Gemini and Flow use the existing authenticated browser/CDP setup. No new cloud SDK or API key is introduced; the browser services still need network access. Background and thumbnail OCR require `pytesseract`, a working Tesseract engine and both `eng` and `ara` language data; missing OCR, assets, references or frame coverage block the stage. Use a PATH-installed engine, set `TESSERACT_CMD` to its executable, or place a project-local executable at `.runtime/tesseract/tesseract.exe` with `tessdata/eng.traineddata` and `tessdata/ara.traineddata`. Do not change system DNS or network adapters for this workflow.

The shot planner sends at most about 20 seconds of canonical narration per Gemini request, retaining original span IDs and binding every validated partial batch to the brief, timeline and window boundaries in `shot_plan.partial.json`. Each window keeps one Gemini chat for validation repair. Transport retry sends the exact same prompt, and atomic files under `planner_responses/` bind the prompt hash, model, frame window, stable `/app/<conversation-id>` URL and attempt states. Ctrl+C persists an interrupted attempt before exiting. A restart first reopens submitted, interrupted or timed-out attempts and accepts only a new response that passes the normal Stop-free stability handshake; the transient blank `/app` route is never navigated as a receipt target, and completed responses are reused without submission. The planner wait defaults to 600 seconds and can be changed with `IMAGE_PLANNER_TIMEOUT_SECONDS`. Changed upstream or planner recipes archive the checkpoint with other mutable activations. A technically valid batch still needs editorial review; Professor Yashrah's archived gears/puzzle shorthand is an explicit reject.

The local compositor supports deterministic `data_grid` and `timer` overlays in addition to labels, arrows and highlights. Use `preset: schulte_6x6` for the Professor challenge: it supplies the immutable 1–36 arrangement and renders the grid, focus cells and timer locally. A Schulte shot must use `narrative_role: diagram`, `framing: diagram`, contain no human, and give the grid a near-full-frame region. Do not ask Flow to generate exact numerals or Arabic text or place the exercise on a presenter-held prop.

Review `adaptive_review/index.html` and the video path inside `adaptive_preview.json`. Confirm subject relevance, factual meaning, consistent identities, meaningful cuts, crops, local Arabic labels and restrained motion. Contact sheets contain original assets; the rendered preview is necessary to review crops and overlays. Shape/font availability and mobile readability require visual inspection.
The review table shows each shot's focal point and zoom. The renderer uses that point for the initial aspect crop and confines pans to travel that keeps it visible. Push/pull/pan with zoom 1 and pans without safe travel now fail planning/render validation; choose a hold or revise the composition. Re-preview and approve after a camera recipe change because cached clips and approval lineage are invalidated.

An edit first reopens the receipt's exact Flow project and attaches the matching provider image, tolerating signed-URL refresh only when the stable provider media ID matches. If that project reloads without its provider cards, the engine re-uploads the receipt-bound content-addressed accepted PNG and verifies exactly one prompt ingredient before generation. It never chooses a recent or merely similar card. Missing or mismatched references block generation; restoration into a different account remains unsupported.

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
- `accepted_assets/` preserves image bytes by SHA-256 independently of provider scratch files. Receipts record prompt, model recipe, dimensions, reference hash and technical status. Before accepted bytes are copied, `.publication_journal/assets/` records the intended content-bound receipt. After a crash, a repeat activates that asset only when the complete PNG still matches the current recipe, exact reference, byte hash, pixel hash and geometry; an incomplete or stale journal causes normal regeneration.
- `adaptive_renders/<generation>/` separates render recipes. Clip receipts validate bytes as well as frame count. Final filenames include content hashes, so interruption before pointer activation leaves the previous master intact. `.publication_journal/renders/` records a verified preview/master pointer before activation; a repeat activates the existing encoded file without another encode only when its generation, full inputs, path, hash, frame count, frame rate and audio stream all revalidate.
- `.publication_journal/writing.json` and the source-audio/thumbnail journal directories protect multi-file activation. A retry reconstructs only outputs whose complete input recipe and bytes still match.
- When a stage recipe changes, `.publication_journal/stage-invalidation.json` records every mutable downstream file before it moves into `.adaptive_history/<old>-to-<new>/<stage>/`. A restart finishes that archive before executing work. Content-addressed `accepted_assets/`, immutable `adaptive_renders/` and reusable caches remain in place.
- `.runtime/adaptive.sqlite3` records content-bound adaptive stage jobs plus resource claims, attempts, lease heartbeats, fences and terminal events. Distinct stage/browser/clipboard/Audacity/encoder claims may nest and jointly fence publication. Legacy device entrypoints participate in the same leases.
- Stop the active process before maintenance. Preserve the run, receipts and prior `active_master.json` to restore an earlier accepted generation; never rename unrelated assets to satisfy a receipt.
- Returning to the legacy workflow means using a separate legacy run without `episode_brief.json`. Do not remove the brief to force adaptive artifacts through legacy stages.

## Remaining rollout gates

Cross-account reference restoration and semantic subject crop review remain pilot gates. Three contrasting channel pilots and user acceptance precede full-episode production. The Snoozer pilot is approved through active master; Professor and Soldier remain open. No historical production runs were regenerated.
