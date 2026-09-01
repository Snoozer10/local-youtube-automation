# 0005: Audio DSP locked contract (Audacity macros + Named Pipes + EBU R128)

The audio chain was an implicit, locally-known sequence: `YouTube_Voice_Optimizer.txt` macros, Audacity Named Pipes, lossless Wave stitch, EBU R128 loudness target. Drift was possible if any link loosened (preset drift, pipe name typo, TTS swap, loudness re-target). We lock the entire chain as a hard contract feeding `timeline.json` so sync downstream has a deterministic source.

## Decision

- **DSP preset:** `YouTube_Voice_Optimizer.txt` macros synced to `%APPDATA%\audacity\macros\`; wipe `SessionData`/`AutoSave` before open; always `SelectAll:` before DSP; verify preset exists via file check.
- **Named Pipes:** `\.\pipe\ToSrvPipe` (commands) and `\.\pipe\FromSrvPipe` (responses); every command ends with `\n`; read until empty line is observed.
- **Stitch:** `stitch_chapters.py` lossless Wave frames, zero drop; per-chapter `Chapter_N.wav` MD5 dedup across `N` to avoid duplicate work on resume.
- **Loudness target (EBU R128):** integrated `-14 LUFS`, true-peak `-1 dBTP`, LRA `11`. Verified vs `video_config.txt:58` and compile `320k/48k I-14 TP-1 LRA11`.
- **TTS model fixed:** `gemini-2.5-pro-preview-tts`, voice `Achird`, `TTS_TEMPERATURE=1.1`, `TTS_PROACTIVE_RELOAD_INTERVAL=40`; Bezier mouse drag; no model swap.
- **Timeline feed:** `correct_transcript_spelling.py` + `faster_whisper` pause-aware transcript (VAD `0.40s` → `VAD_SNAP_THRESHOLD=0.35s`) feeds `timeline.json` `words[]`; timestamps are not touched by the spelling corrector (uses `difflib` with `autojunk=False`).
- **Loudness audit:** `EBU R128 -14 LUFS / -1 dBTP / LRA 11` is measured at the stitched output, not at chapter level. Out-of-tolerance re-runs the DSP pass, not the TTS pass.

## Considered Options

- **TTS model swap (e.g., Flash, Pro, third-party)**: Rejected per broad scope lock; audio is fixed input to timeline and a model swap would invalidate the existing `voice_generation_manifest.json` MD5 dedup and the loudness envelope. Any new model becomes a separate, scoped ADR.
- **Per-chapter loudness normalization**: Rejected; chapter-level loudness shifts cause re-entry jumps on chapter boundaries. Single integrated measurement at stitched output is the YouTube standard.
- **Cloud-based DSP (e.g., Adobe Podcast, Auphonic)**: Rejected; violates CDP-only / no-cloud-SDK constraint and introduces a hard external dependency on the audio path.
- **Loose TTS temperature (free per chapter)**: Rejected; variation compounds with `TTS_PROACTIVE_RELOAD_INTERVAL` reload events and produces audible timbre drift across long videos.

## Consequences

- **Hard-to-reverse lock**: changing any link (preset, pipe name, TTS voice, loudness target) requires a new ADR. The current chain is the source of truth; downstream tickets must not relax it.
- **Glossary:** `CONTEXT.md` `audio_chain` term is the consumer-facing handle.
- **Pipeline contracts unchanged:** `pipeline_manifest` resume + `script_hash` continue to operate on the audio path as they do today; no new fields introduced.
- **No new tickets:** this ADR closes the last frontier ticket of map #4. The audio chain is a contract, not a feature; consumers reference it.
- **Verification:** `video_config.txt:58` (`-14 LUFS/-1 dBTP/LRA 11`) and `YouTube_Voice_Optimizer.txt` macro contents are the executable sources; ADR is the prose rationale.

Status: accepted
