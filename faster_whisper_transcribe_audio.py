import os
import sys
import time
import torch
import wave
import glob
import re
from faster_whisper import WhisperModel

# Ensure WinGet binaries (ffmpeg) are accessible
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
        "PACING_MAX_WORDS": 4,
        "PACING_MIN_DURATION": 1.8,
        "PACING_TARGET_DURATION": 3.2,
        "PACING_MAX_DURATION": 4.2,
        "PACING_MIN_GAP_SPLIT": 0.45,
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
                        config[key] = int(float(value))
                    elif isinstance(default_val, float):
                        config[key] = float(value)
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
    total_ms = int(round(seconds * 1000))
    hours = total_ms // 3600000
    total_ms %= 3600000
    minutes = total_ms // 60000
    total_ms %= 60000
    secs = total_ms // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def read_whisper_preset_fallback(default_model="small"):
    """Reads Whisper model preset from voice_option_notes.txt if available."""
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
    """Slices initial prompt to prevent 224-token context buffer overflow in Whisper."""
    if not text:
        return None
    words = text.strip().split()
    if len(words) > max_words:
        sliced = " ".join(words[:max_words])
        print(f"[SYSTEM] Trimmed initial prompt from {len(words)} words to {max_words} words to fit Whisper's 224-token buffer.")
        return sliced
    return text


def read_initial_prompt(latest_run, config):
    """Looks for script to prime Whisper (refined_script.txt or final_output.txt)."""
    locations_refined = [os.path.join(latest_run, config["REFINED_SCRIPT_FILENAME"])]
    locations_final = [os.path.join(latest_run, config["FINAL_OUTPUT_FILENAME"])]
    
    locations_refined.extend(glob.glob(os.path.join(latest_run, "**", config["REFINED_SCRIPT_FILENAME"]), recursive=True))
    locations_final.extend(glob.glob(os.path.join(latest_run, "**", config["FINAL_OUTPUT_FILENAME"]), recursive=True))

    for path in locations_refined:
        if os.path.exists(path) and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                    if text:
                        print(f"[SYSTEM] Found refined script at '{path}'. Priming Whisper.")
                        return text
            except Exception:
                pass
                
    for path in locations_final:
        if os.path.exists(path) and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                    if text:
                        print(f"[SYSTEM] Priming Whisper with script at '{path}'.")
                        return text
            except Exception:
                pass

    print("[SYSTEM] No custom script found. Falling back to default Egyptian Arabic prompt.")
    return None


def align_and_pace_script(custom_prompt, all_words, config):
    """
    ANIMATION CADENCE ENGINE:
    Splits audio into visually rhythmic units using transcribe_config.txt constraints.
    Guarantees strict time monotonicity (prevents backwards/overlapping timestamps).
    """
    def clean_tok(w):
        return re.sub(r'[^\w\s]', '', w).strip().lower()

    script_words = custom_prompt.split()
    aligned_words = []
    w_idx = 0
    n_whisper = len(all_words)

    last_valid_end = 0.0

    for word_raw in script_words:
        tok = clean_tok(word_raw)
        matched_item = None

        if tok and w_idx < n_whisper:
            for search_i in range(w_idx, min(w_idx + 20, n_whisper)):
                whisper_tok = clean_tok(all_words[search_i].get("word", ""))
                if tok == whisper_tok or (len(tok) > 2 and tok in whisper_tok) or (len(whisper_tok) > 2 and whisper_tok in tok):
                    matched_item = all_words[search_i]
                    w_idx = search_i + 1
                    break

        if matched_item:
            start_t = max(matched_item["start"], last_valid_end)
            end_t = max(matched_item["end"], start_t + 0.1)
            aligned_words.append({
                "text": word_raw,
                "start": start_t,
                "end": end_t
            })
            last_valid_end = end_t
        else:
            fallback_start = last_valid_end
            fallback_end = fallback_start + 0.25
            aligned_words.append({
                "text": word_raw,
                "start": fallback_start,
                "end": fallback_end
            })
            last_valid_end = fallback_end

    ARABIC_TRANSITION_WORDS = {"علشان", "عشان", "بس", "لكن", "يعني", "ثم", "لما", "بعدين", "فبالتالي", "معنى", "زي", "أو", "أوكي", "تمام", "طيب"}
    PUNCTUATION_REGEX = re.compile(r'[،,.؟?!\n]+')

    chunks = []
    curr_words = []
    chunk_start = None

    MIN_DURATION = config["PACING_MIN_DURATION"]
    TARGET_DURATION = config["PACING_TARGET_DURATION"]
    MAX_DURATION = config["PACING_MAX_DURATION"]
    MAX_WORDS = config["PACING_MAX_WORDS"]
    MIN_GAP_SPLIT = config["PACING_MIN_GAP_SPLIT"]

    for i, w_info in enumerate(aligned_words):
        w_text = w_info["text"]
        w_start = w_info["start"]
        w_end = w_info["end"]

        if chunk_start is None:
            chunk_start = w_start

        curr_words.append(w_text)
        curr_duration = w_end - chunk_start
        word_count = len(curr_words)

        has_punctuation = bool(PUNCTUATION_REGEX.search(w_text))
        is_last_word = (i == len(aligned_words) - 1)
        
        next_gap = 0.0
        if i < len(aligned_words) - 1:
            next_gap = max(0.0, aligned_words[i + 1]["start"] - w_end)

        clean_w = clean_tok(w_text)
        is_transition = clean_w in ARABIC_TRANSITION_WORDS

        should_split = False

        if is_last_word:
            should_split = True
        elif word_count >= MAX_WORDS:
            should_split = True
        elif curr_duration >= MAX_DURATION:
            should_split = True
        elif curr_duration >= MIN_DURATION:
            if has_punctuation:
                should_split = True
            elif next_gap >= MIN_GAP_SPLIT:
                should_split = True
            elif is_transition and curr_duration >= TARGET_DURATION:
                should_split = True

        if should_split:
            chunk_text = " ".join(curr_words).strip()
            if chunk_text:
                chunks.append({
                    "start": chunk_start,
                    "end": max(w_end, chunk_start + 0.5),
                    "text": chunk_text
                })
            curr_words = []
            chunk_start = None

    return chunks


