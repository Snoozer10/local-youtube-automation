"""Unit tests for build_subtitle_style_string and fix_arabic_srt."""

import os
import tempfile
import pytest

import compile_video


class TestBuildSubtitleStyleString:
    """Tests for build_subtitle_style_string(config)."""

    def test_all_config_keys_rendered(self):
        """Every SUB_* config key appears in output."""
        config = {
            "SUB_FONT_NAME": "Tahoma",
            "SUB_FONT_SIZE": 22,
            "SUB_PRIMARY_COLOR": "&H00FFFFFF",
            "SUB_OUTLINE_COLOR": "&H00000000",
            "SUB_BORDER_STYLE": 1,
            "SUB_OUTLINE": 2.5,
            "SUB_SHADOW": 1,
            "SUB_ALIGNMENT": 2,
            "SUB_MARGIN_V": 50,
            "SUB_BOLD": 1,
        }
        style = compile_video.build_subtitle_style_string(config)

        # All keys present
        assert "Fontname=Tahoma" in style
        assert "Fontsize=22" in style
        assert "PrimaryColour=&H00FFFFFF" in style
        assert "OutlineColour=&H00000000" in style
        assert "BorderStyle=1" in style
        assert "Outline=2.5" in style
        assert "Shadow=1" in style
        assert "Alignment=2" in style
        assert "MarginV=50" in style
        assert "Bold=1" in style

    def test_ass_format_syntax(self):
        """Output is comma-separated key=value pairs (ASS force_style format)."""
        config = {
            "SUB_FONT_NAME": "Arial",
            "SUB_FONT_SIZE": 24,
            "SUB_PRIMARY_COLOR": "&H00FFFFFF",
            "SUB_OUTLINE_COLOR": "&H00000000",
            "SUB_BORDER_STYLE": 1,
            "SUB_OUTLINE": 2.0,
            "SUB_SHADOW": 0,
            "SUB_ALIGNMENT": 2,
            "SUB_MARGIN_V": 30,
            "SUB_BOLD": 0,
        }
        style = compile_video.build_subtitle_style_string(config)

        # No trailing comma
        assert not style.endswith(",")
        # Each pair separated by comma
        parts = style.split(",")
        assert len(parts) == 10
        for part in parts:
            assert "=" in part

    def test_special_chars_preserved(self):
        """ASS color codes like &H00FFFFFF preserved exactly."""
        config = {
            "SUB_FONT_NAME": "Tahoma",
            "SUB_FONT_SIZE": 22,
            "SUB_PRIMARY_COLOR": "&H00FFFFFF",
            "SUB_OUTLINE_COLOR": "&H000000FF",  # Blue outline
            "SUB_BORDER_STYLE": 1,
            "SUB_OUTLINE": 2.5,
            "SUB_SHADOW": 1,
            "SUB_ALIGNMENT": 2,
            "SUB_MARGIN_V": 50,
            "SUB_BOLD": 1,
        }
        style = compile_video.build_subtitle_style_string(config)

        assert "PrimaryColour=&H00FFFFFF" in style
        assert "OutlineColour=&H000000FF" in style

    def test_int_float_string_values_rendered(self):
        """Int, float, and string config values all render correctly."""
        config = {
            "SUB_FONT_NAME": "Tahoma",
            "SUB_FONT_SIZE": 22,        # int
            "SUB_PRIMARY_COLOR": "&H00FFFFFF",  # string
            "SUB_OUTLINE_COLOR": "&H00000000",
            "SUB_BORDER_STYLE": 1,      # int
            "SUB_OUTLINE": 2.5,         # float
            "SUB_SHADOW": 1,            # int
            "SUB_ALIGNMENT": 2,         # int
            "SUB_MARGIN_V": 50,         # int
            "SUB_BOLD": 1,              # int
        }
        style = compile_video.build_subtitle_style_string(config)

        assert "Fontsize=22" in style
        assert "Outline=2.5" in style
        assert "BorderStyle=1" in style


class TestFixArabicSrt:
    """Tests for fix_arabic_srt(input_path, output_path)."""

    def test_strips_existing_bom(self):
        """Input with UTF-8 BOM written without BOM."""
        d = tempfile.mkdtemp()
        try:
            src = os.path.join(d, "in.srt")
            out = os.path.join(d, "fixed.srt")
            # Write with BOM (utf-8-sig)
            with open(src, "w", encoding="utf-8-sig") as f:
                f.write("1\n00:00:00,000 --> 00:00:01,000\nمرحبا\n")

            compile_video.fix_arabic_srt(src, out)

            with open(out, "rb") as f:
                raw = f.read()

            # No BOM
            assert not raw.startswith(b"\xef\xbb\xbf"), "Output must not contain BOM"
            # Content preserved
            assert "مرحبا".encode("utf-8") in raw
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_never_double_bom_on_rerun(self):
        """Running twice never produces double BOM."""
        d = tempfile.mkdtemp()
        try:
            src = os.path.join(d, "in.srt")
            out = os.path.join(d, "fixed.srt")
            with open(src, "w", encoding="utf-8-sig") as f:
                f.write("1\n00:00:00,000 --> 00:00:01,000\nمرحبا\n")

            compile_video.fix_arabic_srt(src, out)
            compile_video.fix_arabic_srt(src, out)  # Second run

            with open(out, "rb") as f:
                raw = f.read()

            assert raw.count(b"\xef\xbb\xbf") == 0, "Double BOM must never appear"
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_output_opens_in_ffmpeg(self):
        """Fixed SRT opens successfully in ffmpeg subtitles filter."""
        d = tempfile.mkdtemp()
        try:
            src = os.path.join(d, "in.srt")
            out = os.path.join(d, "fixed.srt")
            with open(src, "w", encoding="utf-8-sig") as f:
                f.write("1\n00:00:00,000 --> 00:00:01,000\nمرحبا بالعالم\n")

            compile_video.fix_arabic_srt(src, out)

            # Create dummy video + audio for ffmpeg test
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

            fc = f"[0:v]null[vout];[vout]subtitles='{os.path.basename(out)}':force_style='Fontname=Tahoma,Fontsize=22'[s]"
            cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                   "-i", i, "-i", a, "-filter_complex", fc, "-map", "[s]", "-map", "1:a", o]
            r = subprocess.run(cmd, cwd=d, capture_output=True, text=True, encoding="utf-8", errors="ignore")

            assert r.returncode == 0, f"ffmpeg could not open fixed srt: {r.stderr[-400:]}"
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_plain_utf8_input_works(self):
        """Input without BOM (plain utf-8) also works."""
        d = tempfile.mkdtemp()
        try:
            src = os.path.join(d, "in.srt")
            out = os.path.join(d, "fixed.srt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("1\n00:00:00,000 --> 00:00:01,000\nمرحبا\n")

            compile_video.fix_arabic_srt(src, out)

            with open(out, "rb") as f:
                raw = f.read()

            assert not raw.startswith(b"\xef\xbb\xbf")
            assert "مرحبا".encode("utf-8") in raw
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)