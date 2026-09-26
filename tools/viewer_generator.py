"""Interactive Side-by-Side HTML Comparison Viewer Generator.

Generates a standalone, responsive, dark-mode HTML comparison studio
linking baseline generated images and Socratic canary images side-by-side
with Arabic spoken subtitles, prompt diffs, and interactive keyboard navigation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from typing import Any


def parse_timestamp_seconds(ts_str: str | None) -> float | None:
    """Parses a timestamp string like '[01:23.450]' or '01:23' into seconds as float."""
    if not ts_str:
        return None
    cleaned = str(ts_str).replace("[", "").replace("]", "").strip()
    parts = cleaned.split(":")
    try:
        if len(parts) == 2:
            return float(parts[0]) * 60.0 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
        elif len(parts) == 1 and parts[0]:
            return float(parts[0])
    except (ValueError, TypeError):
        pass
    return None


def format_visual_prompt(prompt_data: Any) -> str:
    """Formats visual prompt data (string or dict) into clean, human-readable text."""
    if not prompt_data:
        return ""
    if isinstance(prompt_data, str):
        return prompt_data.strip()
    if isinstance(prompt_data, dict):
        if prompt_data.get("enhanced_prompt"):
            return str(prompt_data["enhanced_prompt"]).strip()
        lines = []
        for k in ["subject", "action", "setting", "style", "composition", "lighting", "visual_delta"]:
            val = prompt_data.get(k)
            if val:
                lines.append(f"{k.capitalize()}: {val}")
        if lines:
            return "\n".join(lines)
        return json.dumps(prompt_data, ensure_ascii=False, indent=2)
    return str(prompt_data)


def inspect_image_dimensions(file_path: str | None) -> tuple[int, int] | None:
    """Extracts width and height of an image file without external dependencies."""
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "rb") as f:
            header = f.read(32)
            if len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR":
                w = int.from_bytes(header[16:20], "big")
                h = int.from_bytes(header[20:24], "big")
                return (w, h)
    except Exception:
        pass
    try:
        from PIL import Image  # type: ignore
        with Image.open(file_path) as img:
            return img.size
    except Exception:
        pass
    return None


def resolve_media_assets(run_dir: str, html_dir: str) -> dict[str, Any]:
    """Resolves relative paths for master audio and video proxy files."""
    audio_candidates = [
        os.path.join(run_dir, "full_episode_voice.wav"),
        os.path.join(run_dir, "audacity_voice", "full_episode_voice.wav"),
        os.path.join(run_dir, "voice.wav"),
        os.path.join(run_dir, "master_audio.wav"),
        os.path.join(run_dir, "full_voice.mp3"),
    ]
    video_candidates = [
        os.path.join(run_dir, "youtube_ready_video_720p.mp4"),
        os.path.join(run_dir, "youtube_ready_video_1080p.mp4"),
        os.path.join(run_dir, "youtube_ready_video.mp4"),
        os.path.join(run_dir, "video_preview.mp4"),
    ]

    audio_rel = None
    for ac in audio_candidates:
        if os.path.exists(ac):
            audio_rel = os.path.relpath(ac, html_dir).replace("\\", "/")
            break

    video_rel = None
    for vc in video_candidates:
        if os.path.exists(vc):
            video_rel = os.path.relpath(vc, html_dir).replace("\\", "/")
            break

    return {
        "audio_path": audio_rel,
        "video_path": video_rel,
        "has_audio": audio_rel is not None,
        "has_video": video_rel is not None,
    }


def load_roadmap_script_lines(run_dir: str) -> dict[int, str]:
    """Loads Arabic spoken script lines mapped by frame index from roadmap files."""
    script_lines: dict[int, str] = {}
    for fname in ["master_roadmap_socratic.jsonl", "master_roadmap.jsonl"]:
        p = os.path.join(run_dir, fname)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        row = json.loads(line_str)
                        idx = row.get("index")
                        s_line = row.get("script_line") or row.get("sentence", "")
                        if idx is not None and s_line:
                            script_lines[int(idx)] = str(s_line).strip()
                    except Exception:
                        pass
            if script_lines:
                break
    return script_lines


def build_frame_records(
    run_dir: str,
    canary_dir: str | None = None,
    html_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Constructs full comparison metadata records for all production frames."""
    socratic_file = os.path.join(run_dir, "flow_prompts_socratic.json")
    baseline_file = os.path.join(run_dir, "flow_prompts.json")
    canary_path = canary_dir or os.path.join(run_dir, "canary_images")
    target_html_dir = html_dir or canary_path

    # Baseline directory resolution: prefer generated_images_baseline if present, fallback to generated_images
    if os.path.exists(os.path.join(run_dir, "generated_images_baseline")):
        baseline_dir_name = "generated_images_baseline"
    else:
        baseline_dir_name = "generated_images"
    gen_path = os.path.join(run_dir, baseline_dir_name)

    socratic_items: list[dict[str, Any]] = []
    baseline_items: list[dict[str, Any]] = []

    if os.path.exists(socratic_file):
        try:
            with open(socratic_file, encoding="utf-8") as f:
                socratic_items = json.load(f)
        except Exception:
            pass
    if os.path.exists(baseline_file):
        try:
            with open(baseline_file, encoding="utf-8") as f:
                baseline_items = json.load(f)
        except Exception:
            pass

    socratic_map = {int(it["index"]): it for it in socratic_items if isinstance(it, dict) and "index" in it}
    baseline_map = {int(it["index"]): it for it in baseline_items if isinstance(it, dict) and "index" in it}
    script_lines = load_roadmap_script_lines(run_dir)

    # Ingest canonical timeline spans for kinetic camera actions and eye-line tags
    timeline_file = os.path.join(run_dir, "timeline.json")
    timeline_spans_list: list[dict[str, Any]] = []
    timeline_spans_by_idx: dict[int, dict[str, Any]] = {}
    if os.path.exists(timeline_file):
        try:
            with open(timeline_file, encoding="utf-8") as tf:
                td = json.load(tf)
                for s in td.get("spans", []):
                    if isinstance(s, dict):
                        timeline_spans_list.append(s)
                        if "index" in s:
                            try:
                                timeline_spans_by_idx[int(s["index"])] = s
                            except (ValueError, TypeError):
                                pass
        except Exception:
            pass

    # Master socratic directory candidates for fallback if canary_path is a chunk folder
    master_socratic_candidates = [
        os.path.join(run_dir, "socratic_master_frames"),
        os.path.join(run_dir, "generated_images") if baseline_dir_name != "generated_images" else None,
    ]
    master_socratic_dirs = [d for d in master_socratic_candidates if d and os.path.exists(d)]
    # Two-Pass Timestamp-Validated Span Alignment metadata
    is_spans_zero_based = (min(timeline_spans_by_idx.keys()) == 0) if timeline_spans_by_idx else False
    prompt_indices = sorted(set(socratic_map.keys()) | set(baseline_map.keys()))
    min_prompt_idx = min(prompt_indices) if prompt_indices else 1
    has_uniform_offset = (
        is_spans_zero_based
        and min_prompt_idx == 1
        and len(timeline_spans_by_idx) == len(prompt_indices)
    )

    # 5-Tier Priority Cascade with Index Unioning:
    all_indices: set[int] = set()
    all_indices.update(socratic_map.keys())
    all_indices.update(baseline_map.keys())
    all_indices.update(script_lines.keys())

    if prompt_indices:
        if has_uniform_offset:
            # 0-based spans map 1:1 to 1-based prompts: span s corresponds to prompt s + 1.
            # prompt_indices already defines the canonical frame universe.
            pass
        elif is_spans_zero_based and min_prompt_idx == 1:
            for s_idx in timeline_spans_by_idx.keys():
                all_indices.add(s_idx + 1)
        else:
            all_indices.update(timeline_spans_by_idx.keys())
    else:
        if is_spans_zero_based:
            for s_idx in timeline_spans_by_idx.keys():
                all_indices.add(s_idx + 1)
        else:
            all_indices.update(timeline_spans_by_idx.keys())

    # Check physical disk scans if indices are empty or partial
    for d in [gen_path, canary_path] + master_socratic_dirs:
        if os.path.exists(d):
            for fn in os.listdir(d):
                if fn.lower().endswith((".png", ".jpg", ".webp")):
                    stem = os.path.splitext(fn)[0]
                    if stem.isdigit():
                        idx_cand = int(stem)
                        if idx_cand == 0 and min_prompt_idx >= 1 and (prompt_indices or script_lines):
                            continue
                        all_indices.add(idx_cand)
                    elif stem.startswith("sentence_") and stem[9:].isdigit():
                        idx_cand = int(stem[9:])
                        if idx_cand == 0 and min_prompt_idx >= 1 and (prompt_indices or script_lines):
                            continue
                        all_indices.add(idx_cand)

    if not all_indices:
        return []

    sorted_indices = sorted(all_indices)

    records: list[dict[str, Any]] = []
    for idx in sorted_indices:
        s_it = socratic_map.get(idx, {})
        b_it = baseline_map.get(idx, {})

        # Determine timestamp string
        ts = s_it.get("timestamp") or b_it.get("timestamp") or ""
        ts_sec = parse_timestamp_seconds(ts)

        # Two-Pass Span Alignment:
        t_span = None
        # Pass 1: Chronometric match if timestamp exists
        if ts_sec is not None and timeline_spans_list:
            for sp in timeline_spans_list:
                s_start = float(sp.get("start_time", 0.0) or 0.0)
                s_end = float(sp.get("end_time", s_start + 3.0) or (s_start + 3.0))
                if s_start <= ts_sec < s_end:
                    t_span = sp
                    break

        # Pass 2: Strict Index fallback
        if t_span is None and timeline_spans_by_idx:
            if has_uniform_offset:
                t_span = timeline_spans_by_idx.get(idx - 1) or timeline_spans_by_idx.get(idx)
            else:
                t_span = timeline_spans_by_idx.get(idx)

        # Calculate timing numbers
        if t_span:
            start_time = float(t_span.get("start_time", 0.0) or 0.0)
            duration = float(t_span.get("duration", 0.0) or 0.0)
            if duration <= 0.0 and "end_time" in t_span:
                duration = max(0.1, float(t_span["end_time"]) - start_time)
            elif duration <= 0.0:
                duration = 3.0
            end_time = float(t_span.get("end_time", start_time + duration))
            start_frame = int(t_span.get("start_frame", round(start_time * 30)))
            end_frame = int(t_span.get("end_frame", round(end_time * 30)))
            frame_count = int(t_span.get("frame_count", max(1, end_frame - start_frame)))
        else:
            start_time = round((idx - 1) * 3.0, 3) if idx >= 1 else 0.0
            duration = 3.0
            end_time = round(start_time + duration, 3)
            start_frame = round(start_time * 30)
            end_frame = round(end_time * 30)
            frame_count = max(1, end_frame - start_frame)

        if not ts:
            m = int(start_time // 60)
            s = int(start_time % 60)
            ts = f"[{m:02d}:{s:02d}]"

        clean_ts = ts.replace("[", "").replace("]", "").replace(":", "_").strip() if ts else f"sentence_{idx}"
        fname = f"{clean_ts}.png"

        # Baseline resolution
        abs_baseline = os.path.join(gen_path, fname)
        baseline_exists = os.path.exists(abs_baseline)
        if not baseline_exists:
            for alt_name in [f"sentence_{idx}.png", f"{idx:02d}.png", f"{idx}.png"]:
                cand = os.path.join(gen_path, alt_name)
                if os.path.exists(cand):
                    abs_baseline = cand
                    baseline_exists = True
                    break

        if baseline_exists:
            baseline_img_rel = os.path.relpath(abs_baseline, target_html_dir).replace("\\", "/")
        else:
            baseline_img_rel = f"../{baseline_dir_name}/{fname}"

        # Canary / Socratic resolution
        abs_canary = os.path.join(canary_path, fname)
        in_local_dir = os.path.exists(abs_canary)
        if not in_local_dir:
            for alt_name in [f"sentence_{idx}.png", f"{idx:02d}.png", f"{idx}.png"]:
                cand = os.path.join(canary_path, alt_name)
                if os.path.exists(cand):
                    abs_canary = cand
                    in_local_dir = True
                    break

        canary_exists = in_local_dir
        canary_img_rel = fname

        active_canary_file = None
        if in_local_dir:
            active_canary_file = abs_canary
            canary_img_rel = os.path.relpath(abs_canary, target_html_dir).replace("\\", "/")
        else:
            # Check fallback in master socratic directories
            for m_dir in master_socratic_dirs:
                cand_file = os.path.join(m_dir, fname)
                if not os.path.exists(cand_file):
                    for alt_name in [f"sentence_{idx}.png", f"{idx:02d}.png", f"{idx}.png"]:
                        c2 = os.path.join(m_dir, alt_name)
                        if os.path.exists(c2):
                            cand_file = c2
                            break
                if os.path.exists(cand_file):
                    active_canary_file = cand_file
                    canary_exists = True
                    canary_img_rel = os.path.relpath(cand_file, target_html_dir).replace("\\", "/")
                    break
            if not active_canary_file:
                canary_img_rel = os.path.relpath(abs_canary, target_html_dir).replace("\\", "/")

        s_prompt_data = s_it.get("enhanced_prompt") or s_it.get("visual_prompt") or s_it.get("prompt")
        if not s_prompt_data and s_it:
            s_prompt_data = s_it
        s_prompt = format_visual_prompt(s_prompt_data)

        b_prompt_data = b_it.get("visual_prompt") or b_it.get("prompt")
        if not b_prompt_data and b_it:
            b_prompt_data = b_it
        b_prompt = format_visual_prompt(b_prompt_data)

        archetype = s_it.get("layout_classification") or b_it.get("layout_classification", "STANDALONE")
        features = []
        if "1-2-3 shape hierarchy" in s_prompt:
            features.append("1-2-3 Shape Hierarchy")
        if "sfumato" in s_prompt.lower() or "chiaroscuro" in s_prompt.lower():
            features.append("Da Vinci Sfumato")
        if "orthographic" in s_prompt.lower():
            features.append("Orthographic 2D")
        elif "24mm" in s_prompt:
            features.append("24mm Wide-Angle")
        if "negative prompt:" in s_prompt.lower():
            features.append("Latent Neg Filter")

        punch_frame = None
        camera_action = "static_hold"
        eye_line = None
        if t_span:
            punch_frame = t_span.get("punch_frame")
            camera_action = t_span.get("camera_action", "static_hold")
            eye_line = t_span.get("eye_line_elevation")
            if punch_frame:
                features.append(f"⚡ Scale Punch (125% @ frame +{punch_frame})")
            elif camera_action == "linear_push" or float(t_span.get("duration", 0) or 0) >= 3.5:
                features.append("🎥 Linear Push (103%)")
            else:
                features.append("⏱️ Static Hold (100%)")
            if eye_line:
                features.append(f"👁️ Eye-Line Lock (Y={eye_line}px)")

        # Inspect dimensions
        base_dims = inspect_image_dimensions(abs_baseline) if baseline_exists else None
        canary_dims = inspect_image_dimensions(active_canary_file) if canary_exists else None
        res_mismatch = None
        if base_dims and canary_dims and base_dims != canary_dims:
            ar_base = base_dims[0] / max(1, base_dims[1])
            ar_canary = canary_dims[0] / max(1, canary_dims[1])
            if abs(ar_base - ar_canary) > 0.01:
                res_mismatch = f"{base_dims[0]}x{base_dims[1]} vs {canary_dims[0]}x{canary_dims[1]}"

        sha256_hash = None
        if canary_exists and active_canary_file and os.path.exists(active_canary_file):
            try:
                with open(active_canary_file, "rb") as cf:
                    sha256_hash = hashlib.sha256(cf.read()).hexdigest()
            except Exception:
                pass

        baseline_hash = None
        if baseline_exists and os.path.exists(abs_baseline):
            try:
                with open(abs_baseline, "rb") as bf:
                    baseline_hash = hashlib.sha256(bf.read()).hexdigest()
            except Exception:
                pass

        is_enhanced = False
        is_restored = False
        if sha256_hash and baseline_hash:
            if sha256_hash == baseline_hash:
                is_restored = True
            else:
                is_enhanced = True
        elif canary_exists:
            is_enhanced = bool(s_prompt)

        records.append({
            "index": idx,
            "timestamp": ts,
            "clean_ts": clean_ts,
            "start_time": round(start_time, 3),
            "end_time": round(end_time, 3),
            "duration": round(duration, 3),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "frame_count": frame_count,
            "punch_frame": punch_frame,
            "camera_action": camera_action,
            "eye_line_elevation": eye_line,
            "archetype": archetype,
            "sequence_type": s_it.get("sequence_type", "STANDALONE"),
            "script_line": script_lines.get(idx) or (t_span.get("text") if t_span else "") or "",
            "baseline_image": baseline_img_rel,
            "canary_image": canary_img_rel,
            "canary_exists": canary_exists,
            "baseline_exists": baseline_exists,
            "in_local_dir": in_local_dir,
            "is_enhanced": is_enhanced,
            "is_restored": is_restored,
            "baseline_prompt": b_prompt,
            "socratic_prompt": s_prompt,
            "features": features,
            "status": "RESTORED" if is_restored else ("ENHANCED" if is_enhanced else ("READY" if canary_exists else "PENDING")),
            "sha256_hash": sha256_hash,
            "baseline_hash": baseline_hash,
            "dimensions_baseline": f"{base_dims[0]}x{base_dims[1]}" if base_dims else None,
            "dimensions_canary": f"{canary_dims[0]}x{canary_dims[1]}" if canary_dims else None,
            "resolution_mismatch": res_mismatch,
        })

    # Detect duplicate hashes across frames
    hash_map: dict[str, list[int]] = {}
    for r in records:
        h = r.get("sha256_hash")
        if h:
            hash_map.setdefault(h, []).append(r["index"])

    for r in records:
        h = r.get("sha256_hash")
        if h and len(hash_map[h]) > 1:
            others = [i for i in hash_map[h] if i != r["index"]]
            r["duplicate_match"] = others[0] if others else None
            r["duplicate_hash"] = h[:12]
        else:
            r["duplicate_match"] = None
            r["duplicate_hash"] = None

    return records


def generate_comparison_viewer_html(
    run_dir: str,
    canary_dir: str | None = None,
    output_html: str | None = None,
) -> str:
    if canary_dir:
        canary_path = canary_dir
        default_out = os.path.join(canary_path, "canary_comparison_viewer.html")
    else:
        cand_dirs = [
            os.path.join(run_dir, "canary_images"),
            os.path.join(run_dir, "generated_images"),
        ]
        found_dir = next((d for d in cand_dirs if os.path.exists(d)), None)
        canary_path = found_dir or os.path.join(run_dir, "canary_images")
        default_out = os.path.join(run_dir, "studio_viewer.html")

    out_file = output_html or default_out
    html_dir = os.path.dirname(os.path.abspath(out_file))
    os.makedirs(html_dir, exist_ok=True)
    records = build_frame_records(run_dir, canary_path, html_dir=html_dir)

    media_info = resolve_media_assets(run_dir, html_dir)
    payload = {
        "media": media_info,
        "frames": records,
    }
    json_data = json.dumps(payload, ensure_ascii=False)

    num_chunks = max(1, math.ceil(len(records) / 50))
    chunk_options = []
    for c_idx in range(1, num_chunks + 1):
        s_f = (c_idx - 1) * 50 + 1
        e_f = c_idx * 50
        chunk_options.append(f'<option value="chunk_{c_idx}">Chunk {c_idx}: Frames {s_f}–{e_f}</option>')
    chunk_options_html = "\n      ".join(chunk_options)

    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>⚡ Socratic Visual Prompt Comparison Studio (NLE Suite)</title>
<style>
:root {
  --bg-primary: #0b0e14;
  --bg-secondary: #161b22;
  --bg-card: #21262d;
  --border: #30363d;
  --text-main: #f0f6fc;
  --text-muted: #8b949e;
  --accent-blue: #58a6ff;
  --accent-green: #3fb950;
  --accent-orange: #d29922;
  --accent-red: #f85149;
  --accent-cyan: #00e5ff;
  --accent-purple: #a371f7;
  --wipe-pos: 50%;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Cairo', 'Tajawal', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  background-color: var(--bg-primary);
  color: var(--text-main);
  line-height: 1.5;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}
header {
  height: 52px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  z-index: 20;
  flex-shrink: 0;
}
.logo-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.logo-title h1 {
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--accent-blue);
  white-space: nowrap;
}
.stats-badge {
  font-size: 0.78rem;
  background: var(--bg-card);
  padding: 3px 9px;
  border-radius: 20px;
  border: 1px solid var(--border);
  color: var(--text-muted);
  white-space: nowrap;
}
.controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
select, input {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-main);
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 0.82rem;
  outline: none;
}
select:focus, input:focus {
  border-color: var(--accent-blue);
}
.btn {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-main);
  padding: 5px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  transition: all 0.15s ease;
  user-select: none;
}
.btn:hover {
  background: #30363d;
  border-color: #8b949e;
}
.btn.active {
  background: var(--accent-blue);
  color: #0b0e14;
  border-color: var(--accent-blue);
  font-weight: 700;
}

