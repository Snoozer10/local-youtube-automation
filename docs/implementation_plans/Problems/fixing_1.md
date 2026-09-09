As the CEO, you hold ultimate strategic, structural, and technical responsibility for the project. You do not apply shallow patches or pass on incomplete work; you take a macro-view of the workspace, diagnose errors at their absolute root cause, and ensure the entire pipeline executes cleanly and efficiently.

Your immediate objective is to rescue, repair, and fully automate the execution of `compile_video.py`, which is currently crashing mid-run.

# Target File & Environment

- **Target Script:** `compile_video.py`
- **Operating Workspace:** Antigravity Automation Suite (Python + Playwright + FFmpeg pipeline)
- **The Output Goal:** A fully generated, flawless, animated, and annotated video file (`youtube_ready_video.mp4`) containing all planned audio and image clips.

---

# The Diagnostic Evidence (Fatal Error Log)

When `compile_video.py` is executed, the terminal reports the following failure during the single-pass FFmpeg render:

```text
[Single-Pass] Rendering 116 clips + audio + subs in one FFmpeg...
  [ERROR] FFmpeg failed:
-filter_complex_script is deprecated, use -/filter_complex C:\Users\Snoozer\Downloads\Antigravity\Youtube Automation 2\buckup\Version 4 before deepseek implementation plan\image_generation\youtube_runs\Everyday Habits That Boost Brain Power\filter_complex.txt instead
[aist#116:0/pcm_s16le @ 00000227ef01b640] Guessed Channel Layout: mono
Incompatible pixel format 'yuv420p' for codec 'h264_qsv', auto-selecting format 'nv12'
[swscaler @ 00000228e0c82080] deprecated pixel format used, make sure you did set range correctly
[swscaler @ 000002290cfbb100] deprecated pixel format used, make sure you did set range correctly
[h264_qsv @ 00000227ef004080] Invalid FrameType:0.
[vost#0:0/h264_qsv @ 00000227e4a4d000] [enc:h264_qsv @ 00000227e443a180] Error submitting video frame to the encoder
[vost#0:0/h264_qsv @ 00000227e4a4d000] [enc:h264_qsv @ 00000227e443a180] Error encoding a frame: Invalid data found when processing input
[vost#0:0/h264_qsv @ 00000227e4a4d000] Task finished with error code: -1094995529 (Invalid data found when processing input)
[vost#0:0/h264_qsv @ 00000227e4a4d000] Terminating thread with return code -1094995529 (Invalid data found when processing input)

[ERROR] Single-pass render failed.
```

CEO Strategic Directives for Resolution

As the CEO Agent, analyze and implement solutions for the following technical
flaws identified in the log:

1.  Deprecated Argument Fix: Swap the deprecated -filter_complex_script argument
    in the FFmpeg command generation to the modern and supported -filter_complex
    path argument.
2.  QSV Hardware Encoder Crash (Invalid FrameType:0): The hardware encoder
    (h264_qsv) is failing to process the raw frames passed to it from the filter
    complex. You must:
      - Implement an Automatic Software Fallback: Modify the FFmpeg execution
        block so that if the hardware-accelerated h264_qsv encoder fails (or if
        any rendering exception is caught), the script automatically falls back
        to the highly stable software-based libx264 encoder and retries the
        render.
      - Explicit Pixel Format Allocation: In the FFmpeg arguments, explicitly
        map the input stream pixel formats to nv12 or yuv420p (e.g., adding
        format=nv12 or format=yuv420p in your video filter arguments) so the
        encoder does not have to guess.
3.  Clip Validation: Add a pre-compilation sanity check to verify that all 116
    assets/clips exist on disk and have non-zero file sizes before feeding them
    into the FFmpeg command.

Operational Workflow Phases

You must execute your work systematically in these four sequential phases:

Phase 1: Code & Workspace Diagnostics

  - Meticulously scan compile_video.py and its configuration paths.
  - Locate the section of the script generating the FFmpeg arguments and the
    filter script file.
  - Proactively consult any workspace design rules or AGENTS.md skills guides
    present in the workspace directory to ensure your modifications follow
    existing project standards.

Phase 2: Surgical Implementation

  - Apply targeted, precise edits to the FFmpeg execution and fallback blocks in
    compile_video.py.
  - Do not rewrite the entire file; keep your modifications scoped directly to
    fixing the encoder pipeline and adding the libx264 fallback trigger.

Phase 3: Automated Compilation Test

  - Run the compiled script: python compile_video.py
  - Actively monitor the standard output and ensure QSV either executes
    correctly or triggers your new software encoder fallback seamlessly.

Phase 4: Output Quality Verification (The Cycle)

  - Programmatically verify the output file (youtube_ready_video.mp4). Ensure:
    1.  The video compiles completely without terminating midway.
    2.  The file size is healthy and the video plays beyond a single frozen
        frame.
    3.  Multiple distinct images are sequencing smoothly alongside the audio
        track.
  - If errors or rendering bugs occur, adjust your logic and repeat this cycle
    (Fix -> Test -> Verify) recursively until a perfect output is achieved.

Do not yield back to the user or mark this task as completed until you have
successfully executed compile_video.py fully, resulting in a validated, highly
animated output video.

