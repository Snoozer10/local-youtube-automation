language="python"
title="automate_audacity.py"
id="automate-audacity-flexible"
type="application/vnd.ant.code"
import os
import sys
import time
import subprocess
import shutil
import re
import glob
import json

def get_latest_run_folder(runs_path="youtube_runs"):
    if not os.path.exists(runs_path):
        return None
    subdirs = [os.path.join(runs_path, d) for d in os.listdir(runs_path) if os.path.isdir(os.path.join(runs_path, d))]
    if not subdirs:
        return None
    return max(subdirs, key=os.path.getmtime)


def send_audacity_command(write_pipe, read_pipe, command):
    """Sends a single scripting command to Audacity and waits for response."""
    print(f"  [PIPE SEND] {command}")
    write_pipe.write(command + "\n")
    write_pipe.flush()
    
    # Read response until an empty line is returned (Audacity command terminators)
    response = ""
    while True:
        line = read_pipe.readline()
        response += line
        if line.strip() == "":
            break
            
    # Clean and log the response to make sure we see any failures
    cleaned_response = response.strip().replace("\n", " | ")
    print(f"  [PIPE RESPONSE] {cleaned_response}")
    return response

# Add these helper functions right above main()
def load_checkpoint(folder):
    path = os.path.join(folder, "audacity_checkpoint.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("polished_files", [])
        except:
            pass
    return []

def save_checkpoint(folder, polished_files):
    path = os.path.join(folder, "audacity_checkpoint.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"polished_files": polished_files}, f, ensure_ascii=False, indent=2)


def delete_checkpoint(folder):
    path = os.path.join(folder, "audacity_checkpoint.json")
    if os.path.exists(path):
        try:
            os.remove(path)
        except:
            pass

def clear_audacity_temp_data():
    """Wipes Audacity's temporary SessionData and AutoSave folders to prevent 'Automatic Crash Recovery' popups."""
    import shutil
    
    # 1. Clear Local SessionData (usually in AppData\Local\Audacity\SessionData)
    local_appdata = os.getenv('LOCALAPPDATA')
    if local_appdata:
        session_data_dir = os.path.join(local_appdata, 'Audacity', 'SessionData')
        if os.path.exists(session_data_dir):
            for item in os.listdir(session_data_dir):
                item_path = os.path.join(session_data_dir, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                except Exception:
                    pass

    # 2. Clear Roaming AutoSave (usually in AppData\Roaming\audacity\AutoSave)
    roaming_appdata = os.getenv('APPDATA')
    if roaming_appdata:
        autosave_dir = os.path.join(roaming_appdata, 'audacity', 'AutoSave')
        if os.path.exists(autosave_dir):
            for item in os.listdir(autosave_dir):
                item_path = os.path.join(autosave_dir, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                except Exception:
                    pass

def main():
    print("=============================================")
    print("Starting Autonomous Audacity Audio Polishing")
    print("=============================================")

    # Force kill any hidden zombie Audacity processes to release all active file locks
    try:
        subprocess.run(["taskkill", "/F", "/IM", "Audacity.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.0) # Wait for system to release locks
    except:
        pass

    # Wipe leftover crash files on startup
    clear_audacity_temp_data()

    # 1. Locate Run Folder
    latest_run = get_latest_run_folder()
    if not latest_run:
        print("Error: No active run folder detected.")
        sys.exit(1)

    print(f"Target Video Folder: {latest_run}")
    
    # 2. Determine Processing Target (Master Track vs Chapters Subfolder)
    master_track_path = os.path.join(latest_run, "full_episode_voice.wav")
    files_to_process = []
    
    if os.path.exists(master_track_path):
        # Case A: Master stitched voice track found
        print("[SYSTEM] Found 'full_episode_voice.wav'. Targeting the master voice track only.")
        output_dir = os.path.join(latest_run, "audacity_voice")
        files_to_process.append((0, "full_episode_voice.wav", latest_run, output_dir))
    else:
        # Case B: Fallback to voice_chapters subfolder
        print("[SYSTEM] Master voice track not found. Scanning 'voice_chapters' subfolder...")
        chapters_dir = os.path.join(latest_run, "voice_chapters")
        
        if not os.path.exists(chapters_dir):
            print(f"Error: Neither 'full_episode_voice.wav' nor the 'voice_chapters' folder exists in '{latest_run}'.")
            sys.exit(1)
            
        output_dir = os.path.join(latest_run, "polished_chapters")
        chapter_files = []
        for name in os.listdir(chapters_dir):
            if name.startswith("Chapter_") and name.endswith(".wav"):
                match = re.search(r"Chapter_(\d+)\.wav", name)
                if match:
                    idx = int(match.group(1))
                    chapter_files.append((idx, name, chapters_dir, output_dir))
                    
        chapter_files.sort(key=lambda x: x[0])
        
        if not chapter_files:
            print(f"Error: No Chapter_*.wav files found in '{chapters_dir}'.")
            sys.exit(1)
            
        print(f"Found {len(chapter_files)} chapters to polish inside the 'voice_chapters' directory.")
        files_to_process = chapter_files

    # Load checkpoint progress to resume mid-run
    polished_files = load_checkpoint(latest_run)
    if polished_files:
        print(f"[CHECKPOINT] Resuming. Already polished {len(polished_files)} of {len(files_to_process)} files.")

    # 3. Find Audacity Executable Path
    audacity_paths = [
        r"C:\Program Files\Audacity\Audacity.exe",
        r"C:\Program Files (x86)\Audacity\Audacity.exe"
    ]
    executable_path = next((p for p in audacity_paths if os.path.exists(p)), None)
    if not executable_path:
        print("Error: Audacity.exe not found in standard Windows paths.")
        sys.exit(1)

    # 4. Polish target audio files sequentially
    for idx, name, base_dir, output_dir in files_to_process:
        if name in polished_files:
            print(f"Skipping already polished file: {name}")
            continue

        os.makedirs(output_dir, exist_ok=True)
        raw_audio_path = os.path.join(base_dir, name)
        polished_audio_path = os.path.join(output_dir, name)

        # CRITICAL: Delete pre-existing output file to prevent Audacity "Confirm Overwrite" dialogs
        if os.path.exists(polished_audio_path):
            try:
                os.remove(polished_audio_path)
            except Exception:
                pass

        # Force close any existing instance first
        try:
            subprocess.run(["taskkill", "/F", "/IM", "Audacity.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
        except Exception:
            pass

        # Clear any leftover crash session locks before starting Audacity
        clear_audacity_temp_data()

        if base_dir == latest_run:
            print(f"\nProcessing Master Track: {name}...")
        else:
            print(f"\nProcessing Chapter {idx}: {name}...")

        # Launch fresh Audacity instance
        print("  Launching fresh Audacity instance...")
        subprocess.Popen([executable_path])

        # Dynamically poll and connect to named pipes (max 10 seconds)
        write_pipe, read_pipe = None, None
        for attempt in range(20):
            try:
                write_pipe = open(r'\\.\pipe\ToSrvPipe', 'w', encoding='utf-8')
                read_pipe = open(r'\\.\pipe\FromSrvPipe', 'r', encoding='utf-8')
                break
            except Exception:
                time.sleep(0.5)

        if not write_pipe or not read_pipe:
            print("  Error: Could not connect to Audacity Named Pipes. Retrying...")
            continue

        # Wait for Audacity's main GUI window to fully draw and initialize
        print("  Waiting for Audacity GUI to initialize...")
        time.sleep(2.5)

        # Format paths for Windows Audacity API compatibility
        clean_import_path = os.path.abspath(raw_audio_path).replace("\\", "\\\\")
        clean_export_path = os.path.abspath(polished_audio_path).replace("\\", "\\\\")
            
        # Send API commands to Audacity (No spaces after colons)
        send_audacity_command(write_pipe, read_pipe, f'Import2:Filename="{clean_import_path}"')
        send_audacity_command(write_pipe, read_pipe, 'SelectAll:')
        send_audacity_command(write_pipe, read_pipe, 'Macro_Achird Gemini Voice cut and enhance:')
        
        # Explicitly export the processed track directly to our new folder
        send_audacity_command(write_pipe, read_pipe, 'SelectAll:')
        send_audacity_command(write_pipe, read_pipe, f'Export2:Filename="{clean_export_path}" NumChannels=1')
        
        # Monitor the filesystem for the completed output file
        print(f"  Waiting for Audacity to finish processing and save to {output_dir}...")
        while not os.path.exists(polished_audio_path):
            time.sleep(0.5)
            
        # Ensure file write stream is complete (byte stabilization check)
        last_size = -1
        while True:
            try:
                current_size = os.path.getsize(polished_audio_path)
                if current_size > 0 and current_size == last_size:
                    break
                last_size = current_size
            except Exception: 
                pass
            time.sleep(0.5)
        
        print("  Polished file successfully exported!")
        
        # Close named pipes cleanly before terminating process
        try:
            write_pipe.close()
            read_pipe.close()
        except Exception:
            pass

        # Force terminate Audacity to flush all memory leak buffer, lock files and undo history
        print("  Safely closing Audacity instance...")
        try:
            subprocess.run(["taskkill", "/F", "/IM", "Audacity.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.0)  # Wait for locks to fully release
        except Exception:
            pass

        # Save successful execution progress to checkpoint file
        polished_files.append(name)
        save_checkpoint(latest_run, polished_files)

    # 5. Graceful Teardown
    print("\n[SYSTEM] Polishing complete.")
    delete_checkpoint(latest_run)

    print("=============================================")
    print("Success! All target audio assets have been polished.")
    print("=============================================")


if __name__ == "__main__":
    main()