/* Media Bar & Scrubber */
#media-bar {
  background: #11151c;
  border-bottom: 1px solid var(--border);
  padding: 6px 16px;
  display: flex;
  align-items: center;
  gap: 14px;
  flex-shrink: 0;
  z-index: 15;
}
.media-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}
.btn-play {
  background: #238636;
  border-color: #2ea043;
  color: #fff;
  font-weight: 600;
  min-width: 110px;
  justify-content: center;
}
.btn-play.playing {
  background: #da3633;
  border-color: #f85149;
}
.timecode {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.85rem;
  color: var(--accent-cyan);
  font-weight: 700;
  min-width: 135px;
  letter-spacing: 0.05em;
}
.speed-box {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.75rem;
  color: var(--text-muted);
}
.scrubber-track {
  flex: 1;
  height: 16px;
  background: #1e242e;
  border-radius: 4px;
  position: relative;
  cursor: pointer;
  user-select: none;
  border: 1px solid var(--border);
}
.scrubber-cues {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.cue-tick {
  position: absolute;
  top: 3px;
  width: 2px;
  height: 10px;
  background: rgba(255,255,255,0.22);
  pointer-events: none;
  transform: translateX(-50%);
}
.scrubber-progress {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: linear-gradient(90deg, #1f6feb, #58a6ff);
  border-radius: 3px;
  pointer-events: none;
  width: 0%;
}
.scrubber-handle {
  position: absolute;
  top: -3px;
  width: 6px;
  height: 22px;
  background: #fff;
  border-radius: 3px;
  transform: translateX(-50%);
  box-shadow: 0 0 8px rgba(0,0,0,0.9);
  pointer-events: none;
  left: 0%;
}
.scrubber-tooltip {
  position: absolute;
  bottom: 24px;
  transform: translateX(-50%);
  background: #21262d;
  border: 1px solid var(--border);
  padding: 3px 7px;
  font-size: 0.75rem;
  font-family: monospace;
  border-radius: 4px;
  white-space: nowrap;
  pointer-events: none;
  z-index: 30;
  color: #f0f6fc;
  box-shadow: 0 4px 12px rgba(0,0,0,0.5);
  display: none;
}

/* Main Workspace */
main {
  display: flex;
  flex: 1;
  overflow: hidden;
  position: relative;
}
.stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
  overflow-y: auto;
  gap: 12px;
  position: relative;
}

/* Viewport Containers */
#stage-dual {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  flex: 1;
  min-height: 420px;
}
#stage-wipe {
  display: none;
  width: 100%;
  flex: 1;
  min-height: 420px;
  justify-content: center;
  align-items: center;
}
#stage-diff {
  display: none;
  width: 100%;
  flex: 1;
  min-height: 420px;
  justify-content: center;
  align-items: center;
}

.panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}
.panel-header {
  padding: 8px 14px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.82rem;
  font-weight: 600;
  flex-shrink: 0;
}
.tag-baseline { color: var(--accent-orange); }
.tag-socratic { color: var(--accent-green); }

.img-container {
  flex: 1;
  min-height: 380px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #000;
  position: relative;
  overflow: hidden;
}
.pan-zoom-stage {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  cursor: grab;
  background: #000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.pan-zoom-stage.panning {
  cursor: grabbing;
}
.pan-zoom-content {
  position: relative;
  width: 100%;
  height: 100%;
  transform-origin: 0 0;
  transition: transform 0.04s ease-out;
  display: flex;
  align-items: center;
  justify-content: center;
}
.pan-zoom-content img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  pointer-events: none;
  user-select: none;
}
.img-placeholder {
  color: var(--text-muted);
  font-size: 0.9rem;
  font-style: italic;
  position: absolute;
  pointer-events: none;
}

/* Wipe Viewport (Single 16:9 canvas with forced geometric normalization) */
#wipe-viewport {
  position: relative;
  aspect-ratio: 16 / 9;
  width: 100%;
  max-width: 1280px;
  max-height: calc(100vh - 360px);
  background: #000;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  margin: 0 auto;
  user-select: none;
}
#wipe-base-img, #wipe-canary-img {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  pointer-events: none;
}
#wipe-canary-img {
  clip-path: polygon(0 0, var(--wipe-pos, 50%) 0, var(--wipe-pos, 50%) 100%, 0 100%);
}
#wipe-divider {
  position: absolute;
  top: 0;
  bottom: 0;
  left: var(--wipe-pos, 50%);
  width: 2px;
  background: var(--accent-blue);
  pointer-events: none;
  z-index: 10;
  box-shadow: 0 0 8px var(--accent-blue);
}
#wipe-handle {
  position: absolute;
  top: 50%;
  left: var(--wipe-pos, 50%);
  transform: translate(-50%, -50%);
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--accent-blue);
  border: 2px solid #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: #0b0e14;
  font-weight: bold;
  cursor: ew-resize;
  z-index: 12;
  user-select: none;
  box-shadow: 0 0 12px rgba(0,0,0,0.8);
}

