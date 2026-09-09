Because this changes how the whole system talks to each other, we have to update **3 files**. 

Here is your exact, step-by-step implementation plan.

---

### Step 1: Create the Config & Override Files
In your main project folder (where your Python scripts are), create two new text files:

**1. `video_config.txt`**
Create this file and paste this inside. This acts as your master switch.
```text
ENABLE_ANIMATIONS=true
ENABLE_SUBTITLES=true
```

**2. `manual_animations.txt`**
Create this file and leave it empty for now. In the future, if you want to override the AI, you can type things in here like: `00_15 = zoom_out` or `01_30 = static`.

---

### Step 2: Decoupling Images from Captions (`transcribe_audio.py`)
Currently, your images are tied to your subtitles. We need to split the chunking engine into **Two Tracks**: 
1. **Track 1 (Images):** Groups 10-15 words to keep images on screen longer.
2. **Track 2 (Captions):** Groups 1-4 words for fast, engaging YouTube Shorts subtitles.

Open `transcribe_audio.py` and replace the entire `# DYNAMIC YOUTUBE CHUNKING ENGINE` (the whole `for` loop section) with this Dual-Track engine:

```python
            # ==========================================
            # DUAL-TRACK CHUNKING ENGINE
            # ==========================================
            
            # TRACK 1: IMAGE TIMELINE (10-18 words per image)
            img_words = []
            img_start = None
            for i, word_obj in enumerate(all_words):
                w_text = word_obj.get("word", "").strip()
                w_start = word_obj.get("start", 0.0)
                if not w_text: continue
                if img_start is None: img_start = w_start
                img_words.append(w_text)
                
                is_last = (i == len(all_words) - 1)
                has_punct = any(p in w_text for p in ['.', '!', '؟', '?'])
                next_gap = (all_words[i+1].get("start", word_obj.get("end", 0)) - word_obj.get("end", 0)) if not is_last else 0.0
                
                # Break if > 18 words, OR if > 10 words and there's a pause/punctuation, OR heavy pause
                if is_last or next_gap > 1.2 or len(img_words) >= 18 or (len(img_words) >= 10 and (has_punct or next_gap > 0.4)):
                    output_text_lines.append(f"{format_timestamp(img_start)} {' '.join(img_words)}")
                    img_words = []
                    img_start = None

            # TRACK 2: SRT CAPTION TIMELINE (1-4 words max for fast reading)
            srt_words = []
            srt_start = None
            for i, word_obj in enumerate(all_words):
                w_text = word_obj.get("word", "").strip()
                w_start = word_obj.get("start", 0.0)
                w_end = word_obj.get("end", w_start + 0.5)
                if not w_text: continue
                if srt_start is None: srt_start = w_start
                srt_words.append(w_text)
                
                is_last = (i == len(all_words) - 1)
                has_punct = any(p in w_text for p in ['.', '!', '؟', '،', ','])
                next_gap = (all_words[i+1].get("start", w_end) - w_end) if not is_last else 0.0
                
                # Break tightly: Max 4 words, or commas, or small pauses
                if is_last or len(srt_words) >= 4 or has_punct or next_gap > 0.3:
                    chunk_text = " ".join(srt_words).strip()
                    output_srt_lines.extend([
                        str(srt_index),
                        f"{format_srt_timestamp(srt_start)} --> {format_srt_timestamp(w_end)}",
                        chunk_text, ""
                    ])
                    srt_index += 1
                    srt_words = []
                    srt_start = None
```

---

### Step 3: Teaching the AI to Direct Cameras (`flow_image_generator.py`)
We need to add the `"camera_movement"` key to the JSON schema so Gemini decides how the camera should act based on the script.

Open `flow_image_generator.py` and look at the `generic_monolithic_template` (around line 180). **Update the `visual_prompt` dictionary in the JSON schema example to look exactly like this:**

```json
    "visual_prompt": {
      "subject": "Exhaustive description of characters/objects matching the Stick-Figure roadmap.",
      "action_and_expression": "What is happening right now.",
      "environment": "Exhaustive description of the setting. MUST be solid flat colors, no textures.",
      "composition": "Shot type (wide, close up), framing, and negative space.",
      "camera_movement": "Choose ONLY ONE: static, zoom_in, zoom_out, pan_left, pan_right",
      "style": "Flat 2D minimalist vector animation, flat colors, ZERO shading, ZERO 3D.",
      "constraints": { "no_text": true, "no_3d": true, "no_shading": true, "no_photorealism": true, "no_gradients": true }
    }
```

