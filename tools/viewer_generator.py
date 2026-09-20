"""Interactive Side-by-Side HTML Comparison Viewer Generator.

Generates a standalone, responsive, dark-mode HTML comparison studio
linking baseline generated images and Socratic canary images side-by-side
with Arabic spoken subtitles, prompt diffs, and interactive keyboard navigation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
    """Generates the complete, self-contained HTML comparison studio."""
    canary_path = canary_dir or os.path.join(run_dir, "canary_images")
    out_file = output_html or os.path.join(canary_path, "canary_comparison_viewer.html")
    html_dir = os.path.dirname(os.path.abspath(out_file))
    records = build_frame_records(run_dir, canary_path, html_dir=html_dir)

    json_data = json.dumps(records, ensure_ascii=False)

    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Socratic Visual Prompt Comparison Studio</title>
<style>
:root {
  --bg-primary: #0d1117;
  --bg-secondary: #161b22;
  --bg-card: #21262d;
  --border: #30363d;
  --text-main: #f0f6fc;
  --text-muted: #8b949e;
  --accent-blue: #58a6ff;
  --accent-green: #3fb950;
  --accent-orange: #d29922;
  --accent-red: #f85149;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  background-color: var(--bg-primary);
  color: var(--text-main);
  line-height: 1.5;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}
header {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  padding: 10px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.logo-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.logo-title h1 {
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--accent-blue);
}
.stats-badge {
  font-size: 0.8rem;
  background: var(--bg-card);
  padding: 4px 10px;
  border-radius: 20px;
  border: 1px solid var(--border);
  color: var(--text-muted);
}
.controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
select, input {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-main);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 0.85rem;
  outline: none;
}
select:focus, input:focus {
  border-color: var(--accent-blue);
}
.btn {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-main);
  padding: 6px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.15s;
}
.btn:hover {
  background: #30363d;
}
.btn.active {
  background: var(--accent-blue);
  color: #0d1117;
  border-color: var(--accent-blue);
  font-weight: 600;
}
main {
  display: flex;
  flex: 1;
  overflow: hidden;
}
.stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px;
  overflow-y: auto;
  gap: 16px;
}
.comparison-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  flex: 1;
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
  font-size: 0.85rem;
  font-weight: 600;
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
.img-container img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  display: block;
}
.img-placeholder {
  color: var(--text-muted);
  font-size: 0.9rem;
  text-align: center;
  padding: 20px;
}
.meta-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.arabic-script {
  font-size: 1.35rem;
  direction: rtl;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  color: #fff;
  line-height: 1.8;
  padding: 6px 10px;
  background: var(--bg-card);
  border-radius: 6px;
}
.tags-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.badge {
  font-size: 0.75rem;
  padding: 3px 8px;
  border-radius: 12px;
  border: 1px solid var(--border);
}
.badge-blue { background: #1f3a5f; color: #58a6ff; border-color: #388bfd; }
.badge-green { background: #1c4423; color: #3fb950; border-color: #238636; }
.badge-orange { background: #432b13; color: #d29922; border-color: #9e6a03; }
.badge-cyan { background: #0b3d4f; color: #00e5ff; border-color: #00b4d8; font-weight: 600; }
.badge-purple { background: #3b1b54; color: #d187ff; border-color: #a855f7; font-weight: 600; }
.prompt-diff {
  font-size: 0.8rem;
  color: var(--text-muted);
  max-height: 110px;
  overflow-y: auto;
  background: var(--bg-primary);
  padding: 8px 12px;
  border-radius: 6px;
  font-family: monospace;
}
footer {
  height: 100px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 8px 16px;
  gap: 10px;
  overflow-x: auto;
  white-space: nowrap;
}
.film-item {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 6px;
  border-radius: 6px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  cursor: pointer;
  min-width: 90px;
  transition: all 0.15s;
}
.film-item:hover, .film-item.active {
  border-color: var(--accent-blue);
  background: #28303d;
}
.film-item img {
  width: 76px;
  height: 42px;
  object-fit: cover;
  border-radius: 4px;
  background: #000;
}
.film-item span {
  font-size: 0.7rem;
  color: var(--text-muted);
}
.film-item.has-canary {
  border-bottom: 3px solid var(--accent-green);
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
    <span id="frame-counter" style="font-weight: 600; font-size: 0.9rem;">Frame 1 / 293</span>
    <button class="btn" id="next-btn" title="Next Frame (Right Arrow)">Next ▶</button>
    <select id="filter-select">
      <option value="all">Show All Frames (293)</option>
      <option value="chunk_1">Chunk 1: Frames 1–50</option>
      <option value="chunk_2">Chunk 2: Frames 51–100</option>
      <option value="chunk_3">Chunk 3: Frames 101–150</option>
      <option value="chunk_4">Chunk 4: Frames 151–200</option>
      <option value="chunk_5">Chunk 5: Frames 201–250</option>
      <option value="chunk_6">Chunk 6: Frames 251–293</option>
      <option value="enhanced">Socratic Enhanced Only (286)</option>
      <option value="restored">Restored Baseline Only (7)</option>
      <option value="in_folder">In This Folder Only</option>
      <option value="completed">Canary Ready Only</option>
      <option value="pending">Pending Canary Only</option>
      <option value="archetype_hook">Hook (ISOLATED_WHITE)</option>
      <option value="archetype_diagram">Dissection (DIAGRAM)</option>
      <option value="archetype_machine">Analogy (MACHINE)</option>
      <option value="archetype_blueprint">Scientific (BLUEPRINT)</option>
      <option value="archetype_museum">Parody (MUSEUM)</option>
      <option value="kinetic_punch">⚡ Scale Punches (125%)</option>
      <option value="kinetic_push">🎥 Linear Pushes (103%)</option>
    </select>
    <input type="text" id="search-input" placeholder="Search prompt / script..." style="width: 180px;"/>
    <button class="btn" id="toggle-mode-btn" title="Spacebar flips view">Toggle Focus</button>
    <div style="display:flex; gap:8px; align-items:center;">
      <label style="cursor:pointer; display:flex; align-items:center; gap:4px; font-size:12px; color:#c9d1d9;">
        <input type="checkbox" id="regen-checkbox" style="cursor:pointer;"/> Re-Gen
      </label>
      <button class="btn" id="copy-regen-btn" style="background:#238636; font-size:12px;" title="Copy CLI command for selected frames">📋 Copy Re-Gen (<span id="regen-count">0</span>)</button>
      <button class="btn" id="play-btn" style="background:#8957e5; font-size:12px;" title="Play macro-scene (P)">▶ Play (P)</button>
    </div>
  </div>
</header>

<main>
  <div class="stage">
    <div class="comparison-grid" id="comp-grid">
      <div class="panel" id="panel-baseline">
        <div class="panel-header">
          <span class="tag-baseline">BASELINE (Plan v4)</span>
          <span id="baseline-file-info" style="font-size:0.75rem; color:#8b949e;">generated_images_baseline/...</span>
        </div>
        <div class="img-container">
          <img id="baseline-img" src="" alt="Baseline Frame"/>
          <div class="img-placeholder" id="baseline-placeholder" style="display:none;">Baseline image not found</div>
        </div>
      </div>
      <div class="panel" id="panel-socratic">
        <div class="panel-header">
          <span class="tag-socratic">SOCRATIC (NotebookLM Enhanced)</span>
          <span id="socratic-file-info" class="badge badge-green">canary_images/...</span>
        </div>
        <div class="img-container">
          <img id="socratic-img" src="" alt="Socratic Canary Frame"/>
          <div class="img-placeholder" id="socratic-placeholder" style="display:none;">Generation pending in Google Flow</div>
        </div>
      </div>
    </div>

    <div class="meta-section">
      <div class="arabic-script" id="arabic-script">...</div>
      <div class="tags-row" id="tags-row"></div>
      <div class="prompt-diff" id="prompt-diff"></div>
    </div>
  </div>
</main>

<footer id="filmstrip"></footer>

<script>
const frames = __JSON_DATA__;
let currentIndex = 0;
let filteredFrames = [...frames];
let focusMode = 0; // 0: both, 1: baseline only, 2: socratic only

const el = id => document.getElementById(id);

function updateStats() {
  const completed = frames.filter(f => f.canary_exists).length;
  const enhanced = frames.filter(f => f.is_enhanced).length;
  const restored = frames.filter(f => f.is_restored).length;
  const localCount = frames.filter(f => f.in_local_dir).length;
  el('stats-badge').textContent = `${completed}/${frames.length} Ready (${enhanced} Enhanced, ${restored} Restored, ${localCount} in folder)`;
}

function renderFrame(index) {
  if (filteredFrames.length === 0) return;
  if (index < 0) index = 0;
  if (index >= filteredFrames.length) index = filteredFrames.length - 1;
  currentIndex = index;

  const f = filteredFrames[currentIndex];
  el('frame-counter').textContent = `Frame ${f.index} / ${frames.length} [${f.timestamp}]`;

  // Baseline Image
  if (f.baseline_exists) {
    el('baseline-img').src = f.baseline_image;
    el('baseline-img').style.display = 'block';
    el('baseline-placeholder').style.display = 'none';
    el('baseline-file-info').textContent = f.baseline_image.replace('../', '');
  } else {
    el('baseline-img').style.display = 'none';
    el('baseline-placeholder').style.display = 'block';
    el('baseline-file-info').textContent = 'Missing in Baseline';
  }

  // Socratic Image
  if (f.canary_exists) {
    el('socratic-img').src = f.canary_image;
    el('socratic-img').style.display = 'block';
    el('socratic-placeholder').style.display = 'none';
    if (f.is_restored) {
      el('socratic-file-info').textContent = 'RESTORED BASELINE';
      el('socratic-file-info').className = 'badge badge-orange';
    } else {
      el('socratic-file-info').textContent = 'SOCRATIC READY';
      el('socratic-file-info').className = 'badge badge-green';
    }
  } else {
    el('socratic-img').style.display = 'none';
    el('socratic-placeholder').style.display = 'block';
    el('socratic-file-info').textContent = 'PENDING RENDER';
    el('socratic-file-info').className = 'badge badge-orange';
  }

  // Script text
  el('arabic-script').textContent = f.script_line || '—';

  // Badges
  const tagsRow = el('tags-row');
  tagsRow.innerHTML = '';

  const tsBadge = document.createElement('span');
  tsBadge.className = 'badge badge-blue';
  tsBadge.textContent = f.timestamp || `Frame ${f.index}`;
  tagsRow.appendChild(tsBadge);

  const archBadge = document.createElement('span');
  archBadge.className = 'badge badge-orange';
  archBadge.textContent = f.archetype;
  tagsRow.appendChild(archBadge);

  if (f.is_restored) {
    const resBadge = document.createElement('span');
    resBadge.className = 'badge badge-orange';
    resBadge.style = 'background:#54381e; color:#ffb020; border-color:#9e6a03; font-weight:bold;';
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

  f.features.forEach(feat => {
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
    dupBadge.className = 'badge';
    dupBadge.style = 'background:#d90429; color:#fff; font-weight:bold; box-shadow:0 0 10px rgba(217,4,41,0.6);';
    dupBadge.textContent = `⚠️ DUPLICATE: Matches Frame #${f.duplicate_match} (${f.duplicate_hash})`;
    tagsRow.appendChild(dupBadge);
  }

  updateRegenUI();

  // Prompt diff
  el('prompt-diff').innerHTML = `<strong>Socratic Enhanced Prompt:</strong><br/>${f.socratic_prompt}<br/><br/><strong>Baseline Prompt:</strong><br/>${f.baseline_prompt}`;

  // Highlight filmstrip item
  document.querySelectorAll('.film-item').forEach((fi) => {
    if (fi.dataset.frameIndex == f.index) {
      fi.classList.add('active');
      fi.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    } else {
      fi.classList.remove('active');
    }
  });
}

let selectedForRegen = new Set();
let isPlaying = false;
let playTimer = null;

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
  const framesList = Array.from(selectedForRegen).sort((a,b)=>a-b).join(',');
  const cmd = `python tools/run_canary_benchmark.py --frames ${framesList}`;
  navigator.clipboard.writeText(cmd);
  alert(`Copied to clipboard:\n${cmd}`);
};

function togglePlay() {
  isPlaying = !isPlaying;
  el('play-btn').textContent = isPlaying ? '⏹ Pause (P)' : '▶ Play (P)';
  el('play-btn').style.background = isPlaying ? '#da3633' : '#8957e5';
  if (isPlaying) {
    playTimer = setInterval(() => {
      if (currentIndex >= filteredFrames.length - 1) {
        togglePlay();
      } else {
        renderFrame(currentIndex + 1);
      }
    }, 2500);
  } else {
    clearInterval(playTimer);
  }
}
el('play-btn').onclick = togglePlay;

function renderFilmstrip() {
  const strip = el('filmstrip');
  strip.innerHTML = '';
  frames.forEach(f => {
    const item = document.createElement('div');
    item.className = 'film-item' + (f.canary_exists ? ' has-canary' : '');
    item.dataset.frameIndex = f.index;
    const thumb = f.canary_exists ? f.canary_image : (f.baseline_exists ? f.baseline_image : '');
    item.innerHTML = `
      <img src="${thumb}" loading="lazy" decoding="async" onerror="this.style.opacity=0.2"/>
      <span>#${f.index} ${f.timestamp}</span>
    `;
    item.onclick = () => {
      const matchIdx = filteredFrames.findIndex(fr => fr.index === f.index);
      if (matchIdx !== -1) renderFrame(matchIdx);
    };
    strip.appendChild(item);
  });
}

function applyFilter() {
  const sel = el('filter-select').value;
  const q = el('search-input').value.toLowerCase();

  filteredFrames = frames.filter(f => {
    if (sel === 'completed' && !f.canary_exists) return false;
    if (sel === 'pending' && f.canary_exists) return false;
    if (sel === 'enhanced' && !f.is_enhanced) return false;
    if (sel === 'restored' && !f.is_restored) return false;
    if (sel === 'in_folder' && !f.in_local_dir) return false;
    if (sel === 'chunk_1' && (f.index < 1 || f.index > 50)) return false;
    if (sel === 'chunk_2' && (f.index < 51 || f.index > 100)) return false;
    if (sel === 'chunk_3' && (f.index < 101 || f.index > 150)) return false;
    if (sel === 'chunk_4' && (f.index < 151 || f.index > 200)) return false;
    if (sel === 'chunk_5' && (f.index < 201 || f.index > 250)) return false;
    if (sel === 'chunk_6' && (f.index < 251 || f.index > 293)) return false;
    if (sel.startsWith('archetype_')) {
      const k = sel.replace('archetype_', '').toUpperCase();
      if (!f.archetype.toUpperCase().includes(k)) return false;
    }
    if (sel === 'kinetic_punch' && !f.features.some(x => x.includes('Scale Punch'))) return false;
    if (sel === 'kinetic_push' && !f.features.some(x => x.includes('Linear Push'))) return false;
    if (q) {
      const matchText = (f.script_line + ' ' + f.socratic_prompt + ' ' + f.baseline_prompt + ' ' + f.index).toLowerCase();
      if (!matchText.includes(q)) return false;
    }
    return true;
  });

  renderFrame(0);
}

function toggleFocus() {
  focusMode = (focusMode + 1) % 3;
  const pBase = el('panel-baseline');
  const pSoc = el('panel-socratic');
  const grid = el('comp-grid');

  if (focusMode === 0) {
    grid.style.gridTemplateColumns = '1fr 1fr';
    pBase.style.display = 'flex';
    pSoc.style.display = 'flex';
    el('toggle-mode-btn').textContent = 'View: Dual';
  } else if (focusMode === 1) {
    grid.style.gridTemplateColumns = '1fr';
    pBase.style.display = 'flex';
    pSoc.style.display = 'none';
    el('toggle-mode-btn').textContent = 'View: Baseline';
  } else {
    grid.style.gridTemplateColumns = '1fr';
    pBase.style.display = 'none';
    pSoc.style.display = 'flex';
    el('toggle-mode-btn').textContent = 'View: Socratic';
  }
}

el('prev-btn').onclick = () => renderFrame(currentIndex - 1);
el('next-btn').onclick = () => renderFrame(currentIndex + 1);
el('filter-select').onchange = applyFilter;
el('search-input').oninput = applyFilter;
el('toggle-mode-btn').onclick = toggleFocus;

window.onkeydown = e => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'ArrowLeft') renderFrame(currentIndex - 1);
  if (e.key === 'ArrowRight') renderFrame(currentIndex + 1);
  if (e.key === 'ArrowUp') renderFrame(Math.max(0, currentIndex - 5));
  if (e.key === 'ArrowDown') renderFrame(Math.min(filteredFrames.length - 1, currentIndex + 5));
  if (e.key === ' ') { e.preventDefault(); toggleFocus(); }
  if (e.key.toLowerCase() === 'p') { e.preventDefault(); togglePlay(); }
};

updateStats();
renderFilmstrip();
let initIdx = frames.findIndex(f => f.in_local_dir && f.canary_exists);
if (initIdx === -1) initIdx = frames.findIndex(f => f.canary_exists);
if (initIdx === -1) initIdx = 0;
renderFrame(initIdx);
</script>
</body>
</html>
"""
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html_content.replace("__JSON_DATA__", json_data))
    studio_alias = os.path.join(canary_path, "studio_viewer.html")
    if os.path.abspath(out_file) != os.path.abspath(studio_alias):
        if os.path.dirname(os.path.abspath(studio_alias)) == html_dir:
            alias_json = json_data
        else:
            alias_records = build_frame_records(run_dir, canary_path, html_dir=canary_path)
            alias_json = json.dumps(alias_records, ensure_ascii=False)
        try:
            with open(studio_alias, "w", encoding="utf-8") as f:
                f.write(html_content.replace("__JSON_DATA__", alias_json))
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
