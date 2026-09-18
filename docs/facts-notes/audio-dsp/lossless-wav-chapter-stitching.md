# Note: Lossless WAV Chapter Stitching and Homogeneity Assertion

**Category:** Audio DSP  
**Date Logged:** 2026-09-17  
**Relevant Code Files:** src/youtube_automation/audio/chapter_stitcher.py, stitch_chapters.py  
**Audit Reference:** Phase 5 Master Audio Stitching  

### 1. Core Rule in Plain English
Sequential WAV chapter concatenation must assert strict format homogeneity (framerate, channel count, sample width) across all chapters against the reference header before appending raw PCM frames, and scan for contiguous numerical chapter sequences from index 1 without gaps.

### 2. The Failure Mode It Prevents
Blind concatenation of audio files with different sampling rates (e.g. 24kHz mixed with 44.1kHz) produces severe pitch and tempo distortion in downstream players. Missing chapter sequence gaps (e.g. Chapter 4 missing while 1-3 and 5-10 exist) would result in truncated narrative audio.

### 3. Implementation Specification
`python
with wave.open(file_list[0], 'rb') as first_file:
    params = first_file.getparams()
ref = (params.framerate, params.nchannels, params.sampwidth)

for path in file_list[1:]:
    with wave.open(path, 'rb') as probe:
        cur = (probe.getframerate(), probe.getnchannels(), probe.getsampwidth())
    if cur != ref:
        raise ValueError(f'Chapter format mismatch: {cur} != {ref}')
`

### 4. Verification Check
Compare the master ull_episode_voice.wav physical frame count against the sum of individual chapter frame counts: $\sum 	ext{frames}_i == 	ext{frames}_{	ext{master}}$ and verify duration delta $\le 0.05\text{s}$.\n