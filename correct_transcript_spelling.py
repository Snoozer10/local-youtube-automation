import os
import re
import sys
import difflib

print("DEBUG: [Checkpoint 1] Imports completed successfully.", flush=True)


def get_target_directory():
    print("DEBUG: [Checkpoint 4] Entering get_target_directory().", flush=True)
    base_runs_dir = "youtube_runs"

    # Option 1: Command line argument check
    if len(sys.argv) > 1:
        target_name = sys.argv[1]
        print(f"DEBUG: Argument passed: '{target_name}'", flush=True)
        if os.path.exists(target_name):
            return target_name
        runs_subdir = os.path.join(base_runs_dir, target_name)
        if os.path.exists(runs_subdir):
            return runs_subdir
        print(f"Error: Specified directory '{target_name}' not found.")
        sys.exit(1)

    # Option 2: Scan youtube_runs
    print(f"DEBUG: Checking if base dir '{base_runs_dir}' exists...", flush=True)
    if os.path.exists(base_runs_dir) and os.path.isdir(base_runs_dir):
        print(f"DEBUG: '{base_runs_dir}' exists. Listing subdirectories...", flush=True)
        subdirs = [
            os.path.join(base_runs_dir, d)
            for d in os.listdir(base_runs_dir)
            if os.path.isdir(os.path.join(base_runs_dir, d))
        ]
        print(f"DEBUG: Found subdirectories: {subdirs}", flush=True)
        if subdirs:
            subdirs.sort(key=os.path.getmtime, reverse=True)
            latest_dir = subdirs[0]
            print(f"DEBUG: Sorted subdirs. Selecting latest: '{latest_dir}'", flush=True)
            return latest_dir

    print("DEBUG: Falls back to current directory.", flush=True)
    return "."

def align_and_correct_file(file_path, ref_words, file_type):
    """
    Aligns and spelling-corrects a target file against the reference words list.
    Supports 'txt' (timestamped timelines) and 'srt' (standard subtitle files) formats.
    """
    # Force UTF-8-sig reading for SRT compatibility
    encoding_mode = "utf-8-sig" if file_type == "srt" else "utf-8"
    with open(file_path, "r", encoding=encoding_mode) as f:
        lines = f.readlines()

    trans_words = [] # List of (word, group_idx)
    
    if file_type == "txt":
        line_timestamps = []
        for idx, line in enumerate(lines):
            line = line.strip()
            if not line:
                line_timestamps.append("")
                continue
            match = re.match(r"^(\[[0-9:\s\-]+\])\s*(.*)$", line)
            if match:
                timestamp = match.group(1)
                text = match.group(2)
            else:
                timestamp = ""
                text = line
            line_timestamps.append(timestamp)
            words = text.split()
            for w in words:
                trans_words.append((w, idx))
        original_group_count = len(lines)
        
    elif file_type == "srt":
        srt_headers = [] # List of (idx_str, time_str)
        blocks = []
        current_block = []
        for line in lines:
            if line.strip() == "":
                if current_block:
                    blocks.append(current_block)
                    current_block = []
            else:
                current_block.append(line.strip())
        if current_block:
            blocks.append(current_block)
            
        for block_idx, block in enumerate(blocks):
            if len(block) >= 2:
                idx_str = block[0]
                time_str = block[1]
                text_lines = block[2:]
                srt_headers.append((idx_str, time_str))
                full_text = " ".join(text_lines)
                words = full_text.split()
                for w in words:
                    trans_words.append((w, block_idx))
            else:
                srt_headers.append((block[0] if block else "", ""))
        original_group_count = len(blocks)

    # Convert transcript words into sequence list for matching
    trans_words_seq = [tw[0] for tw in trans_words]
    matcher = difflib.SequenceMatcher(None, trans_words_seq, ref_words)
    
    # Store word structures for reconstruction
    corrected_groups_words = [[] for _ in range(original_group_count)]

    # Distribute matching sequences safely
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for offset in range(i2 - i1):
                word_idx = i1 + offset
                ref_word_idx = j1 + offset
                group_idx = trans_words[word_idx][1]
                corrected_groups_words[group_idx].append(ref_words[ref_word_idx])
                
        elif tag == 'replace':
            ref_words_sub = ref_words[j1:j2]
            group_indices = [trans_words[k][1] for k in range(i1, i2)]
            if len(group_indices) > 0 and len(ref_words_sub) > 0:
                for r_idx, r_word in enumerate(ref_words_sub):
                    mapped_pos = int((r_idx / len(ref_words_sub)) * len(group_indices))
                    group_idx = group_indices[mapped_pos]
                    corrected_groups_words[group_idx].append(r_word)
                    
        elif tag == 'insert':
            if i1 > 0:
                nearest_idx = trans_words[i1 - 1][1]
            elif i1 < len(trans_words):
                nearest_idx = trans_words[i1][1]
            else:
                nearest_idx = 0
            for ref_word in ref_words[j1:j2]:
                corrected_groups_words[nearest_idx].append(ref_word)
                
        elif tag == 'delete':
            pass

    # Reconstruct lines based on file type layouts
    new_lines = []
    if file_type == "txt":
        for idx, timestamp in enumerate(line_timestamps):
            group_words = corrected_groups_words[idx]
            if group_words:
                reconstructed_text = " ".join(group_words)
                new_lines.append(f"{timestamp} {reconstructed_text}\n")
            else:
                new_lines.append(f"{timestamp}\n" if timestamp else "\n")
                
    elif file_type == "srt":
        for idx, (idx_str, time_str) in enumerate(srt_headers):
            if not idx_str:
                continue
            group_words = corrected_groups_words[idx]
            reconstructed_text = " ".join(group_words)
            new_lines.append(f"{idx_str}\n")
            new_lines.append(f"{time_str}\n")
            new_lines.append(f"{reconstructed_text}\n\n")

    # Save output with appropriate encoding flags
    with open(file_path, "w", encoding=encoding_mode) as f:
        f.writelines(new_lines)

