import json
import os
import re

# Windows console hardening: guarantee UTF-8 for Arabic output even when piped.
import sys

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main():
    print("==================================================")
    print("Running JSON Timestamp Injector & Cleaner")
    print("==================================================")

    runs_dir = "youtube_runs"
    if not os.path.exists(runs_dir):
        print(f"Error: Directory '{runs_dir}' not found.")
        return

    folders_processed = 0

    for item in os.listdir(runs_dir):
        subfolder = os.path.join(runs_dir, item)
        if not os.path.isdir(subfolder):
            continue

        script_path = os.path.join(subfolder, "timestamped_transcript.txt")
        json_path = os.path.join(subfolder, "flow_prompts.json")

        if not os.path.exists(script_path) or not os.path.exists(json_path):
            continue

        print(f"\nProcessing Folder: {item}")

        # 1. Map Indexes to Timestamps from the Transcript
        timestamps_map = {}
        with open(script_path, encoding="utf-8-sig") as f:
            idx = 1
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue

                # Standard format [MM:SS]
                match = re.match(r"^\[(\d{1,2}:\d{2})\]", line_str)
                if match:
                    timestamps_map[idx] = f"[{match.group(1)}]"
                else:
                    # Fallback for [HH:MM:SS] — fold hours into minutes so the
                    # downstream [MM:SS] contract stays consistent.
                    match_long = re.match(r"^\[(\d{1,2}):(\d{2}):(\d{2})\]", line_str)
                    if match_long:
                        total_min = int(match_long.group(1)) * 60 + int(match_long.group(2))
                        timestamps_map[idx] = f"[{total_min:02d}:{match_long.group(3)}]"
                    else:
                        timestamps_map[idx] = "[00:00]"
                idx += 1

        print(f"  -> Mapped {len(timestamps_map)} timestamps from transcript.")

        # 2. Extract and Parse the messy JSON chunks.
        # Incremental raw_decode scanning tolerates nested arrays, trailing
        # commas, and prose headers — the old single-regex splitter truncated
        # on the first nested "]}" and silently dropped those chunks.
        with open(json_path, encoding="utf-8-sig") as f:
            content = f.read()

        decoder = json.JSONDecoder()
        parsed_arrays = []
        scan_pos = 0
        while True:
            arr_start = content.find("[", scan_pos)
            if arr_start == -1:
                break
            try:
                obj, end_pos = decoder.raw_decode(content, arr_start)
                if isinstance(obj, list):
                    parsed_arrays.extend(o for o in obj if isinstance(o, dict))
                elif isinstance(obj, dict):
                    parsed_arrays.append(obj)
                scan_pos = end_pos
            except ValueError:
                scan_pos = arr_start + 1

        master_list = []
        injected_count = 0
        failed_blocks = 0

        for item_obj in parsed_arrays:
            try:
                item_idx = int(item_obj.get("index", 0))

                # INJECT THE TIMESTAMP
                if item_idx in timestamps_map:
                    item_obj["timestamp"] = timestamps_map[item_idx]
                    injected_count += 1

                master_list.append(item_obj)
            except (TypeError, ValueError) as e:
                failed_blocks += 1
                print(f"  -> Warning: Failed to process a prompt object: {e}")

        # 3. Save atomically — and NEVER overwrite the source file with partial
        # data (a mid-parse crash previously destroyed flow_prompts.json).
        if master_list:
            tmp_path = json_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(master_list, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, json_path)
            print(f"  -> ✅ Success! Injected {injected_count} timestamps.")
            print("  -> ✅ Cleaned JSON file structure.")
        else:
            print("  -> ⚠️ No valid JSON objects found to process.")

        folders_processed += 1

    print("\n==================================================")
    print(f"Finished processing {folders_processed} topic folders.")
    print("==================================================")


if __name__ == "__main__":
    main()
