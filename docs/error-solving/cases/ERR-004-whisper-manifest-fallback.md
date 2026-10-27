# Case ID: ERR-004-whisper-manifest-fallback

## Overview
- **Title**: Whisper Spoken Manifest Fallback and Ghost Word Extrapolation Drift
- **Responsible Layer**: speech.manifest
- **Status**: resolved
- **Date Recorded**: 2026-10-23
- **Affected Components**: Speech transcriber (`transcriber.py`), spelling corrector (`spelling_corrector.py`), timeline alignment

## 1. Verified Facts
- `read_initial_prompt()` in `src/youtube_automation/speech/transcriber.py` omitted `import json`, triggering a `NameError` caught by a generic `except Exception` block.
- Silent exception handling fell back to `refined_script.txt` (which contained 3,798 words from an earlier full draft instead of the 832 words voiced in synthesized audio).
- Timeline alignment aligned the 832 spoken words up to 290.14s, but linearly extrapolated the 2,966 unspoken ghost words across 122 spans out to 455.95s, desynchronizing the downstream timeline by >165 seconds.

## 2. Hypotheses
- Catch-all `except Exception` swallowed a fatal import bug, replacing authoritative audio manifests with full unvoiced script drafts.
- Confidence: high.

## 3. Attempts and Outcomes
- **Attempt 1**: Explicitly import `json` at module top-level and enforce `audio_manifest.json` as the authoritative source of truth for voiced text.
  - *Outcome*: Succeeded. Extrapolation drift eliminated; timeline perfectly matches audio duration.

## 4. Remaining Gaps & False-Positive Boundaries
- **Boundaries**: Applies when synthesizing partial chapter slices from longer draft scripts. Does not affect runs where draft script and spoken audio are identical 1:1.
- **Gaps**: None.

## 5. Verified Prevention Check
- **Rule / Guard**: Always derive lexical reference text from `audio_manifest.json` before any draft script fallback.
- **Verification**: `tests/unit/test_production_source_narration.py` and `tests/unit/test_speech_transcriber.py`

## 6. Evidence Links
- **Legacy Register**: [`docs/error-solving/understood-errors.md#whisper-spoken-manifest-fallback-and-ghost-word-extrapolation-drift`](../understood-errors.md)
- **Source Code**: [`src/youtube_automation/speech/transcriber.py`](../../../src/youtube_automation/speech/transcriber.py)
