import os
import re
import sys
import wave

# Windows console hardening: guarantee UTF-8 for Arabic output even when piped.
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


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


def scan_sequential_chapters(chapters_source_dir, start_index=1):
    """Scans for Chapter_X.wav files and identifies genuine gaps between 1 and the max index.

    found contains only the contiguous prefix before the first absent index.
    missing lists every absent Chapter_X.wav within the scan window. Present
    files beyond the first gap are excluded from found and reported once via
    a single [WARN] line.

    Returns:
        tuple(list, list): (found_paths, missing_names)
    """
    if not os.path.exists(chapters_source_dir):
        return [], []

    # Find all Chapter_*.wav files in the target folder
    present_indices = {}
    for fname in os.listdir(chapters_source_dir):
        match = re.match(r"^Chapter_(\d+)\.wav$", fname, re.IGNORECASE)
        if match:
            idx = int(match.group(1))
            present_indices[idx] = os.path.join(chapters_source_dir, fname)

    if not present_indices:
        return [], []

    max_idx = max(present_indices.keys())
    file_list = []
    missing = []
    orphan_names = []
    gap_found = False

    for i in range(start_index, max_idx + 1):
        if i in present_indices:
            if gap_found:
                orphan_names.append(f"Chapter_{i}.wav")
            else:
                file_list.append(present_indices[i])
        else:
            missing.append(f"Chapter_{i}.wav")
            gap_found = True

    if orphan_names:
        print(
            f"[WARN] {len(orphan_names)} orphan chapter(s) beyond gap ignored:"
            f" {', '.join(orphan_names)}"
        )

    return file_list, missing


def stitch_files(file_list, output_path):
    """Stitches WAV chapters frame-exactly with strict format homogeneity.

    Raises:
        ValueError: when any chapter's sample rate, channel count, or sample
        width differs from the first chapter (blind frame concatenation of
        mismatched formats produces pitch-corrupted audio).
    """
    if not file_list:
        raise ValueError("No chapter files supplied to stitch.")

    with wave.open(file_list[0], "rb") as first_file:
        params = first_file.getparams()
    ref = (params.framerate, params.nchannels, params.sampwidth)

    for path in file_list[1:]:
        with wave.open(path, "rb") as probe:
            cur = (probe.getframerate(), probe.getnchannels(), probe.getsampwidth())
        if cur != ref:
            raise ValueError(
                f"Chapter format mismatch in '{os.path.basename(path)}': "
                f"{cur} != reference {ref} (rate, channels, width)."
            )

    with wave.open(output_path, "wb") as output_file:
        output_file.setparams(params)
        for path in file_list:
            with wave.open(path, "rb") as input_file:
                # Write frames from each chapter directly — zero frames added or dropped.
                output_file.writeframes(input_file.readframes(input_file.getnframes()))
    return output_path


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
        print(
            "[SYSTEM] Found polished chapters. Utilizing 'polished_chapters' as the audio source."
        )
    elif os.path.exists(voice_dir) and os.path.exists(os.path.join(voice_dir, "Chapter_1.wav")):
        chapters_source_dir = voice_dir
        print(
            "[SYSTEM] Polished chapters not found. Falling back to raw 'voice_chapters' as the audio source."
        )
    else:
        print(
            f"Error: Could not find sequential Chapter_*.wav files in either:\n - '{polished_dir}'\n - '{voice_dir}'"
        )
        sys.exit(1)

    # 3. Scan for numerically sequential Chapter_X.wav files starting at 1
    file_list, missing = scan_sequential_chapters(chapters_source_dir)
    if missing:
        print(
            f"[ERROR] Sequence gap detected: {', '.join(missing)} is/are missing "
            f"before the last present chapter. Refusing to stitch a truncated episode."
        )
        sys.exit(1)

    print(f"Detected {len(file_list)} sequential voice chapters to stitch.")
    output_path = os.path.join(latest_run, "full_episode_voice.wav")

    # 4. Stitch Wave files seamlessly without silence gap
    try:
        print("Stitching chapters cleanly...")
        for path in file_list:
            print(f" - Appending: '{os.path.basename(path)}'")
        stitch_files(file_list, output_path)

        print("=============================================")
        print("Success! Master audio track updated cleanly.")
        print(f"Output File: '{output_path}'")
        print("=============================================")

    except ValueError as e:
        print(f"Error stitching audio tracks: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
