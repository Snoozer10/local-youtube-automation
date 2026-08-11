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


def get_latest_run_folder(runs_path="youtube_runs"):
    if not os.path.exists(runs_path):
        print(f"Error: Directory '{runs_path}' does not exist.")
        return None
    
    folders = glob.glob(os.path.join(runs_path, "*"))
    folders = [f for f in folders if os.path.isdir(f)]
    if not folders:
        return None
    
    latest_folder = max(folders, key=os.path.getmtime)
    return latest_folder


def format_timestamp(seconds):
    """Converts raw float seconds into the [MM:SS] string format."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"[{minutes:02d}:{secs:02d}]"


def format_srt_timestamp(seconds):
    """Converts raw float seconds into the standard SRT format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def read_whisper_preset():
    """Read Whisper model size preference from voice_option_notes.txt."""
    preset_path = "voice_option_notes.txt"
    model_size = "small"
    if os.path.exists(preset_path):
        try:
            with open(preset_path, "r", encoding="utf-8") as f:
                for line in f:
                    if ":" in line:
                        key, val = line.split(":", 1)
                        key = key.strip().lower()
                        if "whisper" in key:
                            model_size = val.strip()
            print(f"Loaded Whisper model preset: '{model_size}'")
        except Exception:
            pass
    return model_size


def read_initial_prompt(latest_run):
    """Looks for script to prime Whisper (refined_script.txt or final_output.txt)."""
    locations_refined = [os.path.join(latest_run, "refined_script.txt")]
    locations_final = [os.path.join(latest_run, "final_output.txt")]
    
    locations_refined.extend(glob.glob(os.path.join(latest_run, "**", "refined_script.txt"), recursive=True))
    locations_final.extend(glob.glob(os.path.join(latest_run, "**", "final_output.txt"), recursive=True))

    for path in locations_refined:
        if os.path.exists(path) and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                    if text:
                        print(f"[SYSTEM] Found refined script at '{path}'. Priming Whisper with it.")
                        return text
            except Exception:
                pass
                
    for path in locations_final:
        if os.path.exists(path) and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                    if text:
                        print(f"[SYSTEM] Priming Whisper with Cairo Cut Arabic script at '{path}'.")
                        return text
            except Exception:
                pass

    print("[SYSTEM] No custom script found. Falling back to default Egyptian Arabic prompt.")
    return None