/* Diff Viewport */
#diff-viewport {
  position: relative;
  aspect-ratio: 16 / 9;
  width: 100%;
  max-width: 1280px;
  max-height: calc(100vh - 360px);
  background: #000;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  margin: 0 auto;
}
#diff-base-img {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
#diff-canary-img {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  mix-blend-mode: difference;
  filter: invert(1);
}

/* Safe Zone Overlays (SVG) */
.safe-zones-svg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 15;
}

/* Inspector Metadata Section */
.meta-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex-shrink: 0;
}
.arabic-script-box {
  background: #11151c;
  padding: 8px 14px;
  border-radius: 6px;
  border-right: 3px solid var(--accent-blue);
  direction: rtl;
  text-align: right;
}
.arabic-script {
  font-family: 'Cairo', 'Tajawal', sans-serif;
  font-size: 1.05rem;
  line-height: 1.7;
  color: #f0f6fc;
}
.tags-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.badge {
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.badge-green { background: #1f3d2b; color: #3fb950; border-color: #2ea043; font-weight: 600; }
.badge-orange { background: #3d2f1f; color: #d29922; border-color: #bb8009; font-weight: 600; }
.badge-blue { background: #1f2d3d; color: #58a6ff; border-color: #388bfd; }
.badge-cyan { background: #0e3742; color: #00e5ff; border-color: #00b4d8; font-weight: 600; }
.badge-purple { background: #2e1f3d; color: #d2a8ff; border-color: #a371f7; }
.badge-red { background: #3d1f1f; color: #f85149; border-color: #da3633; font-weight: 600; }

.prompt-diff {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  background: #11151c;
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 0.8rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  line-height: 1.45;
}
.prompt-box {
  background: var(--bg-card);
  padding: 8px 10px;
  border-radius: 4px;
  border: 1px solid var(--border);
  overflow-y: auto;
  max-height: 150px;
  white-space: pre-wrap;
  word-break: break-word;
}
.prompt-box h4 {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
  display: flex;
  justify-content: space-between;
}

/* Filmstrip */
#filmstrip {
  height: 84px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border);
  display: flex;
  overflow-x: auto;
  padding: 6px 12px;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
  z-index: 10;
}
.film-item {
  flex-shrink: 0;
  width: 84px;
  height: 68px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
  transition: all 0.15s ease;
}
.film-item:hover {
  border-color: #8b949e;
  transform: translateY(-2px);
}
.film-item.active {
  border-color: var(--accent-blue);
  box-shadow: 0 0 10px rgba(88, 166, 255, 0.7);
  transform: scale(1.04);
}
.film-item img {
  width: 100%;
  height: 48px;
  object-fit: cover;
  background: #000;
}
.film-item span {
  font-size: 0.68rem;
  color: var(--text-muted);
  font-family: monospace;
  white-space: nowrap;
}
.film-item.has-canary {
  border-bottom: 3px solid var(--accent-green);
}
.film-item.is-restored {
  border-bottom: 3px solid var(--accent-orange);
}
</style>
</head>
<body>

<header>
  <div class="logo-title">
    <h1>⚡ Socratic Comparison Studio</h1>
    <span class="stats-badge" id="stats-badge">Loading stats...</span>
  </div>
  <div class="controls">
    <button class="btn" id="prev-btn" title="Previous Frame (Left Arrow)">◀ Prev</button>
    <span id="frame-counter" style="font-weight: 700; font-size: 0.88rem; min-width: 90px; text-align: center;">Frame 1</span>
    <button class="btn" id="next-btn" title="Next Frame (Right Arrow)">Next ▶</button>
    <select id="filter-select">
      <option value="all">Show All Frames</option>
      __CHUNK_OPTIONS__
      <option value="enhanced">Socratic Enhanced Only</option>
      <option value="restored">Restored Baseline Only</option>
      <option value="in_folder">In This Folder Only</option>
      <option value="completed">Canary Ready Only</option>
      <option value="pending">Pending Canary Only</option>
    </select>
    <input type="text" id="search-input" placeholder="Search prompt / script..." style="width: 160px;"/>
    <select id="view-mode-select" title="Switch View Mode (W / D)">
      <option value="dual" selected>View: Dual (Side-by-Side)</option>
      <option value="wipe">View: Split Wipe (W)</option>
      <option value="baseline">View: Baseline Only</option>
      <option value="socratic">View: Canary Only</option>
      <option value="diff">View: Difference Diff (D)</option>
    </select>
    <button class="btn" id="safe-zone-btn" title="Toggle Broadcast Safe Zones (S)">🛡️ Safe Zones (S)</button>
    <div style="display:flex; align-items:center; gap:4px;">
      <span id="zoom-readout" style="font-size:0.78rem; color:#8b949e; min-width:38px; text-align:right;">100%</span>
      <button class="btn" id="reset-zoom-btn" title="Reset Zoom & Pan (Z)" style="padding:3px 7px; font-size:0.75rem;">Reset (Z)</button>
    </div>
    <div style="display:flex; gap:6px; align-items:center;">
      <label style="cursor:pointer; display:flex; align-items:center; gap:4px; font-size:12px; color:#c9d1d9;">
        <input type="checkbox" id="regen-checkbox" style="cursor:pointer;"/> Select
      </label>
      <button class="btn" id="copy-regen-btn" style="background:#238636; border-color:#2ea043; font-size:12px;" title="Copy CLI command for selected frames">📋 Copy Re-Gen (<span id="regen-count">0</span>)</button>
    </div>
  </div>
</header>

<div id="media-bar">
  <audio id="master-audio" preload="metadata"></audio>
  <video id="video-proxy" preload="metadata" muted playsinline style="display:none;"></video>
  <div class="media-row">
    <button class="btn btn-play" id="play-btn" title="Play / Pause (Space or P)">▶ Play (Space)</button>
    <span id="timecode-display" class="timecode">00:00:00 / 00:00:00</span>
    <div class="speed-box">
      <span>Speed:</span>
      <select id="speed-select">
        <option value="0.75">0.75x</option>
        <option value="1" selected>1.0x</option>
        <option value="1.25">1.25x</option>
        <option value="1.5">1.5x</option>
        <option value="2">2.0x</option>
      </select>
    </div>
    <div id="scrubber-track" class="scrubber-track">
      <div id="scrubber-cues" class="scrubber-cues"></div>
      <div id="scrubber-progress" class="scrubber-progress"></div>
      <div id="scrubber-handle" class="scrubber-handle"></div>
      <div id="scrubber-tooltip" class="scrubber-tooltip">00:00 [Frame #1]</div>
    </div>
    <span id="clock-mode-badge" class="badge badge-blue">Virtual Clock</span>
  </div>
</div>

<main>
  <div class="stage">
    <!-- Dual Panel Viewport -->
    <div id="stage-dual">
      <div class="panel" id="panel-baseline">
        <div class="panel-header">
          <span class="tag-baseline">BASELINE (Plan v4)</span>
          <span id="baseline-file-info" style="font-size:0.75rem; color:#8b949e;">generated_images_baseline/...</span>
        </div>
        <div class="img-container">
          <div class="pan-zoom-stage" id="stage-base">
            <div class="pan-zoom-content">
              <img id="baseline-img" src="" alt="Baseline Frame"/>
            </div>
            <div class="img-placeholder" id="baseline-placeholder" style="display:none;">Baseline image not found</div>
            <!-- Embedded Safe Zones overlay clone -->
            <svg class="safe-zones-svg safe-zones-clone" viewBox="0 0 1920 1080" style="display:none;"></svg>
          </div>
        </div>
      </div>
      <div class="panel" id="panel-socratic">
        <div class="panel-header">
          <span class="tag-socratic">SOCRATIC (Enhanced Canary)</span>
          <span id="socratic-file-info" class="badge badge-green">canary_images/...</span>
        </div>
        <div class="img-container">
          <div class="pan-zoom-stage" id="stage-canary">
            <div class="pan-zoom-content">
              <img id="socratic-img" src="" alt="Socratic Canary Frame"/>
            </div>
            <div class="img-placeholder" id="socratic-placeholder" style="display:none;">Generation pending in Google Flow</div>
            <!-- Embedded Safe Zones overlay clone -->
            <svg class="safe-zones-svg safe-zones-clone" viewBox="0 0 1920 1080" style="display:none;"></svg>
          </div>
        </div>
      </div>
    </div>

    <!-- Split Curtain Wipe Viewport -->
    <div id="stage-wipe">
      <div id="wipe-viewport">
        <div class="pan-zoom-content" id="wipe-pan-zoom">
          <img id="wipe-base-img" src="" alt="Baseline"/>
          <img id="wipe-canary-img" src="" alt="Canary"/>
          <div id="wipe-divider"></div>
          <div id="wipe-handle" title="Drag to wipe (Keys 1-9)">⮜ ⮞</div>
        </div>
        <svg class="safe-zones-svg safe-zones-clone" viewBox="0 0 1920 1080" style="display:none;"></svg>
      </div>
    </div>

    <!-- Difference Diff Viewport -->
    <div id="stage-diff">
      <div id="diff-viewport">
        <div class="pan-zoom-content" id="diff-pan-zoom">
          <img id="diff-base-img" src="" alt="Baseline"/>
          <img id="diff-canary-img" src="" alt="Canary Diff"/>
        </div>
        <svg class="safe-zones-svg safe-zones-clone" viewBox="0 0 1920 1080" style="display:none;"></svg>
      </div>
    </div>

    <!-- Master Safe Zones SVG Definition -->
    <svg id="safe-zones-master" style="display:none;">
      <defs>
        <linearGradient id="yt-top-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(0,0,0,0.75)"/>
          <stop offset="100%" stop-color="rgba(0,0,0,0)"/>
        </linearGradient>
        <linearGradient id="yt-bot-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(0,0,0,0)"/>
          <stop offset="100%" stop-color="rgba(0,0,0,0.85)"/>
        </linearGradient>
      </defs>
      <g id="safe-zones-elements">
        <!-- Action Safe (90%) -->
        <rect x="96" y="54" width="1728" height="972" fill="none" stroke="#00e5ff" stroke-width="2" stroke-dasharray="8 6"/>
        <text x="110" y="80" fill="#00e5ff" font-size="16" font-family="monospace">ACTION SAFE (90%)</text>
        <!-- Title Safe (80%) -->
        <rect x="192" y="108" width="1536" height="864" fill="none" stroke="#ffb300" stroke-width="2" stroke-dasharray="6 4"/>
        <text x="206" y="134" fill="#ffb300" font-size="16" font-family="monospace">TITLE SAFE (80%)</text>
        <!-- Foveal 16:9 Safe Envelope (X: 180 to 1740, Y: 90 to 980) -->
        <rect x="180" y="90" width="1560" height="890" fill="none" stroke="#3fb950" stroke-width="1.5" stroke-dasharray="4 4"/>
        <text x="180" y="80" fill="#3fb950" font-size="14" font-family="monospace">FOVEAL 16:9 ENVELOPE (X:180-1740 Y:90-980)</text>
        <!-- Center Crosshair -->
        <line x1="940" y1="540" x2="980" y2="540" stroke="rgba(255,255,255,0.4)" stroke-width="1"/>
        <line x1="960" y1="520" x2="960" y2="560" stroke="rgba(255,255,255,0.4)" stroke-width="1"/>
        <!-- YouTube UI Overlay Simulator -->
        <rect x="0" y="0" width="1920" height="110" fill="url(#yt-top-grad)"/>
        <circle cx="50" cy="46" r="20" fill="rgba(255,255,255,0.3)"/>
        <rect x="85" y="38" width="180" height="16" rx="4" fill="rgba(255,255,255,0.4)"/>
        <rect x="0" y="960" width="1920" height="120" fill="url(#yt-bot-grad)"/>
        <rect x="30" y="1025" width="1860" height="6" rx="3" fill="rgba(255,0,0,0.7)"/>
        <circle cx="280" cy="1028" r="8" fill="#ff0000"/>
      </g>
    </svg>

    <!-- Inspector Metadata Section -->
    <div class="meta-section">
      <div class="arabic-script-box">
        <bdi dir="rtl" class="arabic-script" id="arabic-script">...</bdi>
      </div>
      <div class="tags-row" id="tags-row"></div>
      <div class="prompt-diff" id="prompt-diff">
        <div class="prompt-box">
          <h4 style="color:var(--accent-green);">✨ Socratic / Canary Prompt</h4>
          <div id="socratic-prompt-text"></div>
        </div>
        <div class="prompt-box">
          <h4 style="color:var(--accent-orange);">🏛️ Baseline Prompt</h4>
          <div id="baseline-prompt-text"></div>
        </div>
      </div>
    </div>
  </div>
</main>

<footer id="filmstrip"></footer>

<!-- Embedded Studio Data Payload -->
<script id="studio-data" type="application/json">
__STUDIO_DATA_JSON__
</script>

<script>
// --- Ingest Data & Setup ---
const DATA = JSON.parse(document.getElementById('studio-data').textContent);
const frames = DATA.frames || [];
const MEDIA = DATA.media || {};

let currentIndex = 0;
let filteredFrames = [...frames];
let viewMode = 'dual'; // 'dual', 'wipe', 'baseline', 'socratic', 'diff'
let isPlaying = false;
let clockMode = 'virtual';
let playbackRate = 1.0;
let virtualStartTime = 0;
let virtualCurrentTime = 0;
let wipePos = 50.0;
let isWipeDragging = false;
let safeZonesVisible = false;
let selectedForRegen = new Set();
let zoomLevel = 1.0;
let panX = 0, panY = 0;
let isPanning = false;
let panStartX = 0, panStartY = 0;

const el = id => document.getElementById(id);
const masterAudio = el('master-audio');
const videoProxy = el('video-proxy');
videoProxy.muted = true; // Single-source audio: video proxy must remain muted

// Calculate total duration
let totalDuration = 0;
if (frames.length > 0) {
  totalDuration = Math.max(...frames.map(f => (f.end_time || (f.start_time + f.duration)) || 0));
}

// Media clock configuration
if (MEDIA.video_path) {
  videoProxy.src = MEDIA.video_path;
  clockMode = 'video';
}
if (MEDIA.audio_path) {
  masterAudio.src = MEDIA.audio_path;
  if (!MEDIA.video_path) clockMode = 'audio';
}
el('clock-mode-badge').textContent = clockMode === 'video' ? '🎥 Video Proxy Sync' : (clockMode === 'audio' ? '🔊 Audio Master Sync' : '⏱️ Virtual Clock');

// Setup Safe Zones clones
function setupSafeZones() {
  const masterContent = el('safe-zones-master').innerHTML;
  document.querySelectorAll('.safe-zones-clone').forEach(svg => {
    svg.innerHTML = masterContent;
  });
}
setupSafeZones();

// Dynamic Filter Ingestion
function initDynamicFilters() {
  const select = el('filter-select');
  // Harvest unique archetypes
  const archetypes = Array.from(new Set(frames.map(f => f.archetype).filter(Boolean))).sort();
  if (archetypes.length > 0) {
    const grp = document.createElement('optgroup');
    grp.label = "Archetypes";
    archetypes.forEach(a => {
      const opt = document.createElement('option');
      opt.value = 'archetype_' + a;
      opt.textContent = `Archetype: ${a}`;
      grp.appendChild(opt);
    });
    select.appendChild(grp);
  }
  // Kinetic features
  const hasPunch = frames.some(f => f.features && f.features.some(x => x.includes('Scale Punch')));
  const hasPush = frames.some(f => f.features && f.features.some(x => x.includes('Linear Push')));
  if (hasPunch || hasPush) {
    const grp = document.createElement('optgroup');
    grp.label = "Kinetic Camera Actions";
    if (hasPunch) {
      const opt = document.createElement('option');
      opt.value = 'kinetic_punch';
      opt.textContent = '⚡ Scale Punches (125%)';
      grp.appendChild(opt);
    }
    if (hasPush) {
      const opt = document.createElement('option');
      opt.value = 'kinetic_push';
      opt.textContent = '🎥 Linear Pushes (103%)';
      grp.appendChild(opt);
    }
    select.appendChild(grp);
  }
  // Duplicates
  const dupCount = frames.filter(f => f.duplicate_match).length;
  if (dupCount > 0) {
    const opt = document.createElement('option');
    opt.value = 'duplicates';
    opt.textContent = `⚠️ Duplicate Hashes (${dupCount})`;
    select.appendChild(opt);
  }
}
initDynamicFilters();

// Format time HH:MM:SS
function formatTime(sec) {
  if (!sec || isNaN(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  const f = Math.floor((sec % 1) * 30);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}:${String(f).padStart(2, '0')}`;
}

// Scrubber setup & Cues
function setupScrubberCues() {
  const cueBox = el('scrubber-cues');
  cueBox.innerHTML = '';
  if (totalDuration <= 0) return;
  frames.forEach(f => {
    const tick = document.createElement('div');
    tick.className = 'cue-tick';
    const pct = (f.start_time / totalDuration) * 100;
    tick.style.left = `${pct}%`;
    cueBox.appendChild(tick);
  });
}
setupScrubberCues();

function updateScrubber(t) {
  el('timecode-display').textContent = `${formatTime(t)} / ${formatTime(totalDuration)}`;
  if (totalDuration > 0) {
    const pct = Math.max(0, Math.min(100, (t / totalDuration) * 100));
    el('scrubber-progress').style.width = `${pct}%`;
    el('scrubber-handle').style.left = `${pct}%`;
  }
}

// Binary Search across frames by time (O(log N))
function findFrameIndexAtTime(t) {
  if (frames.length === 0) return -1;
  let low = 0, high = frames.length - 1;
  while (low <= high) {
    const mid = (low + high) >> 1;
    const f = frames[mid];
    if (t < f.start_time) {
      high = mid - 1;
    } else if (t >= f.end_time) {
      low = mid + 1;
    } else {
      return mid;
    }
  }
  return Math.max(0, Math.min(frames.length - 1, low));
}

function getClockTime() {
  if (clockMode === 'video' && videoProxy.src) {
    return videoProxy.currentTime;
  }
  if (clockMode === 'audio' && masterAudio.src) {
    return masterAudio.currentTime;
  }
  return virtualCurrentTime;
}

function seekClock(targetSeconds) {
  targetSeconds = Math.max(0, Math.min(totalDuration, targetSeconds));
  virtualCurrentTime = targetSeconds;
  virtualStartTime = performance.now() - (targetSeconds * 1000 / playbackRate);
  if (clockMode === 'video' && videoProxy.src) {
    if (videoProxy.fastSeek) videoProxy.fastSeek(targetSeconds);
    else videoProxy.currentTime = targetSeconds;
    if (MEDIA.audio_path && masterAudio.src) {
      masterAudio.currentTime = targetSeconds;
    }
  } else if (clockMode === 'audio' && masterAudio.src) {
    masterAudio.currentTime = targetSeconds;
  }
  updateScrubber(targetSeconds);
  const targetIdx = findFrameIndexAtTime(targetSeconds);
  if (targetIdx !== -1) {
    const matchIdx = filteredFrames.findIndex(fr => fr.index === frames[targetIdx].index);
    if (matchIdx !== -1) renderFrame(matchIdx, false);
  }
}

// Scrubber Pointer Dragging
const scrubberTrack = el('scrubber-track');
const scrubberTooltip = el('scrubber-tooltip');
let isScrubbing = false;

function handleScrubEvent(e) {
  const rect = scrubberTrack.getBoundingClientRect();
  const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const t = pct * totalDuration;
  seekClock(t);
}

scrubberTrack.addEventListener('pointerdown', (e) => {
  isScrubbing = true;
  scrubberTrack.setPointerCapture(e.pointerId);
  handleScrubEvent(e);
});

scrubberTrack.addEventListener('pointermove', (e) => {
  const rect = scrubberTrack.getBoundingClientRect();
  const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const t = pct * totalDuration;
  scrubberTooltip.style.display = 'block';
  scrubberTooltip.style.left = `${pct * 100}%`;
  const fIdx = findFrameIndexAtTime(t);
  const fNum = fIdx !== -1 ? frames[fIdx].index : '?';
  scrubberTooltip.textContent = `${formatTime(t)} [Frame #${fNum}]`;
  if (isScrubbing) {
    handleScrubEvent(e);
  }
});

scrubberTrack.addEventListener('pointerleave', () => {
  if (!isScrubbing) scrubberTooltip.style.display = 'none';
});

scrubberTrack.addEventListener('pointerup', (e) => {
  if (isScrubbing) {
    isScrubbing = false;
    scrubberTooltip.style.display = 'none';
    try { scrubberTrack.releasePointerCapture(e.pointerId); } catch(ex) {}
  }
});

// Lookahead Pre-decoder
function preloadLookahead(curIdx) {
  for (let i = 1; i <= 3; i++) {
    const nextIdx = curIdx + i;
    if (nextIdx < filteredFrames.length) {
      const f = filteredFrames[nextIdx];
      if (f.canary_exists && f.canary_image) {
        const img = new Image();
        img.src = f.canary_image;
        if (img.decode) img.decode().catch(() => {});
      }
      if (f.baseline_exists && f.baseline_image) {
        const img = new Image();
        img.src = f.baseline_image;
        if (img.decode) img.decode().catch(() => {});
      }
    }
  }
}

// Stats & Header Updates
function updateStats() {
  const completed = frames.filter(f => f.canary_exists).length;
  const enhanced = frames.filter(f => f.is_enhanced).length;
  const restored = frames.filter(f => f.is_restored).length;
  const localCount = frames.filter(f => f.in_local_dir).length;
  el('stats-badge').textContent = `${completed}/${frames.length} Ready (${enhanced} Enhanced, ${restored} Restored, ${localCount} in folder)`;
}

// Render Frame
function renderFrame(index, syncClock = true) {
  if (filteredFrames.length === 0) return;
  if (index < 0) index = 0;
  if (index >= filteredFrames.length) index = filteredFrames.length - 1;
  currentIndex = index;

  const f = filteredFrames[currentIndex];
  el('frame-counter').textContent = `Frame ${f.index} / ${frames.length}`;

  if (syncClock && !isPlaying) {
    seekClock(f.start_time);
  }

  // Baseline Image
  if (f.baseline_exists) {
    el('baseline-img').src = f.baseline_image;
    el('baseline-img').style.display = 'block';
    el('baseline-placeholder').style.display = 'none';
    el('wipe-base-img').src = f.baseline_image;
    el('diff-base-img').src = f.baseline_image;
    el('baseline-file-info').textContent = f.baseline_image.replace('../', '');
  } else {
    el('baseline-img').style.display = 'none';
    el('baseline-placeholder').style.display = 'block';
    el('baseline-file-info').textContent = 'Missing in Baseline';
  }

  // Canary Image
  if (f.canary_exists) {
    el('socratic-img').src = f.canary_image;
    el('socratic-img').style.display = 'block';
    el('socratic-placeholder').style.display = 'none';
    el('wipe-canary-img').src = f.canary_image;
    el('diff-canary-img').src = f.canary_image;
    if (f.is_restored) {
      el('socratic-file-info').textContent = 'RESTORED BASELINE';
      el('socratic-file-info').className = 'badge badge-orange';
    } else {
      el('socratic-file-info').textContent = 'CANARY READY';
      el('socratic-file-info').className = 'badge badge-green';
    }
  } else {
    el('socratic-img').style.display = 'none';
    el('socratic-placeholder').style.display = 'block';
    el('socratic-file-info').textContent = 'PENDING RENDER';
    el('socratic-file-info').className = 'badge badge-orange';
  }

  // Arabic Script
  el('arabic-script').textContent = f.script_line || '—';

  // Badges
  const tagsRow = el('tags-row');
  tagsRow.innerHTML = '';

  const tsBadge = document.createElement('span');
  tsBadge.className = 'badge badge-blue';
  tsBadge.textContent = f.timestamp || `Frame ${f.index}`;
  tagsRow.appendChild(tsBadge);

  const durBadge = document.createElement('span');
  durBadge.className = 'badge';
  durBadge.textContent = `⏱️ ${f.duration}s (${f.frame_count}f @ 30fps)`;
  tagsRow.appendChild(durBadge);

  const archBadge = document.createElement('span');
  archBadge.className = 'badge badge-orange';
  archBadge.textContent = f.archetype;
  tagsRow.appendChild(archBadge);

  if (f.is_restored) {
    const resBadge = document.createElement('span');
    resBadge.className = 'badge badge-orange';
    resBadge.textContent = '🛡️ Restored Baseline (Audit Approved)';
    tagsRow.appendChild(resBadge);
  } else if (f.is_enhanced) {
    const enhBadge = document.createElement('span');
    enhBadge.className = 'badge badge-green';
    enhBadge.textContent = '✨ Socratic Enhanced';
    tagsRow.appendChild(enhBadge);
  }

  if (f.in_local_dir) {
    const locBadge = document.createElement('span');
    locBadge.className = 'badge badge-blue';
    locBadge.textContent = '📁 In Local Folder';
    tagsRow.appendChild(locBadge);
  }

  if (f.resolution_mismatch) {
    const misBadge = document.createElement('span');
    misBadge.className = 'badge badge-red';
    misBadge.textContent = `⚠️ AR Mismatch: ${f.resolution_mismatch}`;
    tagsRow.appendChild(misBadge);
  } else if (f.dimensions_canary) {
    const dimBadge = document.createElement('span');
    dimBadge.className = 'badge';
    dimBadge.textContent = `📐 ${f.dimensions_canary}`;
    tagsRow.appendChild(dimBadge);
  }

  (f.features || []).forEach(feat => {
    const b = document.createElement('span');
    if (feat.includes('Scale Punch') || feat.includes('Eye-Line')) {
      b.className = 'badge badge-cyan';
    } else if (feat.includes('Linear Push')) {
      b.className = 'badge badge-purple';
    } else {
      b.className = 'badge badge-green';
    }
    b.textContent = feat;
    tagsRow.appendChild(b);
  });

  if (f.duplicate_match) {
    const dupBadge = document.createElement('span');
    dupBadge.className = 'badge badge-red';
    dupBadge.textContent = `⚠️ DUPLICATE: Matches Frame #${f.duplicate_match} (${f.duplicate_hash})`;
    tagsRow.appendChild(dupBadge);
  }

  updateRegenUI();

  // Prompts
  el('socratic-prompt-text').textContent = f.socratic_prompt || '—';
  el('baseline-prompt-text').textContent = f.baseline_prompt || '—';

  // Highlight Filmstrip
  document.querySelectorAll('.film-item').forEach(fi => {
    if (fi.dataset.frameIndex == f.index) {
      fi.classList.add('active');
      fi.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    } else {
      fi.classList.remove('active');
    }
  });

  preloadLookahead(currentIndex);
}

// Split Curtain Wipe Handlers
function setWipePosition(percent) {
  wipePos = Math.max(0, Math.min(100, percent));
  document.documentElement.style.setProperty('--wipe-pos', `${wipePos}%`);
}

const wipeViewport = el('wipe-viewport');
const wipeHandle = el('wipe-handle');

function handleWipePointer(e) {
  if (!isWipeDragging) return;
  const rect = wipeViewport.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const pct = (x / rect.width) * 100;
  setWipePosition(pct);
}

wipeHandle.addEventListener('pointerdown', (e) => {
  isWipeDragging = true;
  e.preventDefault();
  wipeHandle.setPointerCapture(e.pointerId);
});

wipeHandle.addEventListener('pointermove', handleWipePointer);

const stopWipe = (e) => {
  if (isWipeDragging) {
    isWipeDragging = false;
    try { wipeHandle.releasePointerCapture(e.pointerId); } catch(ex) {}
  }
};
wipeHandle.addEventListener('pointerup', stopWipe);
wipeHandle.addEventListener('pointercancel', stopWipe);

wipeViewport.addEventListener('click', (e) => {
  if (e.target.id === 'wipe-handle') return;
  const rect = wipeViewport.getBoundingClientRect();
  const pct = ((e.clientX - rect.left) / rect.width) * 100;
  setWipePosition(pct);
});

// Pan & Zoom
function applyPanZoom() {
  el('zoom-readout').textContent = `${Math.round(zoomLevel * 100)}%`;
  const transform = `translate(${panX}px, ${panY}px) scale(${zoomLevel})`;
  document.querySelectorAll('.pan-zoom-content').forEach(element => {
    element.style.transform = transform;
  });
}

function resetZoom() {
  zoomLevel = 1.0;
  panX = 0;
  panY = 0;
  applyPanZoom();
}

document.querySelectorAll('.pan-zoom-stage, #wipe-viewport, #diff-viewport').forEach(container => {
  container.addEventListener('wheel', (e) => {
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.15 : -0.15;
    zoomLevel = Math.max(1.0, Math.min(5.0, zoomLevel + delta));
    if (zoomLevel === 1.0) { panX = 0; panY = 0; }
    applyPanZoom();
  }, { passive: false });

  container.addEventListener('pointerdown', (e) => {
    if (zoomLevel > 1.0 && (e.button === 0 || e.button === 1)) {
      isPanning = true;
      panStartX = e.clientX - panX;
      panStartY = e.clientY - panY;
      container.classList.add('panning');
      container.setPointerCapture(e.pointerId);
    }
  });

  container.addEventListener('pointermove', (e) => {
    if (isPanning) {
      panX = e.clientX - panStartX;
      panY = e.clientY - panStartY;
      applyPanZoom();
    }
  });

  const stopPan = (e) => {
    if (isPanning) {
      isPanning = false;
      container.classList.remove('panning');
      try { container.releasePointerCapture(e.pointerId); } catch(ex) {}
    }
  };
  container.addEventListener('pointerup', stopPan);
  container.addEventListener('pointercancel', stopPan);
  container.addEventListener('dblclick', resetZoom);
});
el('reset-zoom-btn').onclick = resetZoom;

// Broadcast Safe Zones Toggle
function toggleSafeZones() {
  safeZonesVisible = !safeZonesVisible;
  document.querySelectorAll('.safe-zones-svg').forEach(svg => {
    svg.style.display = safeZonesVisible ? 'block' : 'none';
  });
  el('safe-zone-btn').classList.toggle('active', safeZonesVisible);
}
el('safe-zone-btn').onclick = toggleSafeZones;

// Re-Gen Range Compressor
function compressRanges(indices) {
  const sorted = Array.from(new Set(indices)).sort((a,b) => a - b);
  if (sorted.length === 0) return "";
  const ranges = [];
  let start = sorted[0];
  let prev = sorted[0];
  for (let i = 1; i < sorted.length; i++) {
    const cur = sorted[i];
    if (cur === prev + 1) {
      prev = cur;
    } else {
      ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
      start = cur;
      prev = cur;
    }
  }
  ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
  return ranges.join(",");
}

function updateRegenUI() {
  const f = filteredFrames[currentIndex];
  el('regen-checkbox').checked = f ? selectedForRegen.has(f.index) : false;
  el('regen-count').textContent = selectedForRegen.size;
}

el('regen-checkbox').onchange = (e) => {
  const f = filteredFrames[currentIndex];
  if (!f) return;
  if (e.target.checked) selectedForRegen.add(f.index);
  else selectedForRegen.delete(f.index);
  updateRegenUI();
};

el('copy-regen-btn').onclick = () => {
  if (selectedForRegen.size === 0) {
    alert('Please select at least one frame using the checkbox.');
    return;
  }
  const compressed = compressRanges(Array.from(selectedForRegen));
  const cmd = `python tools/run_canary_benchmark.py --frames ${compressed}`;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(cmd);
  }
  alert(`Copied to clipboard:\n${cmd}`);
};

// Play / Pause media controls
function togglePlay(forceState) {
  isPlaying = (typeof forceState === 'boolean') ? forceState : !isPlaying;
  const playBtn = el('play-btn');
  if (isPlaying) {
    playBtn.textContent = '⏹ Pause (Space)';
    playBtn.classList.add('playing');
    if (clockMode === 'video' && videoProxy.src) {
      videoProxy.playbackRate = playbackRate;
      videoProxy.play().catch(() => {});
      if (MEDIA.audio_path && masterAudio.src) {
        masterAudio.playbackRate = playbackRate;
        masterAudio.currentTime = videoProxy.currentTime;
        masterAudio.play().catch(() => {});
      }
    } else if (clockMode === 'audio' && masterAudio.src) {
      masterAudio.playbackRate = playbackRate;
      masterAudio.play().catch(() => {});
    } else {
      virtualStartTime = performance.now() - (virtualCurrentTime * 1000 / playbackRate);
    }
  } else {
    playBtn.textContent = '▶ Play (Space)';
    playBtn.classList.remove('playing');
    if (clockMode === 'video' && videoProxy.src) {
      videoProxy.pause();
      if (masterAudio.src) masterAudio.pause();
    } else if (clockMode === 'audio' && masterAudio.src) {
      masterAudio.pause();
    }
  }
}
el('play-btn').onclick = () => togglePlay();

el('speed-select').onchange = (e) => {
  playbackRate = parseFloat(e.target.value) || 1.0;
  if (videoProxy.src) videoProxy.playbackRate = playbackRate;
  if (masterAudio.src) masterAudio.playbackRate = playbackRate;
};

// 60fps RAF Loop with Binary Search and Change Detection Gate
let lastActiveFrameIndex = -1;
function rafClockLoop() {
  if (isPlaying) {
    if (clockMode === 'virtual') {
      virtualCurrentTime = ((performance.now() - virtualStartTime) / 1000) * playbackRate;
      if (virtualCurrentTime >= totalDuration) {
        togglePlay(false);
        virtualCurrentTime = totalDuration;
      }
    }
    const curTime = getClockTime();
    updateScrubber(curTime);

    // Sync secondary audio if video is primary clock
    if (clockMode === 'video' && MEDIA.audio_path && masterAudio.src) {
      if (Math.abs(masterAudio.currentTime - videoProxy.currentTime) > 0.08) {
        masterAudio.currentTime = videoProxy.currentTime;
      }
    }

    const targetFrameIdx = findFrameIndexAtTime(curTime);
    if (targetFrameIdx !== -1 && targetFrameIdx !== lastActiveFrameIndex) {
      lastActiveFrameIndex = targetFrameIdx;
      const matchIdx = filteredFrames.findIndex(fr => fr.index === frames[targetFrameIdx].index);
      if (matchIdx !== -1) {
        renderFrame(matchIdx, false);
      }
    }
  }
  requestAnimationFrame(rafClockLoop);
}
requestAnimationFrame(rafClockLoop);

// Filmstrip rendering
function renderFilmstrip() {
  const strip = el('filmstrip');
  strip.innerHTML = '';
  frames.forEach(f => {
    const item = document.createElement('div');
    item.className = 'film-item' + (f.canary_exists ? ' has-canary' : '') + (f.is_restored ? ' is-restored' : '');
    item.dataset.frameIndex = f.index;
    const thumb = f.canary_exists ? f.canary_image : (f.baseline_exists ? f.baseline_image : '');
    item.innerHTML = `
      <img src="${thumb}" loading="lazy" decoding="async" onerror="this.style.opacity=0.2"/>
      <span>#${f.index}</span>
    `;
    item.onclick = () => {
      const matchIdx = filteredFrames.findIndex(fr => fr.index === f.index);
      if (matchIdx !== -1) renderFrame(matchIdx, true);
    };
    strip.appendChild(item);
  });
}

// Filter handling
function applyFilter() {
  const sel = el('filter-select').value;
  const q = el('search-input').value.toLowerCase();

  filteredFrames = frames.filter(f => {
    if (sel === 'completed' && !f.canary_exists) return false;
    if (sel === 'pending' && f.canary_exists) return false;
    if (sel === 'enhanced' && !f.is_enhanced) return false;
    if (sel === 'restored' && !f.is_restored) return false;
    if (sel === 'in_folder' && !f.in_local_dir) return false;
    if (sel === 'duplicates' && !f.duplicate_match) return false;
    if (sel.startsWith('chunk_')) {
      const cNum = parseInt(sel.replace('chunk_', ''), 10);
      if (!isNaN(cNum)) {
        const sIdx = (cNum - 1) * 50 + 1;
        const eIdx = cNum * 50;
        if (f.index < sIdx || f.index > eIdx) return false;
      }
    }
    if (sel.startsWith('archetype_')) {
      const k = sel.replace('archetype_', '').toUpperCase();
      if (!f.archetype || !f.archetype.toUpperCase().includes(k)) return false;
    }
    if (sel === 'kinetic_punch' && !(f.features && f.features.some(x => x.includes('Scale Punch')))) return false;
    if (sel === 'kinetic_push' && !(f.features && f.features.some(x => x.includes('Linear Push')))) return false;
    if (q) {
      const matchText = (f.script_line + ' ' + f.socratic_prompt + ' ' + f.baseline_prompt + ' ' + f.index).toLowerCase();
      if (!matchText.includes(q)) return false;
    }
    return true;
  });

  renderFrame(0, true);
}

// View Mode Switching
function setViewMode(mode) {
  viewMode = mode;
  el('view-mode-select').value = mode;
  const stageDual = el('stage-dual');
  const stageWipe = el('stage-wipe');
  const stageDiff = el('stage-diff');
  const panelBase = el('panel-baseline');
  const panelSoc = el('panel-socratic');

  stageDual.style.display = 'none';
  stageWipe.style.display = 'none';
  stageDiff.style.display = 'none';
  panelBase.style.display = 'flex';
  panelSoc.style.display = 'flex';

  if (mode === 'dual') {
    stageDual.style.display = 'grid';
    stageDual.style.gridTemplateColumns = '1fr 1fr';
  } else if (mode === 'baseline') {
    stageDual.style.display = 'grid';
    stageDual.style.gridTemplateColumns = '1fr';
    panelSoc.style.display = 'none';
  } else if (mode === 'socratic') {
    stageDual.style.display = 'grid';
    stageDual.style.gridTemplateColumns = '1fr';
    panelBase.style.display = 'none';
  } else if (mode === 'wipe') {
    stageWipe.style.display = 'flex';
  } else if (mode === 'diff') {
    stageDiff.style.display = 'flex';
  }
}

el('view-mode-select').onchange = (e) => setViewMode(e.target.value);
el('prev-btn').onclick = () => renderFrame(currentIndex - 1, true);
el('next-btn').onclick = () => renderFrame(currentIndex + 1, true);
el('filter-select').onchange = applyFilter;
el('search-input').oninput = applyFilter;

// Global Keyboard Navigation
window.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  const key = e.key.toLowerCase();
  if (e.key === 'ArrowLeft') { e.preventDefault(); renderFrame(currentIndex - 1, true); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); renderFrame(currentIndex + 1, true); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); renderFrame(Math.max(0, currentIndex - 5), true); }
  else if (e.key === 'ArrowDown') { e.preventDefault(); renderFrame(Math.min(filteredFrames.length - 1, currentIndex + 5), true); }
  else if (e.key === ' ') { e.preventDefault(); togglePlay(); }
  else if (key === 'p') { e.preventDefault(); togglePlay(); }
  else if (key === 'w') {
    e.preventDefault();
    setViewMode(viewMode === 'wipe' ? 'dual' : 'wipe');
  }
  else if (key === 'd') {
    e.preventDefault();
    setViewMode(viewMode === 'diff' ? 'dual' : 'diff');
  }
  else if (key === 's') {
    e.preventDefault();
    toggleSafeZones();
  }
  else if (key === 'z') {
    e.preventDefault();
    resetZoom();
  }
  else if (key >= '1' && key <= '9') {
    const pct = parseInt(key, 10) * 10;
    setWipePosition(pct);
  }
});

// Initialization
updateStats();
renderFilmstrip();
let initIdx = frames.findIndex(f => f.in_local_dir && f.canary_exists);
if (initIdx === -1) initIdx = frames.findIndex(f => f.canary_exists);
if (initIdx === -1) initIdx = 0;
renderFrame(initIdx, true);
</script>
</body>
</html>
"""
    rendered_html = html_content.replace("__CHUNK_OPTIONS__", chunk_options_html).replace("__STUDIO_DATA_JSON__", json_data)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(rendered_html)

    studio_alias = os.path.join(canary_path, "studio_viewer.html")
    if os.path.abspath(out_file) != os.path.abspath(studio_alias):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(studio_alias)), exist_ok=True)
            if os.path.dirname(os.path.abspath(studio_alias)) == html_dir:
                alias_rendered = rendered_html
            else:
                alias_records = build_frame_records(run_dir, canary_path, html_dir=canary_path)
                alias_media = resolve_media_assets(run_dir, canary_path)
                alias_payload = {"media": alias_media, "frames": alias_records}
                alias_json = json.dumps(alias_payload, ensure_ascii=False)
                alias_rendered = html_content.replace("__CHUNK_OPTIONS__", chunk_options_html).replace("__STUDIO_DATA_JSON__", alias_json)
            with open(studio_alias, "w", encoding="utf-8") as f:
                f.write(alias_rendered)
        except Exception:
            pass

    # Ensure run root studio_viewer.html is synchronized if out_file is inside a subfolder
    root_alias = os.path.join(run_dir, "studio_viewer.html")
    if os.path.abspath(out_file) != os.path.abspath(root_alias) and os.path.abspath(studio_alias) != os.path.abspath(root_alias):
        try:
            root_records = build_frame_records(run_dir, canary_path, html_dir=run_dir)
            root_media = resolve_media_assets(run_dir, run_dir)
            root_payload = {"media": root_media, "frames": root_records}
            root_json = json.dumps(root_payload, ensure_ascii=False)
            root_rendered = html_content.replace("__CHUNK_OPTIONS__", chunk_options_html).replace("__STUDIO_DATA_JSON__", root_json)
            with open(root_alias, "w", encoding="utf-8") as f:
                f.write(root_rendered)
        except Exception:
            pass
    return out_file


generate_studio_viewer_html = generate_comparison_viewer_html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Side-by-Side Comparison HTML Studio")
    parser.add_argument("--run-dir", required=True, help="Path to production run folder")
    parser.add_argument("--canary-dir", default=None, help="Directory containing canary images")
    parser.add_argument("--output", help="Optional output HTML file path")
    args = parser.parse_args()

    out_file = generate_comparison_viewer_html(args.run_dir, canary_dir=args.canary_dir, output_html=args.output)
    print(f"Comparison studio generated at: {out_file}")


if __name__ == "__main__":
    main()
