import os
import sys
import time
import torch
import whisper
import wave  # Used to extract precise audio segment durations
import glob  # For finding folders

# Prepend the WinGet Links directory to the PATH to ensure the newly installed ffmpeg is accessible
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

# Read Whisper model size preference from voice_option_notes.txt
def read_whisper_preset():
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

def main():
    # Reconfigure stdout to use UTF-8 and line buffering to prevent replacement characters and buffering delays
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True, errors='replace')
    except Exception:
        try:
            sys.stdout.reconfigure(line_buffering=True, errors='replace')
        except Exception:
            pass

    print("=============================================")
    print("Starting Automatic Arabic Audio Transcription")
    print("=============================================")

    # 1. Locate the latest run folder
    latest_run = get_latest_run_folder()
    if not latest_run:
        print("Error: No active run folders found in 'youtube_runs/'.")
        sys.exit(1)
        
    print(f"Target Video Folder: {latest_run}")

    # 2. Locate the Stitched Master Audio File
    # Prioritize the studio-polished Audacity version if it exists
    target_audio = os.path.join(latest_run, "audacity_voice", "full_episode_voice.wav")
    if not os.path.exists(target_audio):
        print("[WARNING] Audacity polished audio not found. Falling back to raw stitched audio.")
        target_audio = os.path.join(latest_run, "full_episode_voice.wav")
        if not os.path.exists(target_audio):
            print(f"Error: Master audio file not found at '{target_audio}'.")
            print("Please ensure stitch_chapters.py (and optionally automate_audacity.py) has run.")
            sys.exit(1)

    print(f"Targeting master audio track: {target_audio}")

    # 3. Load the Whisper model based on voice_option_notes.txt
    model_size = read_whisper_preset()
    print(f"Initializing local Whisper model ('{model_size}')...")
    
    try:
        model = whisper.load_model(model_size)
        print("Model loaded successfully.")
    except Exception as e:
        print(f"Error loading Whisper model: {e}")
        sys.exit(1)

    print("\nTranscribing absolute timestamps...")
    start_time = time.time()
    
    use_fp16 = torch.cuda.is_available()
    print(f"CUDA Available: {use_fp16} (Using GPU for processing: {use_fp16})")

    # Priming Whisper with correctly spelled Egyptian terms
    egyptian_arabic_prompt = (
        "الجاس لايتنج، الجاسلايتنج، يا عم، بتهلوس، ميكروباص، المريونيط، اللنبة، سدق، بتلعي، الرموت كونترول."
    )

    output_text_lines = []
    output_srt_lines = []
    srt_index = 1
    
    print("\n--- Generated Timestamped Script ---")

    # 4. Transcribe the single master audio file
    try:
        # OPTIMIZATION: beam_size=3 boosts accuracy without crashing 2GB VRAM. word_timestamps enables micro-captions.
        result = model.transcribe(
            target_audio, 
            language="ar", 
            fp16=use_fp16, 
            initial_prompt=egyptian_arabic_prompt,
            word_timestamps=True,
            beam_size=3 
        )
        
        segments = result.get("segments", [])
        
        # Extract all words across all segments into a single flat list
        all_words = []
        for segment in segments:
            for word_info in segment.get("words", []):
                all_words.append(word_info)
                
        if not all_words:
            # Fallback if audio is completely silent or failed to generate words
            text_content = result.get("text", "").strip() or "..."
            absolute_start = 0.0
            
            # Grab duration safely using wave
            try:
                import wave
                with wave.open(target_audio, 'rb') as f:
                    absolute_end = f.getnframes() / float(f.getframerate())
            except Exception:
                absolute_end = 2.0
            
            output_text_lines.append(f"{format_timestamp(absolute_start)} {text_content}")
            output_srt_lines.extend([
                str(srt_index),
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
                if not w_text: continue
                if img_start is None: img_start = w_start
                img_words.append(w_text)
                
                is_last = (i == len(all_words) - 1)
                has_punct = any(p in w_text for p in ['.', '!', '؟', '?'])
                next_gap = (all_words[i+1].get("start", word_obj.get("end", 0)) - word_obj.get("end", 0)) if not is_last else 0.0
                
                # Break if > 18 words, OR if > 10 words and there's a pause/punctuation, OR heavy pause
                if is_last or next_gap > 1.2 or len(img_words) >= 18 or (len(img_words) >= 10 and (has_punct or next_gap > 0.4)):
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
                has_punct = any(p in w_text for p in ['.', '!', '؟', '،', ','])
                next_gap = (all_words[i+1].get("start", w_end) - w_end) if not is_last else 0.0
                
                # Break tightly: Max 4 words, or commas, or small pauses
                if is_last or len(srt_words) >= 4 or has_punct or next_gap > 0.3:
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
        # If the GPU crashed from VRAM limits, catch it gracefully
        if "OutOfMemoryError" in str(e) or "CUDA out of memory" in str(e):
            print("\n[HARDWARE WARNING] Your GeForce 840M ran out of VRAM!")
            print("To fix: Open voice_option_notes.txt and change Whisper Model from 'small' to 'base'.")
            sys.exit(1)

    elapsed_time = time.time() - start_time
    print(f"\nTranscription completed in {elapsed_time:.2f} seconds.")

    # 5. Save the plain timestamped text transcript (IMAGE TIMELINE - 10-18 words per chunk)
    image_timeline_path = os.path.join(latest_run, "timestamped_transcript.txt")
    with open(image_timeline_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_text_lines))
    print("=============================================")
    print(f"Image Timeline saved: '{image_timeline_path}'")

    # 6. Save the standard `.srt` subtitle file for video editor imports (CAPTION TIMELINE - 1-4 words per chunk)
    srt_file_path = os.path.join(latest_run, "timestamped_transcript.srt")
    try:
        with open(srt_file_path, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(output_srt_lines))
        print(f"Subtitle SRT saved: '{srt_file_path}'")
        print("=============================================")
    except Exception as e:
        print(f"Error saving subtitle file: {e}")

    # 7. Save the IMAGE TIMELINE for the video compiler (MM:SS format for image sync)
    # Format: [MM:SS] text (same as output_text_lines but separate file for clarity)
    image_timestamps_path = os.path.join(latest_run, "image_timestamps.txt")
    with open(image_timestamps_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_text_lines))
    print(f"Image Timestamps saved: '{image_timestamps_path}'")

    # 8. Save the SUBTITLE CHUNKS for the video compiler (SRT format, 1-4 words)
    subtitle_chunks_path = os.path.join(latest_run, "subtitle_chunks.srt")
    with open(subtitle_chunks_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(output_srt_lines))
    print(f"Subtitle Chunks saved: '{subtitle_chunks_path}'")
    print("=============================================")

if __name__ == "__main__":
    main()