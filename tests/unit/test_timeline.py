"""Unit tests for parse_image_timeline and get_sorted_images."""

import os
import shutil
import tempfile
import pytest

import compile_video


def _write_timeline_file(run_folder, content, filename="image_timestamps.txt"):
    """Write a timeline file into a run folder."""
    path = os.path.join(run_folder, filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


class TestParseImageTimeline:
    """Tests for parse_image_timeline(run_folder)."""

    def test_parse_mm_ss_format(self):
        """[MM:SS] format parsed to seconds and filename."""
        d = tempfile.mkdtemp()
        try:
            _write_timeline_file(d, "[00:00] First paragraph\n[00:08] Second paragraph\n[01:30] Third paragraph\n")
            blocks = compile_video.parse_image_timeline(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

        assert len(blocks) == 3
        assert blocks[0] == {"name": "00_00", "sec": 0.0}
        assert blocks[1] == {"name": "00_08", "sec": 8.0}
        assert blocks[2] == {"name": "01_30", "sec": 90.0}

    def test_parse_hh_mm_ss_format(self):
        """[HH:MM:SS] format parsed correctly, sorted by seconds."""
        d = tempfile.mkdtemp()
        try:
            _write_timeline_file(d, "[01:00:00] Hour mark\n[00:01:30] Ninety seconds\n")
            blocks = compile_video.parse_image_timeline(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

        assert len(blocks) == 2
        # blocks are sorted by sec, so 90s (00_01_30) precedes 3600s (01_00_00)
        assert blocks[0] == {"name": "00_01_30", "sec": 90.0}
        assert blocks[1] == {"name": "01_00_00", "sec": 3600.0}

    def test_parse_missing_file_returns_empty(self):
        """Folder without timeline files returns empty list."""
        d = tempfile.mkdtemp()
        try:
            blocks = compile_video.parse_image_timeline(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

        assert blocks == []

    def test_parse_skips_empty_lines(self):
        """Blank lines are ignored."""
        d = tempfile.mkdtemp()
        try:
            _write_timeline_file(d, "[00:00] First\n\n\n[00:10] Second\n")
            blocks = compile_video.parse_image_timeline(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

        assert len(blocks) == 2
        assert blocks[0]["name"] == "00_00"
        assert blocks[1]["name"] == "00_10"

    def test_parse_invalid_lines_skipped(self):
        """Lines without timestamp prefix are skipped."""
        d = tempfile.mkdtemp()
        try:
            _write_timeline_file(d, "No timestamp here\n[00:05] Valid\nAlso invalid\n")
            blocks = compile_video.parse_image_timeline(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

        assert len(blocks) == 1
        assert blocks[0]["name"] == "00_05"

    def test_parse_mixed_mm_ss_and_hh_mm_ss(self):
        """Both timestamp formats in same file parsed correctly."""
        d = tempfile.mkdtemp()
        try:
            _write_timeline_file(d, "[00:00] Start\n[00:01:30] Ninety sec\n[02:30] Two min thirty\n")
            blocks = compile_video.parse_image_timeline(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

        assert len(blocks) == 3
        assert blocks[0] == {"name": "00_00", "sec": 0.0}
        assert blocks[1] == {"name": "00_01_30", "sec": 90.0}
        assert blocks[2] == {"name": "02_30", "sec": 150.0}

    def test_parse_fallback_timestamped_transcript(self):
        """timestamped_transcript.txt used when image_timestamps.txt missing."""
        d = tempfile.mkdtemp()
        try:
            _write_timeline_file(d, "[00:00] Start\n[00:20] Later\n", filename="timestamped_transcript.txt")
            blocks = compile_video.parse_image_timeline(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

        assert len(blocks) == 2
        assert blocks[0]["name"] == "00_00"
        assert blocks[1]["name"] == "00_20"


class TestGetSortedImages:
    """Tests for get_sorted_images(images_dir)."""

    def test_natural_sort_order(self):
        """sentence_2.png comes before sentence_10.png."""
        d = tempfile.mkdtemp()
        try:
            for name in ["sentence_1.png", "sentence_10.png", "sentence_2.png", "sentence_3.png"]:
                open(os.path.join(d, name), 'w').close()
            images = compile_video.get_sorted_images(d)
            assert images == ["sentence_1.png", "sentence_2.png", "sentence_3.png", "sentence_10.png"]
        finally:
            for f in os.listdir(d):
                os.unlink(os.path.join(d, f))
            os.rmdir(d)

    def test_missing_dir_returns_empty(self):
        """Non-existent directory returns empty list."""
        images = compile_video.get_sorted_images("/nonexistent/dir")
        assert images == []

    def test_only_png_files(self):
        """Only .png files are returned."""
        d = tempfile.mkdtemp()
        try:
            open(os.path.join(d, "a.png"), 'w').close()
            open(os.path.join(d, "b.jpg"), 'w').close()
            open(os.path.join(d, "c.txt"), 'w').close()
            open(os.path.join(d, "d.PNG"), 'w').close()  # case sensitive
            images = compile_video.get_sorted_images(d)
            assert images == ["a.png"]
        finally:
            for f in os.listdir(d):
                os.unlink(os.path.join(d, f))
            os.rmdir(d)

    def test_empty_dir_returns_empty(self):
        """Empty directory returns empty list."""
        d = tempfile.mkdtemp()
        try:
            images = compile_video.get_sorted_images(d)
            assert images == []
        finally:
            os.rmdir(d)


class TestValidateAssets:
    """Tests for validate_assets(sync_timeline, images_dir)."""

    def test_all_assets_exist_and_non_empty(self):
        """All assets exist and are non-empty returns empty invalid list."""
        d = tempfile.mkdtemp()
        try:
            # Create non-empty images
            for name in ["00_00.png", "00_08.png"]:
                with open(os.path.join(d, name), 'w') as f:
                    f.write("dummy content")
            blocks = [
                {"name": "00_00", "sec": 0.0, "occurrence": 1},
                {"name": "00_08", "sec": 8.0, "occurrence": 1}
            ]
            invalid = compile_video.validate_assets(blocks, d)
            assert len(invalid) == 0
        finally:
            for f in os.listdir(d):
                os.unlink(os.path.join(d, f))
            os.rmdir(d)

    def test_missing_asset_returns_invalid(self):
        """Missing asset with no fallback returns invalid list."""
        d = tempfile.mkdtemp()
        try:
            blocks = [
                {"name": "00_00", "sec": 0.0, "occurrence": 1}
            ]
            invalid = compile_video.validate_assets(blocks, d)
            assert len(invalid) == 1
            assert invalid[0] == (0, "00_00")
        finally:
            os.rmdir(d)

    def test_empty_asset_returns_invalid(self):
        """Asset with size 0 returns invalid list."""
        d = tempfile.mkdtemp()
        try:
            open(os.path.join(d, "00_00.png"), 'w').close()  # size 0
            blocks = [
                {"name": "00_00", "sec": 0.0, "occurrence": 1}
            ]
            invalid = compile_video.validate_assets(blocks, d)
            assert len(invalid) == 1
            assert invalid[0] == (0, "00_00")
        finally:
            for f in os.listdir(d):
                os.unlink(os.path.join(d, f))
            os.rmdir(d)

    def test_duplicate_occurrence_resolves_to_duplicate_image(self):
        """occurrence > 1 resolves to duplicate image variant."""
        d = tempfile.mkdtemp()
        try:
            open(os.path.join(d, "00_00.png"), 'w').close()
            with open(os.path.join(d, "00_00_2.png"), 'w') as f:
                f.write("dummy content")
            blocks = [
                {"name": "00_00", "sec": 0.0, "occurrence": 2}
            ]
            invalid = compile_video.validate_assets(blocks, d)
            assert len(invalid) == 0
        finally:
            for f in os.listdir(d):
                os.unlink(os.path.join(d, f))
            os.rmdir(d)