---

### Step 4: The Silky Smooth Video Engine (`compile_video.py`)
Because we decoupled the images from the SRT, `compile_video.py` can no longer read the SRT to build the image timeline. It must read the `timestamped_transcript.txt`. Furthermore, we need to inject the "Anti-Jitter" math (`scale=4000x2250` before zooming) and read the AI JSON file.

**Update the `compile_video.py` script with this code:**

```python
import os
import json
import re
import sys
import subprocess

def get_config_value(file_path, key, default):
    """Reads a true/false string from the config text file."""
    if not os.path.exists(file_path): return default
    with open(file_path, 'r') as f:
        for line in f:
            if line.startswith(key):
                return line.split('=')[1].strip().lower()
    return default

def get_audio_duration(audio_path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
    return float(subprocess.check_output(cmd).decode('utf-8').strip())

def get_latest_run_folder(runs_path="youtube_runs"):
    if not os.path.exists(runs_path): return None
    subdirs = [os.path.join(runs_path, name) for name in os.listdir(runs_path) if os.path.isdir(os.path.join(runs_path, name))]
    return max(subdirs, key=os.path.getmtime) if subdirs else None

def load_ai_camera_decisions(json_path):
    """Reads flow_prompts.json to extract what the AI decided for camera_movement."""
    camera_map = {}
    if not os.path.exists(json_path): return camera_map
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            content = f.read()
            json_blocks = re.findall(r'\[\s*\{.*?\}\s*\]', content, re.DOTALL)
            for block in json_blocks:
                data = json.loads(block)
                for item in data:
                    ts = str(item.get("timestamp", "")).replace("[", "").replace("]", "").replace(":", "_").strip()
                    vp = item.get("visual_prompt", {})
                    if isinstance(vp, dict):
                        cam = vp.get("camera_movement", "static").lower()
                        if ts: camera_map[ts] = cam
    except Exception as e:
        print(f"Warning: Could not parse AI camera decisions: {e}")
    return camera_map

def load_manual_overrides(txt_path):
    """Reads manual_animations.txt (e.g. 00_12 = zoom_out)."""
    overrides = {}
    if not os.path.exists(txt_path): return overrides
    with open(txt_path, 'r') as f:
        for line in f:
            if '=' in line:
                k, v = line.split('=')
                overrides[k.strip()] = v.strip().lower()
    return overrides

def parse_image_timeline(txt_path):
    """Reads timestamped_transcript.txt to build the image timeline."""
    blocks = []
    with open(txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            match = re.match(r"^\[(\d{2}):(\d{2})\]", line.strip())
            if match:
                sec = int(match.group(1)) * 60 + int(match.group(2))
                timestamp_clean = f"{match.group(1)}_{match.group(2)}"
                blocks.append({"sec": sec, "name": timestamp_clean})
    return blocks

def fix_arabic_srt(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f: content = f.read()
    with open(output_path, "w", encoding="utf-8-sig") as f: f.write(content)

def main():
    print("=============================================")
    print("Starting SILKY CINEMATIC Video Compilation")
    print("=============================================")

    latest_run = get_latest_run_folder()
    if not latest_run: sys.exit(1)

    # 1. Load Custom Configs (Animations & Subtitles)
    anim_enabled = get_config_value("video_config.txt", "ENABLE_ANIMATIONS", "true") == "true"
    subs_enabled = get_config_value("video_config.txt", "ENABLE_SUBTITLES", "true") == "true"
    
    ai_cameras = load_ai_camera_decisions(os.path.join(latest_run, "flow_prompts.json"))
    manual_cameras = load_manual_overrides("manual_animations.txt")
    
    txt_path = os.path.join(latest_run, "timestamped_transcript.txt")
    image_blocks = parse_image_timeline(txt_path)
    audio_path = os.path.join(latest_run, "full_episode_voice.wav")
    audio_duration = get_audio_duration(audio_path)

    temp_clips_dir = os.path.join(latest_run, "temp_clips")
    os.makedirs(temp_clips_dir, exist_ok=True)
    concat_file_path = os.path.join(latest_run, "concat.txt")
    
    valid_clips = 0
    last_valid_image = None
    
    print(f"\nAnimations Enabled: {anim_enabled}")
    print(f"Subtitles Enabled: {subs_enabled}")
    print("Pre-processing image timeline (Silky Camera Engine)...")
    
    with open(concat_file_path, "w", encoding="utf-8") as f:
        for idx, block in enumerate(image_blocks):
            img_name = f"{block['name']}.png"
            abs_image_path = os.path.join(latest_run, "generated_images", img_name)
            
            if not os.path.exists(abs_image_path):
                if last_valid_image is None: continue
                abs_image_path = last_valid_image
            else:
                last_valid_image = abs_image_path

            start_sec = block['sec']
            end_sec = image_blocks[idx+1]['sec'] if idx < len(image_blocks)-1 else audio_duration
            duration = max(0.2, end_sec - start_sec)
            frames = int(duration * 24)

            # Camera Decision Engine
            camera_action = "static"
            if anim_enabled:
                camera_action = ai_cameras.get(block['name'], "static")
                if block['name'] in manual_cameras:
                    camera_action = manual_cameras[block['name']]
            
            # Silky Anti-Jitter FFmpeg Math
            if "zoom_in" in camera_action:
                vf_string = f"scale=4000x2250,zoompan=z='zoom+0.0005':d={frames}:s=1920x1080:fps=24"
            elif "zoom_out" in camera_action:
                vf_string = f"scale=4000x2250,zoompan=z='if(eq(on,1),1.1,zoom-0.0005)':d={frames}:s=1920x1080:fps=24"
            elif "pan_left" in camera_action:
                vf_string = f"scale=4000x2250,zoompan=z=1.1:x='(iw-iw/zoom)*(1-in/d)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps=24"
            elif "pan_right" in camera_action:
                vf_string = f"scale=4000x2250,zoompan=z=1.1:x='(iw-iw/zoom)*(in/d)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps=24"
            else:
                vf_string = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:-1:-1:color=black"

            clip_name = f"clip_{idx:04d}.mp4"
            clip_path = os.path.join(temp_clips_dir, clip_name)
            
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-loop", "1", "-framerate", "24", 
                "-i", abs_image_path,
                "-vf", vf_string,
                "-c:v", "libx264", "-t", str(duration),
                "-preset", "fast", "-crf", "18", 
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                clip_path
            ]

            res = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0:
                print(f"  [ERROR] {img_name}: {res.stderr.decode('utf-8', errors='ignore')}")
                continue
            
            f.write(f"file 'temp_clips/{clip_name}'\n")
            print(f"  [OK] {img_name} -> {duration:.2f}s ({camera_action.upper()})")
            valid_clips += 1

    # Final Compositing
    print("\nExecuting Final Burn (Audio + Compositing)...")
    
    # Base FFmpeg command
    final_cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", "concat.txt", "-i", "full_episode_voice.wav"
    ]

    # Dynamically inject subtitle filter only if enabled
    if subs_enabled:
        print("  -> Subtitles are ENABLED. Burning Arabic SRT to video track...")
        srt_path = os.path.join(latest_run, "timestamped_transcript.srt")
        fixed_srt = os.path.join(latest_run, "timestamped_transcript_fixed.srt")
        fix_arabic_srt(srt_path, fixed_srt)
        
        sub_style = "Fontname=Tahoma,Fontsize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2.5,Shadow=1,Alignment=2,MarginV=50,Bold=1"
        final_cmd.extend(["-vf", f"subtitles={os.path.basename(fixed_srt)}:force_style='{sub_style}'"])
    else:
        print("  -> Subtitles are DISABLED. Skipping text rendering...")

    # Attach the rest of the encoding arguments
    final_cmd.extend([
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v", "-map", "1:a", "-shortest",
        "youtube_ready_video.mp4"
    ])
    
    subprocess.run(final_cmd, cwd=latest_run, check=True)
    print("\n[SUCCESS] Master Video Completed!")

if __name__ == "__main__":
    main()
```

### What You Will See Now:
1. When you run `transcribe_audio.py`, it will make **two separate files** (Long image timings, and short 4-word subtitles).
2. When Gemini plans the JSON, it will add `camera_movement: "zoom_in"` etc., doing the creative directing for you.
3. When you run `compile_video.py`, FFmpeg will up-scale the images to 4K *before* zooming, resulting in an incredibly slow, cinematic, **completely jitter-free zoom**, just like a real documentary!