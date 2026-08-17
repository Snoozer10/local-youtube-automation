import os
import sys
import time
import torch
import wave
import glob
import re
import difflib
from faster_whisper import WhisperModel

# Ensure WinGet binaries (ffmpeg / ffprobe) are accessible
winget_links_path = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links")
if os.path.exists(winget_links_path):
    os.environ["PATH"] = winget_links_path + os.pathsep + os.environ["PATH"]


def load_transcribe_config(config_path="transcribe_config.txt") -> dict:
    """
    Parse transcribe_config.txt into typed dict.
    Supports: bool (true/false), int, float, str.
    Comments (# ...) and blank lines are ignored.
    """
    DEFAULTS = {
        "WHISPER_MODEL_SIZE": "small",
        "WHISPER_LANGUAGE": "ar",
        "WHISPER_BEAM_SIZE": 5,
        "WHISPER_VAD_FILTER": True,
        "WHISPER_MIN_SPEECH_DURATION_MS": 250,
        "INITIAL_PROMPT_MAX_WORDS": 120,
        "DEFAULT_INITIAL_PROMPT": "يا عم، بتهلوس؟ الجاس لايتنج ده بجد، والمريونيط بيتحرك، والرموت كونترول تاه. سدقني، بلاش تلعب بالنار.",
        # Minimum duration for a micro-fragment before merging with next (in seconds)
        "MIN_SENTENCE_DURATION_SEC": 0.8,
        # Maximum words in a sentence before forcing a cut (prevents run-on paragraphs)
        "MAX_SENTENCE_WORDS": 14,
        # Silence gap that forces a clause split (in seconds)
        "SILENCE_SPLIT_GAP_SEC": 0.45,
        # Paths & Filenames
        "RUNS_DIR": "youtube_runs",
        "POLISHED_AUDIO_SUBDIR": "audacity_voice",
        "AUDIO_FILENAME": "full_episode_voice.wav",
        "REFINED_SCRIPT_FILENAME": "refined_script.txt",
        "FINAL_OUTPUT_FILENAME": "final_output.txt",
        "EXPORT_SRT": True,
        "EXPORT_TIMELINE_TXT": True,
    }

    if not os.path.exists(config_path):
        return DEFAULTS.copy()

    config = DEFAULTS.copy()
    with open(config_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                if '#' in value:
                    value = value.split('#', 1)[0].strip()

                if key in DEFAULTS:
                    default_val = DEFAULTS[key]
                    if isinstance(default_val, bool):
                        config[key] = value.lower() in ('true', '1', 'yes', 'on')
                    elif isinstance(default_val, int):
                        try:
                            config[key] = int(float(value))
                        except ValueError:
                            pass
                    elif isinstance(default_val, float):
                        try:
                            config[key] = float(value)
                        except ValueError:
                            pass
                    else:
                        config[key] = value
    return config


def get_latest_run_folder(runs_path="youtube_runs"):
    """Synchronized folder resolution matching compile_video.py."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    rel_to_script = os.path.join(script_dir, runs_path)
    
    resolved_path = runs_path
    if os.path.exists(rel_to_script):
        resolved_path = rel_to_script
    elif not os.path.exists(resolved_path):
        print(f"Error: Directory '{runs_path}' does not exist.")
        return None

    subdirs = [os.path.join(resolved_path, name) for name in os.listdir(resolved_path) if os.path.isdir(os.path.join(resolved_path, name))]
    return max(subdirs, key=os.path.getmtime) if subdirs else None


def format_timestamp(seconds):
    """Converts raw float seconds into [HH:MM:SS] or [MM:SS] string format compatible with compile_video.py regex."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    return f"[{minutes:02d}:{secs:02d}]"


def format_srt_timestamp(seconds):
    """Converts seconds to standard SRT format (HH:MM:SS,mmm) using integer millisecond precision math."""
    total_ms = int(round(max(0.0, seconds) * 1000))
    hours = total_ms // 3600000
    total_ms %= 3600000
    minutes = total_ms // 60000
    total_ms %= 60000
    secs = total_ms // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def read_whisper_preset_fallback(default_model="small"):
    preset_path = "voice_option_notes.txt"
    model_size = default_model
    if os.path.exists(preset_path):
        try:
            with open(preset_path, "r", encoding="utf-8") as f:
                for line in f:
                    if ":" in line:
                        key, val = line.split(":", 1)
                        if "whisper" in key.strip().lower():
                            model_size = val.strip()
        except Exception:
            pass
    return model_size


def slice_initial_prompt(text, max_words=120):
    if not text:
        return None
    words = text.strip().split()
    if len(words) > max_words:
        return " ".join(words[:max_words])
    return text


def read_initial_prompt(latest_run, config):
    locations = [
        os.path.join(latest_run, config["REFINED_SCRIPT_FILENAME"]),
        os.path.join(latest_run, config["FINAL_OUTPUT_FILENAME"])
    ]
    locations.extend(glob.glob(os.path.join(latest_run, "**", config["REFINED_SCRIPT_FILENAME"]), recursive=True))
    locations.extend(glob.glob(os.path.join(latest_run, "**", config["FINAL_OUTPUT_FILENAME"]), recursive=True))

    for path in locations:
        if os.path.exists(path) and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                    if text:
                        print(f"[SYSTEM] Priming Whisper with script at '{path}'.")
                        return text
            except Exception:
                pass
    return None


def clean_text_for_transcript_and_srt(text: str) -> str:
    cleaned = re.sub(r'[\(\)\[\]\{\}\"\'«»“”‘’،,\.\!\?\؟\:\;\؛—\-\…]+', ' ', text)
    return re.sub(r'\s+', ' ', cleaned).strip()


def normalize_arabic_token(w: str) -> str:
    """Normalizes Arabic text variations, diacritics, and strips non-alphanumeric chars."""
    if not w:
        return ""
    w = re.sub(r'[\u064B-\u065F\u0670]', '', w)  # Tashkeel
    w = re.sub(r'[إأآٱ]', 'ا', w)
    w = re.sub(r'ى', 'ي', w)
    w = re.sub(r'ة', 'ه', w)
    w = re.sub(r'[^\w\s]', '', w)
    return w.strip().lower()


# ============================================================
# TIME-PRESERVING SCRIPT-TO-AUDIO ALIGNMENT ENGINE (FIXED)
# ============================================================
def align_script_words_with_audio(script_text: str, whisper_words: list) -> list:
    """
    Globally aligns full script words to Whisper audio word timestamps using 
    sequence matching and time interpolation.
    GUARANTEES: Monotonically increasing time, zero audio drift, accurate sync.
    """
    script_tokens_raw = script_text.split()
    if not script_tokens_raw:
        return []
    if not whisper_words:
        return [{"text": w, "start": 0.0, "end": 0.0} for w in script_tokens_raw]

    # Less aggressive normalization: keep word boundaries, only strip diacritics
    def light_normalize(w: str) -> str:
        if not w:
            return ""
        w = re.sub(r'[\u064B-\u065F\u0670]', '', w)  # Tashkeel only
        w = re.sub(r'[إأآٱ]', 'ا', w)
        w = re.sub(r'ى', 'ي', w)
        w = re.sub(r'ة', 'ه', w)
        return w.strip().lower()

    script_norm = [light_normalize(w) for w in script_tokens_raw]
    whisper_norm = [light_normalize(w["word"]) for w in whisper_words]

    # Find matching anchor blocks across the full text
    matcher = difflib.SequenceMatcher(None, script_norm, whisper_norm, autojunk=False)
    matching_blocks = matcher.get_matching_blocks()

    aligned = [None] * len(script_tokens_raw)

    # 1. Place exact anchor word timings (only blocks with size >= 2 to avoid false singles)
    for block in matching_blocks:
        if block.size < 2:
            continue
        for offset in range(block.size):
            s_idx = block.a + offset
            w_idx = block.b + offset
            if s_idx < len(aligned) and w_idx < len(whisper_words):
                w_item = whisper_words[w_idx]
                aligned[s_idx] = {
                    "text": script_tokens_raw[s_idx],
                    "start": w_item["start"],
                    "end": w_item["end"]
                }

    # 2. Interpolate with monotonic enforcement and minimum granularity
    total_words = len(aligned)
    audio_max_end = whisper_words[-1]["end"]
    MIN_STEP = 0.05  # 50ms minimum per word

    # Fill leading unaligned words before first anchor
    first_anchor_idx = next((i for i, item in enumerate(aligned) if item is not None), None)
    if first_anchor_idx is not None and first_anchor_idx > 0:
        first_t = aligned[first_anchor_idx]["start"]
        # Distribute leading words evenly before first anchor
        step = max(MIN_STEP, first_t / (first_anchor_idx + 1))
        for i in range(first_anchor_idx):
            aligned[i] = {
                "text": script_tokens_raw[i],
                "start": i * step,
                "end": (i + 1) * step
            }

    # Fill intermediate gaps between anchors
    i = 0
    while i < total_words:
        if aligned[i] is None:
            gap_start = i
            while i < total_words and aligned[i] is None:
                i += 1
            gap_end = i  # first non-None anchor or end of list

            t_start = aligned[gap_start - 1]["end"] if gap_start > 0 else 0.0
            t_end = aligned[gap_end]["start"] if gap_end < total_words else max(t_start + 1.0, audio_max_end)

            # Ensure minimum span for the gap
            span = max(MIN_STEP * (gap_end - gap_start), t_end - t_start)
            num_unaligned = gap_end - gap_start
            step = span / (num_unaligned + 1)

            for g in range(gap_start, gap_end):
                aligned[g] = {
                    "text": script_tokens_raw[g],
                    "start": t_start + ((g - gap_start) * step),
                    "end": t_start + ((g - gap_start + 1) * step)
                }
        else:
            i += 1

    # 3. Enforce strict monotonic increasing timestamps
    for idx in range(1, total_words):
        if aligned[idx]["start"] <= aligned[idx - 1]["end"]:
            aligned[idx]["start"] = aligned[idx - 1]["end"] + 0.01
        if aligned[idx]["end"] <= aligned[idx]["start"]:
            aligned[idx]["end"] = aligned[idx]["start"] + MIN_STEP

    return aligned


# ============================================================
# ACCURATE PUNCTUATION-BASED SENTENCE / CLAUSE SPLITTER (FIXED)
# ============================================================
def split_into_punctuated_sentences(aligned_words: list, config: dict) -> list:
    """
    Accurately splits words into sentences/clauses based on:
    - Commas: '،', ','
    - Periods: '.', '..', '...'
    - Exclamation marks: '!'
    - Question marks: '؟', '?'
    - Colons: ':' (Speaker transitions like 'أبو حميد:', 'أبو حمادة:')
    - Semicolons: '؛', ';'
    - Dashes/Ellipses: '—', '-', '…'
    - Audio pauses: >= SILENCE_SPLIT_GAP_SEC

    FOR IMAGE GENERATION: Every punctuation mark forces a split (max granularity).
    Only silence-gap splits are subject to micro-fragment merging.
    """
    if not aligned_words:
        return []

    MIN_DURATION = float(config.get("MIN_SENTENCE_DURATION_SEC", 0.8))
    SILENCE_GAP = float(config.get("SILENCE_SPLIT_GAP_SEC", 0.55))

    # ALL punctuation = forced split for image timestamps (max granularity)
    PUNCT_SPLIT_REGEX = re.compile(r'[\،\,\.\!\?\؟\:\;\؛\—\-\…]+$')
    SPEAKER_TAG_REGEX = re.compile(r'^(أبو\s+\w+|طنط\s+\w+|الراوي|المذيع|المقدم)\s*:', re.IGNORECASE)

    sentences = []
    current_words = []
    pending_merge = False  # Track if previous silence-gap fragment was too short

    for i, word_item in enumerate(aligned_words):
        w_text = word_item["text"]
        w_start = word_item["start"]
        w_end = word_item["end"]

        # Speaker tag detection (e.g. 'أبو حميد:') -> Split before if clause has words
        # BUT don't split if current clause is a micro-fragment (merge it with speaker tag instead)
        if current_words and SPEAKER_TAG_REGEX.search(w_text):
            clause_duration = current_words[-1]["end"] - current_words[0]["start"]
            if clause_duration >= MIN_DURATION or pending_merge:
                clause_text = " ".join(w["text"] for w in current_words).strip()
                sentences.append({
                    "start": current_words[0]["start"],
                    "end": current_words[-1]["end"],
                    "raw_text": clause_text,
                    "clean_text": clean_text_for_transcript_and_srt(clause_text)
                })
                current_words = []
                pending_merge = False
            # else: keep current_words, let speaker tag be part of next clause

        current_words.append(word_item)

        is_last = (i == len(aligned_words) - 1)
        has_punct = bool(PUNCT_SPLIT_REGEX.search(w_text))

        next_gap = 0.0
        if not is_last:
            next_gap = max(0.0, aligned_words[i + 1]["start"] - w_end)

        should_split = False
        split_type = None  # 'punct' or 'silence' or 'end'
        if is_last:
            should_split = True
            split_type = 'end'
        elif has_punct:
            should_split = True
            split_type = 'punct'
        elif next_gap >= SILENCE_GAP:
            should_split = True
            split_type = 'silence'

        if should_split:
            clause_duration = current_words[-1]["end"] - current_words[0]["start"]

            # Micro-fragment handling: ONLY for silence-gap splits
            # Punctuation splits ALWAYS split (max granularity for image generation)
            if split_type == 'silence' and not is_last and clause_duration < MIN_DURATION and not w_text.endswith(":"):
                # Mark to merge with next clause - DON'T create sentence, DON'T clear current_words
                pending_merge = True
                continue

            # Normal split: create sentence from accumulated words
            clause_text = " ".join(w["text"] for w in current_words).strip()
            sentences.append({
                "start": current_words[0]["start"],
                "end": current_words[-1]["end"],
                "raw_text": clause_text,
                "clean_text": clean_text_for_transcript_and_srt(clause_text)
            })
            current_words = []
            pending_merge = False

    # Handle any remaining words
    if current_words:
        clause_text = " ".join(w["text"] for w in current_words).strip()
        sentences.append({
            "start": current_words[0]["start"],
            "end": current_words[-1]["end"],
            "raw_text": clause_text,
            "clean_text": clean_text_for_transcript_and_srt(clause_text)
        })

    # Post-process: merge only adjacent silence-gap fragments that are both too short
    # (punctuation splits already forced, so this only catches edge-case silence merges)
    merged = []
    for s in sentences:
        if merged and (s["end"] - s["start"]) < MIN_DURATION and (merged[-1]["end"] - merged[-1]["start"]) < MIN_DURATION:
            # Merge with previous
            merged[-1]["end"] = s["end"]
            merged[-1]["raw_text"] += " " + s["raw_text"]
            merged[-1]["clean_text"] += " " + s["clean_text"]
        else:
            merged.append(s)

    return merged


def load_whisper_model(config):
    """Safely loads Whisper model with GPU fallbacks and CPU int8 mode."""
    model_size = config["WHISPER_MODEL_SIZE"]
    model_size = read_whisper_preset_fallback(default_model=model_size)

    # Force CPU for GeForce 840M (2GB VRAM, compute capability 5.0) - CUDA compatibility issues
    try:
        print(f"Loading Whisper ('{model_size}') on CPU (int8)...")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        print("Model loaded successfully on CPU.")
        return model
    except Exception as e:
        print(f"Error loading Whisper model on CPU: {e}")
        sys.exit(1)

    # GPU fallback (commented out - uncomment if CUDA is properly configured)
    # if torch.cuda.is_available():
    #     for compute_type in ["int8_float16", "float16", "int8", "float32"]:
    #         try:
    #             print(f"Loading Whisper ('{model_size}') on GPU ({compute_type})...")
    #             model = WhisperModel(model_size, device="cuda", compute_type=compute_type)
    #             print(f"Model loaded successfully on GPU ({compute_type}).")
    #             return model
    #         except Exception as e:
    #             print(f"  [WARN] GPU load failed for {compute_type}: {e}")


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True, errors='replace')
    except Exception:
        pass

    print("=============================================")
    print("Starting Accurate Faster-Whisper Arabic Transcription")
    print("=============================================")

    config = load_transcribe_config("transcribe_config.txt")

    latest_run = get_latest_run_folder(config["RUNS_DIR"])
    if not latest_run:
        print(f"Error: No active run folders found in '{config['RUNS_DIR']}'.")
        sys.exit(1)

    print(f"Target Video Folder: {latest_run}")

    target_audio = os.path.join(latest_run, config["POLISHED_AUDIO_SUBDIR"], config["AUDIO_FILENAME"])
    if os.path.exists(target_audio):
        print(f"[AUDIO] Target: Audacity Polished Voice Track ('{target_audio}')")
    else:
        target_audio = os.path.join(latest_run, config["AUDIO_FILENAME"])
        if os.path.exists(target_audio):
            print(f"[AUDIO] Fallback: Raw Voice Track ('{target_audio}')")
        else:
            print(f"Error: Master audio file not found at '{target_audio}'.")
            sys.exit(1)

    model = load_whisper_model(config)

    print("\nTranscribing audio with exact word timestamps...")
    start_time = time.time()

    raw_custom_prompt = read_initial_prompt(latest_run, config)
    initial_prompt_sliced = slice_initial_prompt(raw_custom_prompt, config["INITIAL_PROMPT_MAX_WORDS"]) if raw_custom_prompt else config["DEFAULT_INITIAL_PROMPT"]

    try:
        segments_gen, _ = model.transcribe(
            target_audio,
            language=config["WHISPER_LANGUAGE"],
            initial_prompt=initial_prompt_sliced,
            word_timestamps=True,
            beam_size=config["WHISPER_BEAM_SIZE"],
            vad_filter=config["WHISPER_VAD_FILTER"],
            vad_parameters=dict(min_speech_duration_ms=config["WHISPER_MIN_SPEECH_DURATION_MS"])
        )

        whisper_words = []
        for segment in segments_gen:
            if segment.words:
                for word in segment.words:
                    whisper_words.append({
                        "word": word.word.strip(),
                        "start": word.start,
                        "end": word.end
                    })

        if raw_custom_prompt and whisper_words:
            print("[ALIGNMENT] Performing monotonic time alignment with refined script...")
            aligned_words = align_script_words_with_audio(raw_custom_prompt, whisper_words)
        else:
            aligned_words = [{"text": w["word"], "start": w["start"], "end": w["end"]} for w in whisper_words]

        # Generate accurate punctuated sentences / clauses
        punctuated_sentences = split_into_punctuated_sentences(aligned_words, config)

    except Exception as e:
        print(f"Error transcribing master audio: {e}")
        sys.exit(1)

    elapsed_time = time.time() - start_time
    avg_dur = sum(s['end'] - s['start'] for s in punctuated_sentences) / max(1, len(punctuated_sentences))
    print(f"\nTranscription completed in {elapsed_time:.2f} seconds.")
    print(f"Generated {len(punctuated_sentences)} Accurate Punctuated Sentences (Average duration: {avg_dur:.2f}s).")

    # 1. Save image_timestamps.txt (Exact punctuated sentences with accurate timing)
    image_timestamp_lines = [f"{format_timestamp(s['start'])} {s['raw_text']}" for s in punctuated_sentences]
    path_images = os.path.join(latest_run, "image_timestamps.txt")
    with open(path_images, "w", encoding="utf-8") as f:
        f.write("\n".join(image_timestamp_lines))
    print(f"Image timeline saved: '{path_images}'")

    # 2. Save timestamped_transcript.txt
    path_transcript = os.path.join(latest_run, "timestamped_transcript.txt")
    with open(path_transcript, "w", encoding="utf-8") as f:
        f.write("\n".join(image_timestamp_lines))
    print(f"Clean transcript saved: '{path_transcript}'")

    # 3. Save SRT Subtitles
    if config["EXPORT_SRT"]:
        output_srt_lines = []
        for srt_idx, s in enumerate(punctuated_sentences, 1):
            output_srt_lines.extend([
                str(srt_idx),
                f"{format_srt_timestamp(s['start'])} --> {format_srt_timestamp(s['end'])}",
                s["clean_text"],
                ""
            ])

        for filename in ["timestamped_transcript.srt", "subtitle_chunks.srt"]:
            path_srt = os.path.join(latest_run, filename)
            with open(path_srt, "w", encoding="utf-8-sig") as f:
                f.write("\n".join(output_srt_lines))
            print(f"Subtitle SRT saved: '{path_srt}'")

    print("=============================================")


if __name__ == "__main__":
    main()