def correct_transcript():
    print("DEBUG: [Checkpoint 3] Entering correct_transcript().", flush=True)
    target_dir = get_target_directory()
    print(f"DEBUG: [Checkpoint 5] Target directory resolved to: '{target_dir}'", flush=True)
    
    # Prioritize refined_script.txt, fallback to final_output.txt
    ref_refined = os.path.join(target_dir, "refined_script.txt")
    ref_final = os.path.join(target_dir, "final_output.txt")

    if os.path.exists(ref_refined):
        ref_path = ref_refined
        print(f"[SYSTEM] Found refined script. Utilizing '{ref_refined}' as spelling reference.", flush=True)
    elif os.path.exists(ref_final):
        ref_path = ref_final
        print(f"[SYSTEM] Refined script not found. Falling back to final output script '{ref_final}' as spelling reference.", flush=True)
    else:
        print(f"Error: Neither 'refined_script.txt' nor 'final_output.txt' found in '{target_dir}'.", flush=True)
        return

    print("DEBUG: [Checkpoint 6] Target reference file exists. Reading contents...", flush=True)

    # 1. Read and tokenize reference text
    with open(ref_path, "r", encoding="utf-8") as f:
        ref_text = f.read().strip()
    ref_words = ref_text.split()
    print(f"DEBUG: Reference text loaded. Word count = {len(ref_words)}", flush=True)

    # 2. Pipeline sequence across all timeline outputs
    files_to_correct = [
        ("timestamped_transcript.txt", "txt"),
        ("timestamped_transcript.srt", "srt"),
        ("image_timestamps.txt", "txt"),
        ("subtitle_chunks.srt", "srt")
    ]

    for filename, f_type in files_to_correct:
        f_path = os.path.join(target_dir, filename)
        if os.path.exists(f_path):
            print(f"\nAligning and correcting spelling in: '{filename}'...", flush=True)
            try:
                align_and_correct_file(f_path, ref_words, f_type)
                print(f"Success! Overwrote and aligned '{filename}'.", flush=True)
            except Exception as e:
                print(f"Error aligning file '{filename}': {e}", flush=True)
        else:
            print(f"\nSkipping '{filename}' (File does not exist in target directory).", flush=True)

    print("\n=============================================")
    print("Success! Spelling correction alignment sequence completed.")
    print("=============================================")

if __name__ == "__main__":
    print("DEBUG: [Checkpoint 2] Entered main block.", flush=True)
    
    # Safely reconfigure consoles with replacements to avoid crash loops
    if sys.platform.startswith("win"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            print("DEBUG: Consoles reconfigured to UTF-8 safely.", flush=True)
        except Exception as e:
            print(f"DEBUG WARNING: Console reconfig failed: {e}", flush=True)

    try:
        correct_transcript()
    except Exception as err:
        import traceback
        # Cast the error to ASCII representation to guarantee safe terminal rendering
        safe_err_msg = str(err).encode("ascii", "replace").decode("ascii")
        print(f"\n[CRITICAL ERROR OCCURRED]: {safe_err_msg}", flush=True)
        traceback.print_exc()