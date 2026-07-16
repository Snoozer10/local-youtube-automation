import os
import re
import sys
import json
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

def clean_timestamp_to_bracket_format(srt_time_range):
    """Converts '00:01:23,450 --> 00:01:28,100' into '[01:23]' format."""
    if not srt_time_range or "-->" not in srt_time_range:
        return ""
    try:
        # Extract the start time part: "00:01:23,450"
        start_part = srt_time_range.split("-->")[0].strip()
        # Strip milliseconds: "00:01:23"
        time_digits = start_part.split(",")[0].strip()
        h, m, s = [int(x) for x in time_digits.split(":")]
        if h > 0:
            return f"[{h:02d}:{m:02d}:{s:02d}]"
        else:
            return f"[{m:02d}:{s:02d}]"
    except Exception:
        return ""

def parse_pre_planned_prompts(prompts_path):
    """Parses blocks inside pre_planned_prompts.txt into structural dictionaries."""
    if not os.path.exists(prompts_path):
        return []
        
    with open(prompts_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    blocks = []
    current_block = {}
    
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
            
        # Detect start of a new Index block
        match_idx = re.match(r"^Index:\s*(\d+)", line)
        if match_idx:
            if current_block:
                blocks.append(current_block)
            current_block = {"index": int(match_idx.group(1))}
            continue
            
        # Parse visual fields
        if line.startswith("Sentence:"):
            current_block["sentence"] = line.replace("Sentence:", "", 1).strip()
            continue
        if line.startswith("Calculated Timestamp:"):
            current_block["timestamp_raw"] = line.replace("Calculated Timestamp:", "", 1).strip()
            continue
        if line.startswith("Visual Prompt:"):
            current_block["visual_prompt"] = line.replace("Visual Prompt:", "", 1).strip()
            continue
            
    if current_block:
        blocks.append(current_block)
        
    return blocks

def generate_flow_prompts():
    print("=============================================")
    print("Generating flow_prompts.json for Compiler")
    print("=============================================")

    # 1. Resolve latest run folder
    latest_run = get_latest_run_folder()
    if not latest_run:
        print("Error: No active run folders found in 'youtube_runs/'.")
        sys.exit(1)
        
    print(f"Target Video Folder: '{latest_run}'")
    
    prompts_path = os.path.join(latest_run, "pre_planned_prompts.txt")
    json_output_path = os.path.join(latest_run, "flow_prompts.json")
    
    if not os.path.exists(prompts_path):
        print(f"Error: Missing required file: '{prompts_path}'")
        sys.exit(1)
        
    # 2. Parse prompts file
    raw_blocks = parse_pre_planned_prompts(prompts_path)
    print(f"Parsed {len(raw_blocks)} blocks from prompts file.")
    
    # 3. Format into compile_video.py-compatible JSON structures
    flow_data = []
    for b in raw_blocks:
        raw_ts = b.get("timestamp_raw", "")
        bracket_ts = clean_timestamp_to_bracket_format(raw_ts)
        
        # Skip entries that don't have valid timestamps assigned yet
        if not bracket_ts:
            continue
            
        flow_item = {
            "timestamp": bracket_ts,
            "visual_prompt": {
                "camera_specifications": b.get("visual_prompt", "")
            }
        }
        flow_data.append(flow_item)
        
    # 4. Save JSON file using standard pretty print brackets
    with open(json_output_path, "w", encoding="utf-8") as f:
        json.dump(flow_data, f, ensure_ascii=False, indent=2)
        
    print(f"Success! Generated '{json_output_path}' with {len(flow_data)} active entries.")
    print("=============================================")

if __name__ == "__main__":
    generate_flow_prompts()