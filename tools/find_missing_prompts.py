import os
import json
import re
import sys

# automated Python script called find_missing_prompts.py that will compare your generated_images folder against flow_prompts.json, identify the exact 6 missing image prompts, and output them into missing_prompts.json inside your run folder.

def get_latest_run_folder(runs_path="youtube_runs"):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    rel_to_script = os.path.join(script_dir, runs_path)
    resolved_path = rel_to_script if os.path.exists(rel_to_script) else runs_path
    
    if not os.path.exists(resolved_path):
        return None
        
    subdirs = [
        os.path.join(resolved_path, name) 
        for name in os.listdir(resolved_path) 
        if os.path.isdir(os.path.join(resolved_path, name))
    ]
    return max(subdirs, key=os.path.getmtime) if subdirs else None

def load_flow_prompts(json_path):
    if not os.path.exists(json_path):
        return []
    with open(json_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
        
    cleaned = re.sub(r'\]\s*\[', ',', content)
    if not cleaned.startswith('['): cleaned = '[' + cleaned
    if not cleaned.endswith(']'): cleaned += ']'
    
    return json.loads(cleaned)

def find_missing_prompts(run_folder=None):
    if not run_folder:
        run_folder = get_latest_run_folder()

    if not run_folder or not os.path.exists(run_folder):
        print("[FATAL ERROR] Could not locate an active run folder in 'youtube_runs'.")
        return

    flow_prompts_path = os.path.join(run_folder, "flow_prompts.json")
    images_dir = os.path.join(run_folder, "generated_images")

    if not os.path.exists(flow_prompts_path):
        print(f"[FATAL ERROR] flow_prompts.json not found in: {run_folder}")
        return

    if not os.path.exists(images_dir):
        print(f"[FATAL ERROR] generated_images folder not found in: {run_folder}")
        return

    prompts = load_flow_prompts(flow_prompts_path)
    
    # Get all image files on disk
    all_files = sorted([f for f in os.listdir(images_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])
    available_files = set(all_files)
    used_files = set()  # Track 1-to-1 claimed files to prevent double counting

    print("=============================================")
    print("      IMAGE PROMPT MISSING FINDER (STRICT)   ")
    print("=============================================")
    print(f"Run Folder:                     {run_folder}")
    print(f"Total Prompts in flow_prompts: {len(prompts)}")
    print(f"Total Images on disk:          {len(all_files)}")
    print("---------------------------------------------")

    missing_prompts = []
    timestamp_occurrences = {}

    for prompt_idx, item in enumerate(prompts):
        ts_raw = str(item.get("timestamp", "")).strip("[] ")
        parts = ts_raw.split(":")
        
        if len(parts) == 2:
            ts_key = f"{int(parts[0]):02d}_{int(parts[1]):02d}"
        elif len(parts) == 3:
            ts_key = f"{int(parts[0]):02d}_{int(parts[1]):02d}_{int(parts[2]):02d}"
        else:
            ts_key = f"prompt_{prompt_idx+1}"

        # Track occurrence for duplicate timestamps (e.g. frame 1 vs frame 2)
        frame_occ = timestamp_occurrences.get(ts_key, 0) + 1
        timestamp_occurrences[ts_key] = frame_occ

        # Build candidate image names for THIS specific prompt instance
        candidates = []
        if frame_occ == 1:
            candidates.extend([
                f"{ts_key}.png",
                f"{ts_key}_1.png",
                f"{ts_key}_frame1.png",
                f"{ts_key}_frame_1.png",
                f"{prompt_idx+1:04d}.png",
                f"{prompt_idx+1}.png"
            ])
        else:
            candidates.extend([
                f"{ts_key}_{frame_occ}.png",
                f"{ts_key}_frame{frame_occ}.png",
                f"{ts_key}_frame_{frame_occ}.png",
                f"{prompt_idx+1:04d}.png",
                f"{prompt_idx+1}.png"
            ])

        seq_meta = item.get("sequence_metadata", {})
        set_id = seq_meta.get("set_id")
        if set_id:
            candidates.append(f"{set_id}.png")
            candidates.append(f"{set_id}_{frame_occ}.png")

        # 1-to-1 Match check: claim the first unused matching file
        matched_file = None
        for cand in candidates:
            if cand in available_files and cand not in used_files:
                matched_file = cand
                used_files.add(cand)  # Reserve this file so another prompt cannot claim it!
                break

        if not matched_file:
            missing_prompts.append({
                "missing_number": len(missing_prompts) + 1,
                "prompt_position": prompt_idx + 1,
                "timestamp": item.get("timestamp", "N/A"),
                "frame_occurrence": frame_occ,
                "original_item": item
            })

    print(f"\n[RESULT] Found {len(missing_prompts)} missing image prompt(s):\n")
    for m in missing_prompts:
        item = m["original_item"]
        ts = item.get("timestamp", "N/A")
        meta = item.get("sequence_metadata", {})
        set_id = meta.get("set_id", "N/A")
        frame_idx = meta.get("frame_index", 1)
        total_frames = meta.get("total_frames_in_set", 1)
        
        print(f"  ❌ Prompt #{m['prompt_position']} | Timestamp: {ts} (Occurrence #{m['frame_occurrence']}) | Set: {set_id} (Frame {frame_idx}/{total_frames})")

    # Write missing prompts to missing_prompts.json inside the run folder
    output_json_path = os.path.join(run_folder, "missing_prompts.json")
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump([m["original_item"] for m in missing_prompts], f, ensure_ascii=False, indent=2)

    print(f"\n[SUCCESS] Exported missing prompts to:\n  -> {output_json_path}")

if __name__ == "__main__":
    run_folder_arg = sys.argv[1] if len(sys.argv) > 1 else None
    find_missing_prompts(run_folder_arg)