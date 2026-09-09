# Drill 01.01: AI Studio TTS Paragraph Parsing & Filename Sequencing

## Objectives
- Master script sanitization for generative neural text-to-speech models (AI Studio and Gemini Web UI).
- Implement **Speech Tag Armor**: lowercasing all audio control directives (`[tone:...]`, `[pace:...]`, `[pause:...]`) so generative models treat them as prosody directives rather than spelling out individual English characters phonetically.
- Enforce 1-based sequential chapter indexing, structured manifest generation, and filename alignment (`Chapter_1.wav`, `Chapter_2.wav`, ...).
- Implement sequence validation and gap detection algorithms to catch missing chunks before lossless WAV stitching.

## Architectural Context
In the YouTube automation pipeline ([`tts_generator.py`](file:///C:/Users/Snoozer/Downloads/Antigravity/Youtube%20Automation%202/buckup/Version%204%20before%20deepseek%20implementation%20plan/image_generation/src/youtube_automation/audio/tts_generator.py) and [`chapter_stitcher.py`](file:///C:/Users/Snoozer/Downloads/Antigravity/Youtube%20Automation%202/buckup/Version%204%20before%20deepseek%20implementation%20plan/image_generation/src/youtube_automation/audio/chapter_stitcher.py)), lengthy multi-scene Arabic narration cannot be synthesized in a single monolithic API call due to token limitations and model drift. The script is partitioned into narrative chapters.
Each chapter is verified, saved to `voice_chapters/Chapter_{N}.wav`, and tracked in `voice_generation_manifest.json`.

```
[Raw Gemini Response]
         │
         ▼
[Script Sanitizer & Tag Armoring]
         │
         ▼
[Chapter Extraction & Sequencing] ──► { "chapter_num": 1, "audio_file": "Chapter_1.wav" }
         │
         ▼
[Sequence Validation & Gap Detection] ──► Detect missing or orphan WAV chapters
```

## Input/Output Contracts
- `sanitize_tts_script(raw_text: str) -> str`:
  - Input: Raw text possibly containing markdown code blocks, uppercase tags (`[TONE: Calming]`), and terminal words (`PROCEED`, `COMPLETE`).
  - Output: Cleaned string with all markdown fences stripped, control keywords filtered, and tags normalized to lowercase (`[tone: calming]`).
- `extract_tts_blocks(script_text: str) -> list[dict[str, Any]]`:
  - Input: Cleaned multi-block script text.
  - Output: List of dictionaries matching schema:
    ```python
    {
        "chapter_num": int,        # 1-based sequential integer
        "text": str,               # Chapter narration text
        "audio_file": str,         # "Chapter_{N}.wav"
        "status": str              # "PENDING"
    }
    ```
- `verify_chapter_sequence(chapter_files: list[str]) -> tuple[list[str], list[str], list[str]]`:
  - Input: List of filenames or paths (e.g. `["Chapter_1.wav", "Chapter_2.wav", "Chapter_4.wav"]`).
  - Output: `(contiguous_prefix, missing_chapters, orphan_chapters)`:
    - `contiguous_prefix`: Valid contiguous sequence starting from index 1.
    - `missing_chapters`: Expected missing chapter filenames before max index.
    - `orphan_chapters`: Present files located beyond the first gap.

## Drill Variants
- [Detailed Architectural Explainer](explainer/readme.md)
- [Problem Workspace (Student)](problem/exercise.py)
- [Solution Reference](solution/exercise.py)
- [Solution Verification Tests](solution/test_exercise.py)
