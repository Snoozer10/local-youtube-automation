import os
import tempfile

import compile_video


def _write(path, text, encoding):
    with open(path, "w", encoding=encoding) as f:
        f.write(text)


def test_fix_arabic_srt_strips_existing_bom():
    d = tempfile.mkdtemp()
    src = os.path.join(d, "in.srt")
    out = os.path.join(d, "fixed.srt")
    # input already has a UTF-8 BOM (as produced by the transcript pipeline)
    _write(src, "1\n00:00:00,000 --> 00:00:01,000\nمرحبا\n", "utf-8-sig")
    compile_video.fix_arabic_srt(src, out)
    with open(out, "rb") as f:
        raw = f.read()
    # no BOM at all, and content preserved
    assert not raw.startswith(b"\xef\xbb\xbf"), "output must not contain a BOM"
    assert "مرحبا".encode("utf-8") in raw


def test_fix_arabic_srt_never_double_bom_on_rerun():
    d = tempfile.mkdtemp()
    src = os.path.join(d, "in.srt")
    out = os.path.join(d, "fixed.srt")
    _write(src, "1\n00:00:00,000 --> 00:00:01,000\nمرحبا\n", "utf-8-sig")
    # run twice (idempotent re-run scenario)
    compile_video.fix_arabic_srt(src, out)
    compile_video.fix_arabic_srt(src, out)
    with open(out, "rb") as f:
        raw = f.read()
    assert raw.count(b"\xef\xbb\xbf") == 0, "double BOM must never appear"


def test_fix_arabic_srt_output_opens_in_ffmpeg():
    d = tempfile.mkdtemp()
    src = os.path.join(d, "in.srt")
    out = os.path.join(d, "fixed.srt")
    _write(src, "1\n00:00:00,000 --> 00:00:01,000\nمرحبا بالعالم\n", "utf-8-sig")
    compile_video.fix_arabic_srt(src, out)
    # ffmpeg subtitles filter must open the file (no double-BOM parse failure)
    fc = f"[0:v]null[vout];[vout]subtitles='{os.path.basename(out)}'[s]"
    i = os.path.join(d, "i.png")
    a = os.path.join(d, "a.wav")
    o = os.path.join(d, "o.mp4")
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=blue:s=320x180", "-frames:v", "1", "-update", "1", i],
                   capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-t", "1", a],
                   capture_output=True)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-i", i, "-i", a, "-filter_complex", fc, "-map", "[s]", "-map", "1:a", o]
    r = subprocess.run(cmd, cwd=d, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    assert r.returncode == 0, f"ffmpeg could not open fixed srt: {r.stderr[-400:]}"
