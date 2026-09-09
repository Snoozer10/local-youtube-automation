"""Audacity automation client module.

Provides Win32 Named Pipes IPC (\\\\.\\pipe\\ToSrvPipe and \\\\.\\pipe\\FromSrvPipe),
macro preset synchronization, and automated batch audio polishing.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import wave

# Windows console hardening: guarantee UTF-8 for Arabic output even when piped.
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass


def get_latest_run_folder(runs_path="youtube_runs"):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    rel_to_script = os.path.join(script_dir, runs_path)
    resolved_path = rel_to_script if os.path.exists(rel_to_script) else runs_path
    if not os.path.exists(resolved_path):
        return None
    subdirs = [
        os.path.join(runs_path, d)
        for d in os.listdir(runs_path)
        if os.path.isdir(os.path.join(runs_path, d))
    ]
    if not subdirs:
        return None
    return max(subdirs, key=os.path.getmtime)


def send_audacity_command(write_pipe, read_pipe, command):
    """Sends a single scripting command to Audacity and waits for response.

    Audacity Named Pipe protocol:
    Audacity transmits arbitrary information lines (often starting with a leading newline
    when no textual output is produced), followed by 'BatchCommand finished: <status>',
    followed by a final empty line ('\\n') marking completion.
    """
    t0 = time.perf_counter()
    write_pipe.write(command + "\n")
    write_pipe.flush()

    response = ""
    saw_batch_finished = False
    while True:
        line = read_pipe.readline()
        if not line:  # Audacity crashed or closed pipe
            break
        response += line

        if "BatchCommand finished" in line:
            saw_batch_finished = True
        elif saw_batch_finished and line.strip() == "":
            break
        elif not saw_batch_finished and line.strip() == "":
            # Handle mock test harness without BatchCommand framing
            if hasattr(read_pipe, "has_pending"):
                if not read_pipe.has_pending() or response.strip():
                    break

    latency_ms = (time.perf_counter() - t0) * 1000
    cleaned_response = response.strip().replace("\n", " | ")
    status_tag = "OK" if ("OK" in cleaned_response or "BatchCommand finished: OK" in cleaned_response) else "INFO"
    if "failed" in cleaned_response.lower() or "error" in cleaned_response.lower():
        status_tag = "WARN"
    print(f"  [PIPE {status_tag} ({latency_ms:5.1f}ms)] {command} -> {cleaned_response}", flush=True)
    return response


def find_preset_file():
    """Locates the preset text file in the workspace."""
    candidates = [
        "YouTube_Voice_Optimizer.txt.txt",
        "YouTube_Voice_Optimizer.txt",
        "YouTube_Voice_Optimizer",
    ]
    for filename in candidates:
        if os.path.exists(filename):
            return filename
    return None


def sync_macro_to_audacity(preset_path):
    """Copies the preset file into Audacity's AppData Macros folder before launch."""
    if not preset_path or not os.path.exists(preset_path):
        return

    appdata = os.getenv("APPDATA")
    if not appdata:
        return

    macros_dir = os.path.join(appdata, "audacity", "macros")
    os.makedirs(macros_dir, exist_ok=True)

    # Copy under both possible names so Audacity GUI always registers it
    try:
        shutil.copy(preset_path, os.path.join(macros_dir, "YouTube_Voice_Optimizer.txt"))
        shutil.copy(
            preset_path, os.path.join(macros_dir, "Achird Gemini Voice cut and enhance.txt")
        )
        print(f"[SYSTEM] Synced preset settings to Audacity Macros folder: {macros_dir}")
    except Exception as e:
        print(f"[WARNING] Could not sync macro file to AppData: {e}")


