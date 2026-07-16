import os
import sys
import wave

def get_latest_run_folder(runs_path="youtube_runs"):
    if not os.path.exists(runs_path):
        print(f"Error: Directory '{runs_path}' does not exist.")
        return None
    # Get all subdirectories in youtube_runs
    subdirs = [
        os.path.join(runs_path, name)
        for name in os.listdir(runs_path)
        if os.path.isdir(os.path.join(runs_path, name))
    ]
    if not subdirs:
        return None
    # Sort folders by modification time to get the newest run
    latest_folder = max(subdirs, key=os.path.getmtime)
    return latest_folder

def main():
    print("=============================================")
    print("Starting Standalone Audio Chapter Stitcher")
    print("=============================================")

    # 1. Locate the latest run directory dynamically
    latest_run = get_latest_run_folder()
    if not latest_run:
        print("Error: No active run folders found in 'youtube_runs/'.")
        sys.exit(1)
        
    print(f"Target Video Folder: '{latest_run}'")

    # 2. Determine target chapters directory (Polished Chapters vs Raw Voice Chapters fallback)
    polished_dir = os.path.join(latest_run, "polished_chapters")
    voice_dir = os.path.join(latest_run, "voice_chapters")
    
    # Prioritize polished_chapters, fall back to voice_chapters
    if os.path.exists(polished_dir) and os.path.exists(os.path.join(polished_dir, "Chapter_1.wav")):
        chapters_source_dir = polished_dir
        print("[SYSTEM] Found polished chapters. Utilizing 'polished_chapters' as the audio source.")
    elif os.path.exists(voice_dir) and os.path.exists(os.path.join(voice_dir, "Chapter_1.wav")):
        chapters_source_dir = voice_dir
        print("[SYSTEM] Polished chapters not found. Falling back to raw 'voice_chapters' as the audio source.")
    else:
        print(f"Error: Could not find sequential Chapter_*.wav files in either:\n - '{polished_dir}'\n - '{voice_dir}'")
        sys.exit(1)

    # Scan for numerically sequential Chapter_X.wav files starting at 1 inside the target directory
    file_list = []
    idx = 1
    while True:
        chapter_path = os.path.join(chapters_source_dir, f"Chapter_{idx}.wav")
        if os.path.exists(chapter_path):
            file_list.append(chapter_path)
            idx += 1
        else:
            break

    print(f"Detected {len(file_list)} sequential voice chapters to stitch.")
    output_path = os.path.join(latest_run, "full_episode_voice.wav")

    # 3. Stitch Wave files sequentially with a 1-second silence gap
    try:
        # Read format parameters from the first file
        with wave.open(file_list[0], 'rb') as first_file:
            params = first_file.getparams()
            
        print("Stitching chapters cleanly...")
        with wave.open(output_path, 'wb') as output_file:
            output_file.setparams(params)
            
            for path in file_list:
                print(f" - Appending: '{os.path.basename(path)}'")
                with wave.open(path, 'rb') as input_file:
                    # Write frames from chapter
                    output_file.writeframes(input_file.readframes(input_file.getnframes()))
                    
                    # Add a clean 1-second silence padding between chapters
                    silence_frames = b'\x00' * (params.framerate * params.sampwidth * params.nchannels * 1)
                    output_file.writeframes(silence_frames)
                    
        print("=============================================")
        print("Success! Master audio track updated cleanly.")
        print(f"Output File: '{output_path}'")
        print("=============================================")
        
    except Exception as e:
        print(f"Error stitching audio tracks: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