def align_and_pace_script(custom_prompt, all_words):
    """
    ANIMATION CADENCE ENGINE:
    Splits audio into visually rhythmic units targetting 1.8s - 4.2s per keyframe.
    Detects punctuation, speech pauses (>0.45s), and transition words.
    """
    def clean_tok(w):
        return re.sub(r'[^\w\s]', '', w).strip().lower()

    script_words = custom_prompt.split()
    aligned_words = []
    w_idx = 0
    n_whisper = len(all_words)

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
            aligned_words.append({
                "text": word_raw,
                "start": matched_item["start"],
                "end": matched_item["end"]
            })
        else:
            fallback_start = aligned_words[-1]["end"] if aligned_words else 0.0
            aligned_words.append({
                "text": word_raw,
                "start": fallback_start,
                "end": fallback_start + 0.3
            })

    ARABIC_TRANSITION_WORDS = {"علشان", "عشان", "بس", "لكن", "يعني", "ثم", "لما", "بعدين", "فبالتالي", "معنى", "زي", "يعني", "أو", "أوكي", "تمام", "طيب", ","}
    PUNCTUATION_REGEX = re.compile(r'[،,.؟?!\n]+')

    chunks = []
    curr_words = []
    chunk_start = None

    MIN_DURATION = 1.8
    TARGET_DURATION = 3.2
    MAX_DURATION = 4.2

    for i, w_info in enumerate(aligned_words):
        w_text = w_info["text"]
        w_start = w_info["start"]
        w_end = w_info["end"]

        if chunk_start is None:
            chunk_start = w_start

        curr_words.append(w_text)
        curr_duration = w_end - chunk_start

        has_punctuation = bool(PUNCTUATION_REGEX.search(w_text))
        is_last_word = (i == len(aligned_words) - 1)
        
        next_gap = 0.0
        if i < len(aligned_words) - 1:
            next_gap = aligned_words[i + 1]["start"] - w_end

        clean_w = clean_tok(w_text)
        is_transition = clean_w in ARABIC_TRANSITION_WORDS

        should_split = False

        if is_last_word:
            should_split = True
        elif curr_duration >= MAX_DURATION:
            should_split = True
        elif curr_duration >= MIN_DURATION:
            if has_punctuation:
                should_split = True
            elif next_gap >= 0.45:
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


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True, errors='replace')
    except Exception:
        try:
            sys.stdout.reconfigure(line_buffering=True, errors='replace')
        except Exception:
            pass

    print("=============================================")
    print("Starting Faster-Whisper Arabic Audio Transcription")
    print("=============================================")

    latest_run = get_latest_run_folder()
    if not latest_run:
        print("Error: No active run folders found in 'youtube_runs/'.")
        sys.exit(1)
        
    print(f"Target Video Folder: {latest_run}")

    # Priority Path Resolution: Polished Audacity audio -> Raw audio fallback
    target_audio = os.path.join(latest_run, "audacity_voice", "full_episode_voice.wav")
    if os.path.exists(target_audio):
        print(f"[AUDIO] Target: Audacity Polished Voice Track ('{target_audio}')")
    else:
        target_audio = os.path.join(latest_run, "full_episode_voice.wav")
        if os.path.exists(target_audio):
            print(f"[AUDIO] Audacity track missing. Fallback to Raw Voice Track ('{target_audio}')")
        else:
            print(f"Error: Master audio file not found at '{target_audio}'.")
            sys.exit(1)

    model_size = read_whisper_preset()
    model = None

    if torch.cuda.is_available():
        try:
            print(f"Initializing local faster-whisper model ('{model_size}') on GPU...")
            model = WhisperModel(model_size, device="cuda", compute_type="int8_float16")
            print("Model loaded successfully on GPU (CUDA).")
        except Exception as e:
            print(f"[WARNING] Failed to load on GPU ({e}). Falling back to CPU...")
            
    if not model:
        try:
            print(f"Initializing local faster-whisper model ('{model_size}') on CPU...")
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            print("Model loaded successfully on CPU.")
        except Exception as e:
            print(f"Error loading Whisper model on CPU: {e}")
            sys.exit(1)

    print("\nTranscribing absolute timestamps...")
    start_time = time.time()

    default_prompt = (
        "يا عم، بتهلوس؟ الجاس لايتنج ده بجد، والمريونيط بيتحرك، والرموت كونترول تاه. سدقني، بلاش تلعي بالنار، الميكروباص واقف في اللنبة."
    )

    custom_prompt = read_initial_prompt(latest_run)
    egyptian_arabic_prompt = custom_prompt if custom_prompt else default_prompt

    output_text_lines = []
    output_srt_lines = []
    
    print("\n--- Generating Timestamped Script ---")

    try:
        segments_gen, info = model.transcribe(
            target_audio,
            language="ar",
            initial_prompt=egyptian_arabic_prompt,
            word_timestamps=True,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_speech_duration_ms=250)
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
                
        if not all_words:
            text_content = " ".join([seg.text for seg in segments]).strip() or "..."
            absolute_start = 0.0
            
            try:
                with wave.open(target_audio, 'rb') as f:
                    absolute_end = f.getnframes() / float(f.getframerate())
            except Exception:
                absolute_end = 2.0
            
            output_text_lines.append(f"{format_timestamp(absolute_start)} {text_content}")
            output_srt_lines.extend([
                "1",
                f"{format_srt_timestamp(absolute_start)} --> {format_srt_timestamp(absolute_end)}",
                text_content,
                ""
            ])
        elif custom_prompt:
            paced_chunks = align_and_pace_script(custom_prompt, all_words)
            srt_index = 1

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
        else:
            output_text_lines.append(f"{format_timestamp(0.0)} {' '.join([w['word'] for w in all_words])}")

    except Exception as e:
        print(f"Error transcribing master audio: {e}")
        sys.exit(1)

    elapsed_time = time.time() - start_time
    print(f"\nTranscription completed in {elapsed_time:.2f} seconds.")

    # Save outputs
    image_timeline_path = os.path.join(latest_run, "timestamped_transcript.txt")
    with open(image_timeline_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_text_lines))
    print("=============================================")
    print(f"Image Timeline saved: '{image_timeline_path}'")

    srt_file_path = os.path.join(latest_run, "timestamped_transcript.srt")
    try:
        with open(srt_file_path, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(output_srt_lines))
        print(f"Subtitle SRT saved: '{srt_file_path}'")
    except Exception as e:
        print(f"Error saving subtitle file: {e}")

    image_timestamps_path = os.path.join(latest_run, "image_timestamps.txt")
    with open(image_timestamps_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_text_lines))

    subtitle_chunks_path = os.path.join(latest_run, "subtitle_chunks.srt")
    with open(subtitle_chunks_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(output_srt_lines))
    print("=============================================")


if __name__ == "__main__":
    main()