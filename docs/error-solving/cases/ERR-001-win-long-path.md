# Case ID: ERR-001-win-long-path

## Overview
- **Title**: Windows Explorer Long Path Video Playback Failure (File System Error -2147219196)
- **Responsible Layer**: os.filesystem
- **Status**: resolved
- **Date Recorded**: 2026-10-23
- **Affected Components**: Production review output, preview video playback, Windows shell invocation

## 1. Verified Facts
- Deep nesting of output directories under `youtube_runs/` (repository path + run folder + adaptive_renders + generation hash + preview filename) exceeds 260-350 characters.
- Double-clicking generated MP4 files in Windows File Explorer triggers default UWP media player (Films & TV / Windows Media Player), which fails with dialogs: `Explorer.EXE: The app didn't start` and `Explorer.EXE: File system error (-2147219196)`.
- The video files themselves are completely valid and uncorrupted; Win32 players (VLC, mpv) or Chromium browsers open them without error.

## 2. Hypotheses
- Default Windows UWP application host does not inherit long path awareness (`\\?\` prefix or manifest `longPathAware`) when launched via Explorer shell verbs.
- Confidence: high.

## 3. Attempts and Outcomes
- **Attempt 1**: Enable long path registry key `LongPathsEnabled=1` globally.
  - *Outcome*: Resolves console and Win32 applications, but default UWP app associations still fail when double-clicked through File Explorer.
- **Attempt 2**: Copy/symlink preview and master video artifacts to convenient short paths on user Desktop or workspace root during production review milestones.
  - *Outcome*: Succeeded. User double-click works seamlessly without modifying system UWP bindings.

## 4. Remaining Gaps & False-Positive Boundaries
- **Boundaries**: Applies specifically to Explorer double-click execution of video files exceeding MAX_PATH (260 chars). Does not apply to Python file operations using extended-length paths.
- **Gaps**: None.

## 5. Verified Prevention Check
- **Rule / Guard**: Expose convenient short-path links or copies of preview MP4s in review directories.
- **Verification**: `tests/unit/test_production_render.py`

## 6. Evidence Links
- **Legacy Register**: [`docs/error-solving/understood-errors.md#windows-explorer-long-path-video-playback-failure-file-system-error--2147219196`](file:///C:/Users/Snoozer/teamwork_projects/architecture-renewal-campaign/docs/error-solving/understood-errors.md)
- **Source Code**: [`src/youtube_automation/production/render.py`](file:///C:/Users/Snoozer/teamwork_projects/architecture-renewal-campaign/src/youtube_automation/production/render.py)
