import os
import re
import json
import glob

# Injects timestamps from image_timestamps.txt into flow_prompts.json based on matching index values.

def get_target_directory():
    """
    Checks if target files exist in the current directory first.
    If not, locates the newest subdirectory inside 'youtube_runs/'.
    """
    if os.path.exists("image_timestamps.txt") and os.path.exists("flow_prompts.json"):
        return "."
    
    runs_path = "youtube_runs"
    if os.path.exists(runs_path):
        folders = glob.glob(os.path.join(runs_path, "*"))
        folders = [f for f in folders if os.path.isdir(f)]
        if folders:
            return max(folders, key=os.path.getmtime)
            
    return "."

def parse_image_timestamps(timestamps_path):
    """
    Parses image_timestamps.txt and maps line index to bracketed timestamps.
    Line 1 -> '[00:00]', Line 2 -> '[00:06]', etc.
    """
    timestamps_map = {}
    if not os.path.exists(timestamps_path):
        return timestamps_map
        
    index = 1
    with open(timestamps_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            # Extract timestamp inside brackets e.g., [00:00] or [01:23:45]
            match = re.search(r'\[(\d{2}:\d{2}(?::\d{2})?)\]', line)
            if match:
                timestamps_map[index] = f"[{match.group(1)}]"
                index += 1
                
    return timestamps_map

def sanitize_json_content(content):
    """
    Fixes invalid unescaped inner double quotes inside JSON string values.
    Example:
      "accent_color_hook": "The Arabic text "ولكن" in bold."
      -->
      "accent_color_hook": "The Arabic text \"ولكن\" in bold."
    """
    lines = content.splitlines()
    fixed_lines = []
    
    # Matches lines structured as:  "key": "value string" or "key": "value string",
    kv_pattern = re.compile(r'^(\s*"[^"]+"\s*:\s*")(.+)("\s*,?\s*)$')
    
    for line in lines:
        match = kv_pattern.match(line)
        if match:
            prefix = match.group(1)
            body = match.group(2)
            suffix = match.group(3)
            
            # Escape inner unescaped quotes
            body_fixed = re.sub(r'(?<!\\)"', r'\"', body)
            fixed_lines.append(prefix + body_fixed + suffix)
        else:
            fixed_lines.append(line)
            
    return '\n'.join(fixed_lines)

def load_flow_prompts_json(json_path):
    """
    Reads flow_prompts.json safely, fixing unescaped inner quotes and multi-array JSON blocks.
    """
    with open(json_path, "r", encoding="utf-8-sig") as f:
        content = f.read()
        
    # Clean header/footer lines if present
    content = re.sub(r'^---.*?\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'---.*?$', '', content, flags=re.MULTILINE)
    content = content.strip()

    if not content:
        print("Diagnostic: 'flow_prompts.json' is empty.")
        return []

    # Auto-sanitize inner unescaped quotes in JSON string fields
    sanitized_content = sanitize_json_content(content)

    blocks = []
    
    # 1. Match all JSON array patterns [...]
    array_matches = re.findall(r'\[\s*\{[\s\S]*?\}\s*\]', sanitized_content)
    
    for match_str in array_matches:
        # Clean trailing commas if present e.g. ", }" or ", ]"
        clean_str = re.sub(r',\s*([\}\]])', r'\1', match_str)
        try:
            parsed = json.loads(clean_str)
            if isinstance(parsed, list):
                blocks.append(parsed)
        except json.JSONDecodeError as e:
            print(f"Warning: Block failed to parse: {e}")

    # 2. Fallback: Try standard json.loads if regex extraction didn't catch blocks
    if not blocks:
        try:
            clean_content = re.sub(r',\s*([\}\]])', r'\1', sanitized_content)
            parsed = json.loads(clean_content)
            if isinstance(parsed, list):
                blocks = [parsed]
        except json.JSONDecodeError:
            pass

    # 3. Fallback 2: Incremental raw_decode loop
    if not blocks:
        decoder = json.JSONDecoder()
        pos = 0
        length = len(sanitized_content)
        while pos < length:
            while pos < length and sanitized_content[pos].isspace():
                pos += 1
            if pos >= length:
                break
            try:
                obj, end = decoder.raw_decode(sanitized_content, pos)
                if isinstance(obj, list):
                    blocks.append(obj)
                pos = end
            except json.JSONDecodeError:
                pos += 1

    return blocks

def inject_timestamps():
    target_dir = get_target_directory()
    timestamps_path = os.path.join(target_dir, "image_timestamps.txt")
    json_path = os.path.join(target_dir, "flow_prompts.json")
    
    print("=============================================")
    print("Injecting Timestamps into flow_prompts.json")
    print(f"Target Directory: '{os.path.abspath(target_dir)}'")
    print("=============================================")
    
    if not os.path.exists(timestamps_path) or not os.path.exists(json_path):
        print(f"Error: Missing required files in '{target_dir}'")
        print(f" - image_timestamps.txt (exists: {os.path.exists(timestamps_path)})")
        print(f" - flow_prompts.json (exists: {os.path.exists(json_path)})")
        return

    # 1. Parse timestamps map from txt file
    timestamps_map = parse_image_timestamps(timestamps_path)
    print(f"Parsed {len(timestamps_map)} timestamps from '{os.path.basename(timestamps_path)}'.")

    # 2. Parse flow_prompts.json blocks
    blocks = load_flow_prompts_json(json_path)
    if not blocks:
        print("Error: Could not parse any JSON blocks from flow_prompts.json")
        return
    
    # 3. Inject timestamps into items matching index
    injected_count = 0
    for block in blocks:
        for item in block:
            idx = item.get("index")
            if idx in timestamps_map:
                item["timestamp"] = timestamps_map[idx]
                injected_count += 1

    # 4. Save updated flow_prompts.json with valid escaped JSON encoding
    json_blocks_str = [json.dumps(block, ensure_ascii=False, indent=2) for block in blocks]
    
    with open(json_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(json_blocks_str))
        
    print(f"Success! Injected timestamps into {injected_count} prompt entries.")
    print("=============================================")

if __name__ == "__main__":
    inject_timestamps()