def apply_preset_file(write_pipe, read_pipe, preset_path):
    """Reads effect settings line-by-line from the preset file and executes them via pipe."""
    if not preset_path or not os.path.exists(preset_path):
        return False

    print(f"  Applying preset settings directly from '{preset_path}'...")
    with open(preset_path, encoding="utf-8") as f:
        lines = f.readlines()

    executed_count = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Skip export commands inside preset file (export is handled explicitly by python)
        if line.startswith("Export") or line.startswith("ExportWav"):
            continue

        # Select all audio before applying each effect (avoid duplicate SelectAll)
        if not line.startswith("SelectAll"):
            send_audacity_command(write_pipe, read_pipe, "SelectAll:")

        # Ensure correct formatting (e.g. "NoiseGate:attack=..." instead of "NoiseGate: attack=...")
        if ":" in line:
            cmd_name, cmd_args = line.split(":", 1)
            formatted_cmd = f"{cmd_name.strip()}:{cmd_args.strip()}"
        else:
            formatted_cmd = line.strip()

        send_audacity_command(write_pipe, read_pipe, formatted_cmd)
        executed_count += 1
        time.sleep(0.2)

    return executed_count > 0


def load_checkpoint(folder):
    path = os.path.join(folder, "audacity_checkpoint.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("polished_files", [])
        except Exception as e:
            print(f"[WARNING] Ignoring unreadable audacity_checkpoint.json: {e}")
    return []


def save_checkpoint(folder, polished_files):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "audacity_checkpoint.json")
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"polished_files": polished_files}, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def delete_checkpoint(folder):
    path = os.path.join(folder, "audacity_checkpoint.json")
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError as e:
            print(f"[WARNING] Could not delete audacity_checkpoint.json: {e}")


def ensure_audacity_script_pipe_enabled():
    """Forces mod-script-pipe=1 in Audacity configuration file."""
    appdata = os.getenv("APPDATA")
    if not appdata:
        return
    cfg_path = os.path.join(appdata, "audacity", "audacity.cfg")
    try:
        content = ""
        if os.path.exists(cfg_path):
            with open(cfg_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()

        if "mod-script-pipe=1" not in content:
            print("[SYSTEM] Auto-enabling 'mod-script-pipe' in Audacity configuration...")
            if "[Modules]" in content:
                content = content.replace("[Modules]", "[Modules]\nmod-script-pipe=1")
            else:
                content += "\n[Modules]\nmod-script-pipe=1\n"

            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(content)
    except Exception as e:
        print(f"[WARNING] Could not update audacity.cfg: {e}")


def clear_audacity_temp_data():
    """Wipes Audacity's temporary SessionData and AutoSave folders to prevent recovery popups."""
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        session_data_dir = os.path.join(local_appdata, "Audacity", "SessionData")
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

    roaming_appdata = os.getenv("APPDATA")
    if roaming_appdata:
        autosave_dir = os.path.join(roaming_appdata, "audacity", "AutoSave")
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


def probe_audio_file(file_path):
    """Extracts exact physical duration and audio format parameters via wave header inspection.

    Returns dict with keys: duration, framerate, channels, sampwidth, nframes, or None on error.
    """
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        with wave.open(file_path, "rb") as wf:
            framerate = wf.getframerate()
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            nframes = wf.getnframes()
            if framerate <= 0 or nframes < 0:
                return None
            duration = round(nframes / float(framerate), 3)
            return {
                "duration": duration,
                "framerate": framerate,
                "channels": nchannels,
                "sampwidth": sampwidth,
                "nframes": nframes,
            }
    except Exception:
        return None


def sync_polished_audio_manifest(latest_run, silence_padding_sec=0.300):
    """Synchronizes post-mastered audio durations and paths from polished_chapters into audio manifests.

    Ensures audio_manifest.json and voice_generation_manifest.json reflect exact physical
    durations after DSP processing (e.g. TruncateSilence), preserving downstream video sync.
    """
    if not latest_run or not os.path.exists(latest_run):
        return

    polished_dir = os.path.join(latest_run, "polished_chapters")
    if not os.path.exists(polished_dir):
        return

    audio_manifest_path = os.path.join(latest_run, "audio_manifest.json")
    voice_manifest_path = os.path.join(latest_run, "voice_generation_manifest.json")

    # 1. Update audio_manifest.json if present
    if os.path.exists(audio_manifest_path):
        try:
            with open(audio_manifest_path, encoding="utf-8") as f:
                data = json.load(f)

            padding = float(data.get("silence_padding_sec", silence_padding_sec))
            current_time = 0.0
            segments = data.get("segments", [])
            updated_count = 0

            for seg in segments:
                base_name = os.path.basename(seg.get("audio_file", ""))
                if not base_name:
                    seg_idx = seg.get("index", 1)
                    base_name = f"Chapter_{seg_idx}.wav"

                polished_path = os.path.join(polished_dir, base_name)
                probe = probe_audio_file(polished_path) if os.path.exists(polished_path) else None

                if probe:
                    duration = probe["duration"]
                    seg["audio_file"] = f"polished_chapters/{base_name}"
                    seg["duration"] = duration
                    updated_count += 1
                else:
                    duration = float(seg.get("duration", 0.0))

                start_time = round(current_time, 3)
                end_time = round(start_time + duration, 3)
                seg["start_time"] = start_time
                seg["end_time"] = end_time

                if seg.get("status") == "COMPLETED" and duration > 0:
                    current_time = end_time + padding
                else:
                    current_time = end_time

            data["cumulative_duration_sec"] = round(current_time, 3)

            # Atomic write
            tmp_path = audio_manifest_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, audio_manifest_path)
            print(
                f"[MANIFEST SYNC] Updated audio_manifest.json: {updated_count}/{len(segments)} segments "
                f"re-timed from polished_chapters (cumulative duration: {data['cumulative_duration_sec']}s)"
            )
        except Exception as e:
            print(f"[MANIFEST WARNING] Failed to sync audio_manifest.json with polished audio: {e}")

    # 2. Update voice_generation_manifest.json if present
    if os.path.exists(voice_manifest_path):
        try:
            with open(voice_manifest_path, encoding="utf-8") as f:
                vdata = json.load(f)

            chapters = vdata.get("chapters", [])
            for chap in chapters:
                chap_num = chap.get("chapter_num", chap.get("index", 1))
                base_name = f"Chapter_{chap_num}.wav"
                polished_path = os.path.join(polished_dir, base_name)
                probe = probe_audio_file(polished_path) if os.path.exists(polished_path) else None
                if probe:
                    chap["audio_file"] = f"polished_chapters/{base_name}"
                    chap["duration"] = probe["duration"]
                    chap["sample_rate"] = probe["framerate"]
                    chap["channels"] = probe["channels"]
                    chap["bit_depth"] = probe["sampwidth"] * 8

            tmp_path = voice_manifest_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(vdata, f, ensure_ascii=False, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, voice_manifest_path)
            print("[MANIFEST SYNC] Synchronized voice_generation_manifest.json with polished audio.")
        except Exception as e:
            print(f"[MANIFEST WARNING] Failed to sync voice_generation_manifest.json: {e}")


