import os
import re
import json

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
        with open(script_path, "r", encoding="utf-8") as f:
            idx = 1
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                    
                # Standard format [MM:SS]
                match = re.match(r"^\[(\d{2}:\d{2})\]", line_str)
                if match:
                    timestamps_map[idx] = f"[{match.group(1)}]"
                else:
                    # Fallback for [HH:MM:SS]
                    match_long = re.match(r"^\[(\d{2}:\d{2}:\d{2})\]", line_str)
                    if match_long:
                        time_parts = match_long.group(1).split(":")
                        timestamps_map[idx] = f"[{time_parts[1]}:{time_parts[2]}]"
                    else:
                        timestamps_map[idx] = "[00:00]"
                idx += 1

        print(f"  -> Mapped {len(timestamps_map)} timestamps from transcript.")

        # 2. Extract and Parse the messy JSON chunks
        with open(json_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Find all JSON arrays in the file using Regex
        json_blocks = re.findall(r'\[\s*\{.*?\}\s*\]', content, re.DOTALL)
        
        master_list = []
        injected_count = 0

        for block in json_blocks:
            try:
                data = json.loads(block)
                for item_obj in data:
                    item_idx = int(item_obj.get("index", 0))
                    
                    # INJECT THE TIMESTAMP
                    if item_idx in timestamps_map:
                        item_obj["timestamp"] = timestamps_map[item_idx]
                        injected_count += 1
                        
                    master_list.append(item_obj)
            except json.JSONDecodeError as e:
                print(f"  -> Warning: Failed to parse a JSON chunk: {e}")

        # 3. Save as a single, beautiful, valid JSON file
        if master_list:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(master_list, f, indent=2, ensure_ascii=False)
            print(f"  -> ✅ Success! Injected {injected_count} timestamps.")
            print(f"  -> ✅ Cleaned JSON file structure.")
        else:
            print("  -> ⚠️ No valid JSON objects found to process.")
            
        folders_processed += 1

    print("\n==================================================")
    print(f"Finished processing {folders_processed} topic folders.")
    print("==================================================")

if __name__ == "__main__":
    main()