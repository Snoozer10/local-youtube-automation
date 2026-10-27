# Case ID: ERR-002-qsv-lookahead

## Overview
- **Title**: Intel QSV Lookahead Stream Corruption
- **Responsible Layer**: video.qsv
- **Status**: resolved
- **Date Recorded**: 2026-10-23
- **Affected Components**: Hardware video encoding, FFmpeg encoder parameters (`h264_qsv`)

## 1. Verified Facts
- Configuring `-look_ahead 1` with a non-zero `-look_ahead_depth` on Intel QSV (`h264_qsv`) hardware encoder when feeding software-decoded frames causes frame pool exhaustion in the hardware memory driver.
- The output video bitstream suffers silent corruption (missing pictures in access units, invalid NAL unit sizes).
- FFmpeg exits with return code 0, masking the bitstream defect from basic subprocess returncode checks.

## 2. Hypotheses
- Hybrid software-to-hardware transcode chains exhaust driver-allocated surface buffers when lookahead buffering is enabled on this specific hardware/driver baseline.
- Confidence: high.

## 3. Attempts and Outcomes
- **Attempt 1**: Increase frame allocation buffer sizes.
  - *Outcome*: Delayed but did not prevent surface starvation on longer video clips.
- **Attempt 2**: Disable lookahead by setting `QSV_LOOKAHEAD=0` in video compiler configuration.
  - *Outcome*: Succeeded. Zero bitstream corruption across all render lengths.

## 4. Remaining Gaps & False-Positive Boundaries
- **Boundaries**: Applies specifically to Intel QSV hybrid transcode chains. Does not apply to pure software encoders (`libx264`) or full hardware-decode-and-encode pipelines (`qsv` hwaccel input).
- **Gaps**: None.

## 5. Verified Prevention Check
- **Rule / Guard**: Ensure `QSV_LOOKAHEAD=0` is enforced in production video compiler parameters.
- **Verification**: `tests/unit/test_video_compiler_safety.py`

## 6. Evidence Links
- **Legacy Register**: [`docs/error-solving/understood-errors.md#qsv-lookahead-stream-corruption`](../understood-errors.md)
- **Source Code**: [`src/youtube_automation/video/compiler.py`](../../../src/youtube_automation/video/compiler.py)
