import os
import sys
import time
import torch
import wave  # Used to extract precise audio segment durations
import glob  # For finding folders
from faster_whisper import WhisperModel

# Prepend the WinGet Links directory to the PATH to ensure ffmpeg is accessible
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
    
    # Sort folders by modification time to get the newest run
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
    model_size = "small"  # Default fallback
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
    """
    Looks for a script file to use as the Whisper initial prompt.
    Prioritizes refined_script.txt, falls back to final_output.txt.
    Looks in the root run directory and recursively in subfolders.
    """
    # 1. Define paths inside the root run directory
    locations_refined = [os.path.join(latest_run, "refined_script.txt")]
    locations_final = [os.path.join(latest_run, "final_output.txt")]
    
    # 2. Add recursive subfolder paths using glob
    locations_refined.extend(glob.glob(os.path.join(latest_run, "**", "refined_script.txt"), recursive=True))
    locations_final.extend(glob.glob(os.path.join(latest_run, "**", "final_output.txt"), recursive=True))

    # Try loading refined_script.txt first
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
                
    # Fallback to final_output.txt
    for path in locations_final:
        if os.path.exists(path) and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                    if text:
                        print(f"[SYSTEM] Refined script not found. Priming Whisper with final output script at '{path}'.")
                        return text
            except Exception:
                pass

    print("[SYSTEM] No custom script found. Falling back to default Egyptian Arabic prompt.")
    return None

def main():
    # Reconfigure stdout to use UTF-8 and prevent buffering issues
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

    # 1. Locate the latest run folder
    latest_run = get_latest_run_folder()
    if not latest_run:
        print("Error: No active run folders found in 'youtube_runs/'.")
        sys.exit(1)
        
    print(f"Target Video Folder: {latest_run}")

    # 2. Locate the Stitched Master Audio File
    target_audio = os.path.join(latest_run, "audacity_voice", "full_episode_voice.wav")
    if not os.path.exists(target_audio):
        print("[WARNING] Audacity polished audio not found. Falling back to raw stitched audio.")
        target_audio = os.path.join(latest_run, "full_episode_voice.wav")
        if not os.path.exists(target_audio):
            print(f"Error: Master audio file not found at '{target_audio}'.")
            sys.exit(1)

    print(f"Targeting master audio track: {target_audio}")

    # 3. Load faster-whisper Model with Failover Safeguards
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

    # Define the default fallback prompt
    default_prompt = (
        "يا عم، بتهلوس؟ الجاس لايتنج ده بجد، والمريونيط بيتحرك، والرموت كونترول تاه. سدقني، بلاش تلعي بالنار، الميكروباص واقف في اللنبة."
    )

    # Check for a refined_script or final_output file first
    custom_prompt = read_initial_prompt(latest_run)
    egyptian_arabic_prompt = custom_prompt if custom_prompt else default_prompt

    output_text_lines = []
    output_srt_lines = []
    
    print("\n--- Generating Timestamped Script ---")

    # 4. Transcribe the master audio track
    try:
        segments_gen, info = model.transcribe(
            target_audio,
            language="ar",
            initial_prompt=egyptian_arabic_prompt,
            word_timestamps=True,
            beam_size=5,          # Upgraded to 5 for higher transcription accuracy
            vad_filter=True,      # Enabled Silero VAD to filter out empty noise and static
            vad_parameters=dict(min_speech_duration_ms=250)
        )
        
        # Pull generator results into memory
        segments = list(segments_gen)
        
        # Flatten word-level timing details across all segments
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
            # Fallback if no word-level timestamps were resolved
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
        else:
            # ==========================================
            # DUAL-TRACK CHUNKING ENGINE
            # ==========================================
            
            # TRACK 1: IMAGE TIMELINE (10-18 words per image)
            img_words = []
            img_start = None
            for i, word_obj in enumerate(all_words):
                w_text = word_obj.get("word", "").strip()
                w_start = word_obj.get("start", 0.0)
                w_end = word_obj.get("end", w_start + 0.5)
                if not w_text: continue
                if img_start is None: img_start = w_start
                img_words.append(w_text)
                
                is_last = (i == len(all_words) - 1)
                has_comma = '،' in w_text or ',' in w_text
                has_ending_punct = any(p in w_text for p in ['.', '!', '؟', '?'])
                next_gap = (all_words[i+1].get("start", w_end) - w_end) if not is_last else 0.0
                
                # Split instantly on any comma, ending punctuation, large pause, or word limits
                if is_last or has_comma or has_ending_punct or next_gap > 1.2 or len(img_words) >= 18:
                    output_text_lines.append(f"{format_timestamp(img_start)} {' '.join(img_words)}")
                    img_words = []
                    img_start = None

            # TRACK 2: SRT CAPTION TIMELINE (1-4 words max for fast reading)
            srt_words = []
            srt_start = None
            srt_index = 1
            for i, word_obj in enumerate(all_words):
                w_text = word_obj.get("word", "").strip()
                w_start = word_obj.get("start", 0.0)
                w_end = word_obj.get("end", w_start + 0.5)
                if not w_text: continue
                if srt_start is None: srt_start = w_start
                srt_words.append(w_text)
                
                is_last = (i == len(all_words) - 1)
                has_comma = '،' in w_text or ',' in w_text
                has_ending_punct = any(p in w_text for p in ['.', '!', '؟', '?'])
                next_gap = (all_words[i+1].get("start", w_end) - w_end) if not is_last else 0.0
                
                # Force subtitle chunk split at every comma, sentence ending, max length, or gap
                if is_last or has_comma or has_ending_punct or len(srt_words) >= 4 or next_gap > 0.3:
                    chunk_text = " ".join(srt_words).strip()
                    output_srt_lines.extend([
                        str(srt_index),
                        f"{format_srt_timestamp(srt_start)} --> {format_srt_timestamp(w_end)}",
                        chunk_text, ""
                    ])
                    srt_index += 1
                    srt_words = []
                    srt_start = None

    except Exception as e:
        print(f"Error transcribing master audio: {e}")
        sys.exit(1)

    elapsed_time = time.time() - start_time
    print(f"\nTranscription completed in {elapsed_time:.2f} seconds.")

    # 5. Save the plain timestamped text transcript (IMAGE TIMELINE)
    image_timeline_path = os.path.join(latest_run, "timestamped_transcript.txt")
    with open(image_timeline_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_text_lines))
    print("=============================================")
    print(f"Image Timeline saved: '{image_timeline_path}'")

    # 6. Save the standard `.srt` subtitle file
    srt_file_path = os.path.join(latest_run, "timestamped_transcript.srt")
    try:
        with open(srt_file_path, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(output_srt_lines))
        print(f"Subtitle SRT saved: '{srt_file_path}'")
        print("=============================================")
    except Exception as e:
        print(f"Error saving subtitle file: {e}")

    # 7. Save the IMAGE TIMELINE for the video compiler
    image_timestamps_path = os.path.join(latest_run, "image_timestamps.txt")
    with open(image_timestamps_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_text_lines))
    print(f"Image Timestamps saved: '{image_timestamps_path}'")

    # 8. Save the SUBTITLE CHUNKS for the video compiler
    subtitle_chunks_path = os.path.join(latest_run, "subtitle_chunks.srt")
    with open(subtitle_chunks_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(output_srt_lines))
    print(f"Subtitle Chunks saved: '{subtitle_chunks_path}'")
    print("=============================================")


if __name__ == "__main__":
    main()