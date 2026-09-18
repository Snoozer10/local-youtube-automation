# Note: Automated Broadcast Assembly & Kinetic Studio Validation

**Category:** Kinematics  
**Date Logged:** 2026-09-16  
**Relevant Code Files:** `compile_video.py`, `src/youtube_automation/video/compiler.py`, `tools/viewer_generator.py`  
**Audit Reference:** Section 5, Section 6.4 (Module 6D)  

### 1. Core Rule in Plain English
Automated recompilation of long-form 16:9 broadcast masters must dynamically enrich canonical timeline spans with procedural kinetic metadata (`camera_action`, `drift_type`, `eye_line_elevation`, `punch_frame`) and synchronize SHA-256 sidecars before rendering. Synchronized timelines must subdivide long holds ($\ge 4.0\text{s}$) at acoustic transients into discrete setup (`static_hold`) and reaction (`scale_punch`) sub-shots while preserving identical asset occurrence integer mapping and sample-exact frame budgeting ($\sum \text{frames} = 40,035$ at 30 fps). Comparison studios must surface kinetic badges with vibrant dark-mode distinction (`badge-cyan` for Scale Punches and Eye-Line Locks, `badge-purple` for Linear Pushes).

### 2. The Failure Mode It Prevents
1. **Sidecar Desync & Aborts**: Modifying `timeline.json` without updating the SHA-256 sidecars (`image_timestamps.txt.sha256`, `timestamped_transcript.txt.sha256`, etc.) triggers fatal `ValueError: Stale timeline shim detected` during ingestion.
2. **Kinetic Action Erasure**: If non-subdivided spans omit `camera_action`, generic animation loops override them with cyclic pan/tilt motions (`pool[global_idx % len(pool)]`), completely destroying intentional linear push drifts.
3. **Mid-Stream Macroblocking**: Attempting to apply stepped scale punches inside a single FFmpeg filtergraph violates Intel QuickSync / hardware encoder constraints (`lookahead=0`, `format=nv12`), causing P-frame corruption and PTS timeline jitter.
4. **Ocular Saccades**: Unconstrained scaling into geometric screen centers jumps eye-lines vertically; anchoring scale punches to $Y = 360\text{px}$ ($1/3$ elevation in 1080p) preserves optical gaze stability across cuts.

### 3. Implementation Specification
1. **Automated Kinetic Enrichment & Sidecar Sync (`enrich_timeline_kinetics`)**:
   ```python
   def enrich_timeline_kinetics(run_folder: str, fps: int = 30) -> dict:
       detector = AudioTransientDetector(wav_path=audio_path, sample_rate=16000)
       for s in spans:
           s["eye_line_elevation"] = 360
           if detector and dur >= 4.0 and fc >= 60:
               punch_info = detector.find_best_scale_punch_frame(...)
           if punch_info and 18 <= punch_info["relative_frame"] <= fc - 18:
               s["camera_action"] = "scale_punch"
               s["punch_frame"] = punch_info["relative_frame"]
               s["drift_type"] = "scale_punch_125"
           else:
               s["camera_action"] = "linear_push" if dur >= 3.5 else "static_hold"
               s["drift_type"] = "linear_push_103" if dur >= 3.5 else "static_hold"
       save_timeline_and_shims(timeline_data, run_folder, export_srt=True)
   ```

2. **Kinetic Camera Action Pass-Through (`prepare_synchronized_timeline`)**:
   ```python
   final_timeline.append({
       "name": name, "start_frame": start_frame, "end_frame": end_frame,
       "camera_action": span.get("camera_action") or ("linear_push" if span_dur >= 3.5 else "static_hold"),
       ...
   })
   ```

3. **Comparison Studio Badging (`viewer_generator.py`)**:
   ```javascript
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
   ```

### 4. Verification Check
- Verify that `load_timeline_or_shim` and `verify_shim` succeed with zero errors.
- Confirm total frames across all 446 synchronized clips sum to exactly 40,035 frames ($1334.50\text{s}$ at 30 fps).
- Confirm `validate_assets` reports 0 invalid/missing images.
- Verify that `youtube_ready_video.mp4` passes `verify_master_video()` and `validate_post_encode()`.
- Regenerate and verify `studio_viewer.html` across all comparison chunk directories.
