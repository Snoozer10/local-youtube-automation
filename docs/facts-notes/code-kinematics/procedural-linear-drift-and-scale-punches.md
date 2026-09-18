# Note: Procedural Linear Drift & Discrete Scale Punches

**Category:** Kinematics  
**Date Logged:** 2026-09-16  
**Relevant Code Files:** `src/youtube_automation/video/ken_burns.py`, `src/youtube_automation/video/compiler.py`, `src/youtube_automation/video/filter_graph.py`  
**Audit Reference:** Section 6.4 (Module 6D)  

### 1. Core Rule in Plain English
Static holds longer than 3.5 seconds must execute a continuous linear Ken Burns push (100% to 103%) using zero-safe clamped evaluation `min(1.03,1.0+0.03*(clip(on,0,frames)/max(1,frames)))`, eliminating dead holds without triggering negative pops at `on=0` or division-by-zero crashes. Emphatic keyword moments in long holds (>= 4.0s) trigger sub-beat scale punches (125%) via discrete timeline subdivision into two sequential clips (`static_hold` setup + `scale_punch` close-up) locked to the upper-third eye-line elevation (Y=360px in 1080p).

### 2. The Failure Mode It Prevents
Raw linear interpolation expressions like `((on-1)/(d-1))` evaluate to negative values at frame `on=0` (causing an instantaneous -1 negative zoom pop) and trigger fatal division-by-zero crashes in libavfilter when clip duration is 1 frame (`d=1`). Attempting mid-stream stepped scale jumps within a single FFmpeg clip triggers severe P-frame macroblocking and PTS desync on hardware encoders like Intel QSV (`h264_qsv` with `lookahead=0`, `format=nv12`). Centering zoom into geometric midpoint (Y=0.5) jumps the character's eye-line upward across cuts, causing disorienting ocular saccades for viewers.

### 3. Implementation Specification
1. **Zero-Safe Clamped Linear Push (`build_ken_burns_filter`)**:
   ```python
   if duration >= 3.5:
       z_expr = f"min(1.03,1.0+0.03*(clip(on,0,{frames})/max(1,{frames})))"
   else:
       z_expr = "1.0"
   x_expr = safe_center_x
   y_expr = safe_center_y
   ```

2. **Eye-Line Elevation Anchor (`scale_punch` & `derive_multishot_crop`)**:
   ```python
   elif "scale_punch" in camera_action:
       z_expr = "1.25"
       x_expr = safe_center_x
       # Locks vertical viewport to upper-third eye-line elevation (Y=360px in 1080p)
       y_expr = "trunc(max(0,min(ih-ih/zoom,(ih-ih/zoom)/3.0)))"
   ```

3. **Discrete Timeline Subdivision (`prepare_synchronized_timeline`)**:
   ```python
   if punch_info and 18 <= punch_info["relative_frame"] <= frame_count - 18:
       rel_f = punch_info["relative_frame"]
       split_frame = start_frame + rel_f
       # Sub-shot 1: Setup
       final_timeline.append({
           "name": name, "start_frame": start_frame, "end_frame": split_frame,
           "frame_count": rel_f, "camera_action": "static_hold", "occurrence": occurrence, ...
       })
       # Sub-shot 2: Scale Punch reaction
       final_timeline.append({
           "name": name, "start_frame": split_frame, "end_frame": end_frame,
           "frame_count": frame_count - rel_f, "camera_action": "scale_punch", "occurrence": occurrence, ...
       })
   ```

### 4. Verification Check
- Run unit test suite: `python -m pytest tests/unit/test_procedural_kinematics.py -v` (5/5 PASS).
- Verify mathematically that at `on=0`, `clip(0, 0, d) / max(1, d) == 0.0` (zero pop).
- Verify that `crop_w`, `crop_h`, `crop_x`, `crop_y` from `derive_multishot_crop` are all even integers conforming to NV12 subsampling and BT.709 color matrix.
- Verify that total frames before and after subdivision remain identical down to the exact sample (`hold_frames + punch_frames == total_frames`).
