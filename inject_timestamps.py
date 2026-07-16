import os
import re
import sys
import glob

def get_latest_run_folder(runs_path="youtube_runs"):
    """Locates the newest subdirectory inside the youtube_runs directory."""
    if not os.path.exists(runs_path):
        return None
    folders = glob.glob(os.path.join(runs_path, "*"))
    folders = [f for f in folders if os.path.isdir(f)]
    if not folders:
        return None
    return max(folders, key=os.path.getmtime)

def parse_srt_timestamps(srt_path):
    """Parses SRT file and maps subtitle index integers to duration strings."""
    timestamps = {}
    if not os.path.exists(srt_path):
        return timestamps
    
    with open(srt_path, "r", encoding="utf-8-sig") as f:
        content = f.read()
        
    # Split content by double newlines to process independent blocks
    blocks = [b.strip().split('\n') for b in content.split('\n\n') if b.strip()]
    for block in blocks:
        if len(block) >= 2:
            try:
                idx = int(block[0].strip())
                time_range = block[1].strip()
                if "-->" in time_range:
                    timestamps[idx] = time_range
            except ValueError:
                pass
    return timestamps

def inject_timestamps():
    print("=============================================")
    print("Starting Automated Prompt Timestamp Injection")
    print("=============================================")

    # 1. Resolve latest run target folder
    latest_run = get_latest_run_folder()
    if not latest_run:
        print("Error: No active run folders found in 'youtube_runs/'.")
        sys.exit(1)
        
    print(f"Target Video Folder: '{latest_run}'")
    
    srt_path = os.path.join(latest_run, "timestamped_transcript.srt")
    prompts_path = os.path.join(latest_run, "pre_planned_prompts.txt")
    
    if not os.path.exists(srt_path) or not os.path.exists(prompts_path):
        print("Error: Missing required files in target folder:")
        print(f"  - Looking for: '{srt_path}' (exists: {os.path.exists(srt_path)})")
        print(f"  - Looking for: '{prompts_path}' (exists: {os.path.exists(prompts_path)})")
        sys.exit(1)
        
    # 2. Extract timestamps
    srt_timestamps = parse_srt_timestamps(srt_path)
    print(f"Parsed {len(srt_timestamps)} timestamp keys from SRT.")
    
    # 3. Read pre-planned prompts file
    with open(prompts_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    lines = content.split('\n')
    new_lines = []
    current_idx = None
    injected_count = 0
    
    # 4. Inject matching timestamps via a state-machine scan
    for line in lines:
        # Match "Index: <number>"
        match_idx = re.match(r"^Index:\s*(\d+)", line)
        if match_idx:
            current_idx = int(match_idx.group(1))
            new_lines.append(line)
            continue
            
        # Match "Calculated Timestamp:" line
        if line.strip().startswith("Calculated Timestamp:"):
            if current_idx in srt_timestamps:
                new_lines.append(f"Calculated Timestamp: {srt_timestamps[current_idx]}")
                injected_count += 1
            else:
                new_lines.append("Calculated Timestamp:")
            continue
            
        new_lines.append(line)
        
    # 5. Overwrite file with updated contents
    with open(prompts_path, "w", encoding="utf-8") as f:
        f.write('\n'.join(new_lines))
        
    print(f"Success! Injected {injected_count} timestamps into '{prompts_path}'.")
    print("=============================================")

if __name__ == "__main__":
    inject_timestamps()