def main():
    print("=============================================")
    print("Starting Autonomous Audacity Audio Polishing")
    print("=============================================")

    # Force kill any existing Audacity processes
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "Audacity.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1.0)
    except Exception as e:
        print(f"[WARNING] Audacity taskkill failed (may not be running): {e}")

    # Wipe leftover crash files
    clear_audacity_temp_data()
    ensure_audacity_script_pipe_enabled()  # <--- CALL IT HERE

    # Find and sync preset file
    preset_file_path = find_preset_file()
    if preset_file_path:
        print(f"[SYSTEM] Found preset file: '{preset_file_path}'")
        sync_macro_to_audacity(preset_file_path)
    else:
        print("[WARNING] No preset file found! Audacity will rely on default internal macros.")

    # 1. Locate Run Folder
    latest_run = get_latest_run_folder()
    if not latest_run:
        print("Error: No active run folder detected.")
        sys.exit(1)

    print(f"Target Video Folder: {latest_run}")

    # 2. Determine Processing Target
    master_track_path = os.path.join(latest_run, "full_episode_voice.wav")
    files_to_process = []

    if os.path.exists(master_track_path):
        print("[SYSTEM] Found 'full_episode_voice.wav'. Targeting the master voice track only.")
        output_dir = os.path.join(latest_run, "audacity_voice")
        files_to_process.append((0, "full_episode_voice.wav", latest_run, output_dir))
    else:
        print("[SYSTEM] Master voice track not found. Scanning 'voice_chapters' subfolder...")
        chapters_dir = os.path.join(latest_run, "voice_chapters")

        if not os.path.exists(chapters_dir):
            print(
                f"Error: Neither 'full_episode_voice.wav' nor the 'voice_chapters' folder exists in '{latest_run}'."
            )
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

        print(
            f"Found {len(chapter_files)} chapters to polish inside the 'voice_chapters' directory."
        )
        files_to_process = chapter_files

    # Load checkpoint progress
    polished_files = load_checkpoint(latest_run)
    if polished_files:
        print(
            f"[CHECKPOINT] Resuming. Already polished {len(polished_files)} of {len(files_to_process)} files."
        )

    # 3. Find Audacity Executable Path
    audacity_paths = [
        r"C:\Program Files\Audacity\Audacity.exe",
        r"C:\Program Files (x86)\Audacity\Audacity.exe",
    ]
    executable_path = next((p for p in audacity_paths if os.path.exists(p)), None)
    if not executable_path:
        print("Error: Audacity.exe not found in standard Windows paths.")
        sys.exit(1)

    # 4. Polish target audio files sequentially (Single Persistent Session)
    EXPORT_WAIT_TIMEOUT_SEC = 900

    def launch_audacity_session():
        clear_audacity_temp_data()
        print("  Launching Audacity instance...")
        subprocess.Popen([executable_path])
        time.sleep(3.0)

        w_pipe, r_pipe = None, None
        for _attempt in range(30):
            try:
                w_pipe = open(r"\\.\pipe\ToSrvPipe", "w", encoding="utf-8")
                r_pipe = open(r"\\.\pipe\FromSrvPipe", encoding="utf-8")
                break
            except Exception:
                time.sleep(0.5)

        if not w_pipe or not r_pipe:
            raise ConnectionError("Could not connect to Audacity Named Pipes!")
        print("  Audacity Named Pipes connected successfully.")
        # Pre-flight handshake to ensure Audacity GUI and scripting thread are actively responding
        print("  Executing initial handshake...")
        send_audacity_command(w_pipe, r_pipe, "Help: Command=Help")
        send_audacity_command(w_pipe, r_pipe, "SelectAll:")
        print("  Audacity session handshake complete and responsive.")
        return w_pipe, r_pipe

    def terminate_audacity_session(w_pipe, r_pipe):
        # Kill process FIRST so FromSrvPipe EOFs and unblocks any reading thread/call without Windows CRT file-lock deadlock
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "Audacity.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
        except Exception:
            pass
        try:
            if w_pipe:
                w_pipe.close()
        except Exception:
            pass
        try:
            if r_pipe:
                r_pipe.close()
        except Exception:
            pass
        clear_audacity_temp_data()

    write_pipe, read_pipe = None, None
    try:
        write_pipe, read_pipe = launch_audacity_session()
    except Exception as e:
        print(f"[ERROR] Failed to start Audacity session: {e}")
        sys.exit(1)

    try:
        for idx, name, base_dir, output_dir in files_to_process:
            if name in polished_files:
                print(f"Skipping already polished file: {name}")
                continue

            os.makedirs(output_dir, exist_ok=True)
            raw_audio_path = os.path.join(base_dir, name)
            polished_audio_path = os.path.join(output_dir, name)

            if os.path.exists(polished_audio_path):
                try:
                    os.remove(polished_audio_path)
                except Exception:
                    pass

            if base_dir == latest_run:
                print(f"\nProcessing Master Track: {name}...")
            else:
                print(f"\nProcessing Chapter {idx}: {name}...")

            clean_import_path = os.path.abspath(raw_audio_path).replace("\\", "\\\\")
            clean_export_path = os.path.abspath(polished_audio_path).replace("\\", "\\\\")

            try:
                # 1. Import raw audio
                send_audacity_command(write_pipe, read_pipe, f'Import2:Filename="{clean_import_path}"')

                # 2. Apply preset settings (NoiseGate, TruncateSilence, BassAndTreble, Compressor, Normalize)
                preset_success = apply_preset_file(write_pipe, read_pipe, preset_file_path)

                # Fallback if preset file was missing
                if not preset_success:
                    print("  Falling back to internal macro command...")
                    send_audacity_command(write_pipe, read_pipe, "SelectAll:")
                    send_audacity_command(write_pipe, read_pipe, "Macro_YouTube_Voice_Optimizer:")

                # 3. Export polished track
                send_audacity_command(write_pipe, read_pipe, "SelectAll:")
                send_audacity_command(
                    write_pipe, read_pipe, f'Export2:Filename="{clean_export_path}" NumChannels=1'
                )

                # 4. Wait for exported file to complete
                print(f"  Waiting for Audacity to finish processing and save to {output_dir}...")
                wait_start = time.time()
                while not os.path.exists(polished_audio_path):
                    if time.time() - wait_start > EXPORT_WAIT_TIMEOUT_SEC:
                        raise TimeoutError(
                            f"Export never produced '{name}' within {EXPORT_WAIT_TIMEOUT_SEC}s"
                        )
                    time.sleep(0.5)

                last_size = -1
                size_stable_since = time.time()
                while True:
                    try:
                        current_size = os.path.getsize(polished_audio_path)
                        if current_size > 0 and current_size == last_size:
                            break
                        if current_size != last_size:
                            last_size = current_size
                            size_stable_since = time.time()
                        elif time.time() - size_stable_since > EXPORT_WAIT_TIMEOUT_SEC:
                            raise TimeoutError(
                                f"'{name}' size never stabilized within {EXPORT_WAIT_TIMEOUT_SEC}s"
                            )
                    except OSError:
                        pass
                    time.sleep(0.5)

                print("  Polished file successfully exported!")

                # --- OUTPUT SYNC SAFEGUARD ---
                if name == "full_episode_voice.wav" and os.path.exists(polished_audio_path):
                    try:
                        shutil.copy(polished_audio_path, master_track_path)
                        print(
                            f"  [SYNC] Synchronized polished voice track to root: '{master_track_path}'"
                        )
                    except Exception as e:
                        print(f"  [WARNING] Sync copy failed: {e}")

                polished_files.append(name)
                save_checkpoint(latest_run, polished_files)

                # 5. Clear tracks canvas cleanly for the next chapter
                send_audacity_command(write_pipe, read_pipe, "SelectAll:")
                send_audacity_command(write_pipe, read_pipe, "RemoveTracks:")

            except TimeoutError as te:
                print(f"  [TIMEOUT] {te}")
                print(f"  Skipping '{name}' — it will be retried on the next pipeline resume.")
            except Exception as e:
                print(f"  [ERROR] Processing failed for '{name}': {e}")
                print("  Recovering Audacity session for subsequent chapters...")
                terminate_audacity_session(write_pipe, read_pipe)
                try:
                    write_pipe, read_pipe = launch_audacity_session()
                except Exception as rec_err:
                    print(f"  [FATAL] Could not recover Audacity session: {rec_err}")
                    break
    finally:
        print("  Safely closing Audacity instance...")
        terminate_audacity_session(write_pipe, read_pipe)

    print("\n[SYSTEM] Polishing complete.")
    delete_checkpoint(latest_run)

    # Synchronize post-mastered durations to manifests
    try:
        sync_polished_audio_manifest(latest_run)
    except Exception as e:
        print(f"  [WARNING] Could not synchronize polished audio manifest: {e}")

    print("=============================================")
    print("Success! All target audio assets have been polished.")
    print("=============================================")


__all__ = [
    "apply_preset_file",
    "clear_audacity_temp_data",
    "delete_checkpoint",
    "ensure_audacity_script_pipe_enabled",
    "find_preset_file",
    "get_latest_run_folder",
    "load_checkpoint",
    "main",
    "probe_audio_file",
    "save_checkpoint",
    "send_audacity_command",
    "sync_macro_to_audacity",
    "sync_polished_audio_manifest",
]


if __name__ == "__main__":
    main()