def load_whisper_model(config):
    """Safely loads Whisper model with multi-level GPU and CPU fallbacks."""
    model_size = config["WHISPER_MODEL_SIZE"]
    model_size = read_whisper_preset_fallback(default_model=model_size)

    if torch.cuda.is_available():
        for compute_type in ["int8_float16", "float16", "int8", "float32"]:
            try:
                print(f"Attempting Whisper model ('{model_size}') on GPU ({compute_type})...")
                model = WhisperModel(model_size, device="cuda", compute_type=compute_type)
                print(f"Model loaded successfully on GPU ({compute_type}).")
                return model
            except Exception as e:
                print(f"  [WARN] GPU load failed for {compute_type}: {e}")

    try:
        print(f"Initializing Whisper model ('{model_size}') on CPU (int8)...")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        print("Model loaded successfully on CPU.")
        return model
    except Exception as e:
        print(f"Error loading Whisper model on CPU: {e}")
        sys.exit(1)


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True, errors='replace')
    except Exception:
        pass

    print("=============================================")
    print("Starting Faster-Whisper Arabic Audio Transcription")
    print("=============================================")

    config = load_transcribe_config("transcribe_config.txt")
    print(f"Loaded config: MAX_WORDS={config['PACING_MAX_WORDS']}, TARGET_DURATION={config['PACING_TARGET_DURATION']}s")

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

    print("\nTranscribing absolute timestamps...")
    start_time = time.time()

    raw_custom_prompt = read_initial_prompt(latest_run, config)
    
    # Safe initial prompt slicing (Prevents 224-token buffer overflow)
    initial_prompt_sliced = slice_initial_prompt(raw_custom_prompt, config["INITIAL_PROMPT_MAX_WORDS"]) if raw_custom_prompt else config["DEFAULT_INITIAL_PROMPT"]

    output_text_lines = []
    output_srt_lines = []
    srt_index = 1

    try:
        segments_gen, info = model.transcribe(
            target_audio,
            language=config["WHISPER_LANGUAGE"],
            initial_prompt=initial_prompt_sliced,
            word_timestamps=True,
            beam_size=config["WHISPER_BEAM_SIZE"],
            vad_filter=config["WHISPER_VAD_FILTER"],
            vad_parameters=dict(min_speech_duration_ms=config["WHISPER_MIN_SPEECH_DURATION_MS"])
        )
        
        segments = list(segments_gen)
        all_words = []
        
        for segment in segments:
            if segment.words:
                for word in segment.words:
                    all_words.append({
                        "word": word.word,
                        "start": word.start,
                        "end": word.end
                    })
                
        if raw_custom_prompt and all_words:
            # Align full script text with speech timings
            paced_chunks = align_and_pace_script(raw_custom_prompt, all_words, config)
            for chunk in paced_chunks:
                c_start = chunk["start"]
                c_end = chunk["end"]
                clause = chunk["text"]

                output_text_lines.append(f"{format_timestamp(c_start)} {clause}")
                output_srt_lines.extend([
                    str(srt_index),
                    f"{format_srt_timestamp(c_start)} --> {format_srt_timestamp(c_end)}",
                    clause,
                    ""
                ])
                srt_index += 1
        elif segments:
            # Automatic segment chunking fallback if custom_prompt is None
            for segment in segments:
                s_start = segment.start
                s_end = segment.end
                s_text = segment.text.strip()
                if s_text:
                    output_text_lines.append(f"{format_timestamp(s_start)} {s_text}")
                    output_srt_lines.extend([
                        str(srt_index),
                        f"{format_srt_timestamp(s_start)} --> {format_srt_timestamp(s_end)}",
                        s_text,
                        ""
                    ])
                    srt_index += 1
        else:
            print("[WARN] No speech detected in audio.")

    except Exception as e:
        print(f"Error transcribing master audio: {e}")
        sys.exit(1)

    elapsed_time = time.time() - start_time
    print(f"\nTranscription completed in {elapsed_time:.2f} seconds.")

    # Save output timeline files
    if config["EXPORT_TIMELINE_TXT"]:
        for filename in ["timestamped_transcript.txt", "image_timestamps.txt"]:
            path = os.path.join(latest_run, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(output_text_lines))
            print(f"Timeline saved: '{path}'")

    # Save SRT files
    if config["EXPORT_SRT"]:
        for filename in ["timestamped_transcript.srt", "subtitle_chunks.srt"]:
            path = os.path.join(latest_run, filename)
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write("\n".join(output_srt_lines))
            print(f"Subtitle SRT saved: '{path}'")

    print("=============================================")


if __name__ == "__main__":
    main()