"""Speech domain automation package.

Provides Faster-Whisper CTranslate2 audio transcription, Silero VAD pause detection,
monotonic script-to-audio anchor alignment, timeline synthesis, and fuzzy
difflib lexical spelling correction.
"""

from .spelling_corrector import (
    align_and_correct_file,
    correct_transcript,
    get_target_directory,
)
from .transcriber import (
    align_script_words_with_audio,
    clean_text_for_transcript_and_srt,
    format_srt_timestamp,
    format_timestamp,
    get_latest_run_folder,
    load_transcribe_config,
    load_whisper_model,
    normalize_arabic_token,
    read_initial_prompt,
    read_whisper_preset_fallback,
    slice_initial_prompt,
    split_into_punctuated_sentences,
)

__all__ = [
    "align_and_correct_file",
    "align_script_words_with_audio",
    "clean_text_for_transcript_and_srt",
    "correct_transcript",
    "format_srt_timestamp",
    "format_timestamp",
    "get_latest_run_folder",
    "get_target_directory",
    "load_transcribe_config",
    "load_whisper_model",
    "normalize_arabic_token",
    "read_initial_prompt",
    "read_whisper_preset_fallback",
    "slice_initial_prompt",
    "split_into_punctuated_sentences",
]
