"""Unit tests for load_ai_camera_decisions and load_manual_overrides."""

import os
import tempfile
import json
import pytest

import compile_video


class TestLoadAiCameraDecisions:
    """Tests for load_ai_camera_decisions(json_path)."""

    def test_valid_json_blocks_parsed(self):
        """Valid JSON array blocks with camera_specifications parsed."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            data = [
                {"timestamp": "[00:00]", "visual_prompt": {"camera_specifications": "zoom in slowly"}},
                {"timestamp": "[00:08]", "visual_prompt": {"camera_specifications": "pan left across scene"}},
                {"timestamp": "[00:15]", "visual_prompt": {"camera_specifications": "static shot"}},
            ]
            json.dump(data, f)
            f.flush()
            result = compile_video.load_ai_camera_decisions(f.name)
        os.unlink(f.name)

        assert result == {
            "00_00": "zoom_in",
            "00_08": "pan_left",
            "00_15": "static",
        }

    def test_multiple_json_blocks_concatenated(self):
        """Multiple JSON arrays in file (regex findall behavior)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write('[\n  {"timestamp": "[00:00]", "visual_prompt": {"camera_specifications": "zoom in"}}\n]\n')
            f.write('\n')
            f.write('[\n  {"timestamp": "[00:10]", "visual_prompt": {"camera_specifications": "pan right"}}\n]\n')
            f.flush()
            result = compile_video.load_ai_camera_decisions(f.name)
        os.unlink(f.name)

        assert result == {
            "00_00": "zoom_in",
            "00_10": "pan_right",
        }

    def test_missing_file_returns_empty(self):
        """Non-existent file returns empty dict."""
        result = compile_video.load_ai_camera_decisions("/nonexistent/flow_prompts.json")
        assert result == {}

    def test_malformed_json_returns_empty(self):
        """Invalid JSON returns empty dict (logged warning)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write('{ not valid json }')
            f.flush()
            result = compile_video.load_ai_camera_decisions(f.name)
        os.unlink(f.name)

        assert result == {}

    def test_missing_visual_prompt_or_camera_spec_defaults_to_static(self):
        """Items without visual_prompt or camera_specifications default to static (not skipped)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            data = [
                {"timestamp": "[00:00]", "visual_prompt": {}},  # no camera_specifications -> static
                {"timestamp": "[00:05]", "visual_prompt": {"camera_specifications": "zoom out"}},  # valid
                {"timestamp": "[00:10]"},  # no visual_prompt -> static
                {"timestamp": "[00:15]", "visual_prompt": {"camera_specifications": "static"}},  # valid
            ]
            json.dump(data, f)
            f.flush()
            result = compile_video.load_ai_camera_decisions(f.name)
        os.unlink(f.name)

        assert result == {
            "00_00": "static",
            "00_05": "zoom_out",
            "00_10": "static",
            "00_15": "static",
        }

    def test_camera_spec_keywords_case_insensitive(self):
        """Camera specification keywords matched case-insensitively."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            data = [
                {"timestamp": "[00:00]", "visual_prompt": {"camera_specifications": "ZOOM IN"}},
                {"timestamp": "[00:05]", "visual_prompt": {"camera_specifications": "Zoom Out"}},
                {"timestamp": "[00:10]", "visual_prompt": {"camera_specifications": "Pan Left"}},
                {"timestamp": "[00:15]", "visual_prompt": {"camera_specifications": "PAN RIGHT"}},
            ]
            json.dump(data, f)
            f.flush()
            result = compile_video.load_ai_camera_decisions(f.name)
        os.unlink(f.name)

        assert result == {
            "00_00": "zoom_in",
            "00_05": "zoom_out",
            "00_10": "pan_left",
            "00_15": "pan_right",
        }

    def test_unknown_camera_spec_defaults_to_static(self):
        """Unrecognized camera specification defaults to static."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            data = [
                {"timestamp": "[00:00]", "visual_prompt": {"camera_specifications": "rotate 360"}},
                {"timestamp": "[00:05]", "visual_prompt": {"camera_specifications": "dolly zoom"}},
            ]
            json.dump(data, f)
            f.flush()
            result = compile_video.load_ai_camera_decisions(f.name)
        os.unlink(f.name)

        assert result == {
            "00_00": "static",
            "00_05": "static",
        }

    def test_empty_timestamp_skipped(self):
        """Items with empty/missing timestamp are skipped."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            data = [
                {"timestamp": "", "visual_prompt": {"camera_specifications": "zoom in"}},
                {"visual_prompt": {"camera_specifications": "static"}},  # no timestamp key
                {"timestamp": "[00:10]", "visual_prompt": {"camera_specifications": "pan left"}},
            ]
            json.dump(data, f)
            f.flush()
            result = compile_video.load_ai_camera_decisions(f.name)
        os.unlink(f.name)

        assert result == {
            "00_10": "pan_left",
        }


class TestLoadManualOverrides:
    """Tests for load_manual_overrides(txt_path)."""

    def test_valid_key_value_pairs(self):
        """key=value lines parsed correctly."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write("00_00=zoom_in\n")
            f.write("00_08=pan_left\n")
            f.write("00_15=static\n")
            f.flush()
            result = compile_video.load_manual_overrides(f.name)
        os.unlink(f.name)

        assert result == {
            "00_00": "zoom_in",
            "00_08": "pan_left",
            "00_15": "static",
        }

    def test_missing_file_returns_empty(self):
        """Non-existent file returns empty dict."""
        result = compile_video.load_manual_overrides("/nonexistent/manual_animations.txt")
        assert result == {}

    def test_values_lowercased(self):
        """Values are lowercased."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write("00_00=ZOOM_IN\n")
            f.write("00_08=Pan_Left\n")
            f.flush()
            result = compile_video.load_manual_overrides(f.name)
        os.unlink(f.name)

        assert result == {
            "00_00": "zoom_in",
            "00_08": "pan_left",
        }

    def test_whitespace_trimmed(self):
        """Keys and values have whitespace trimmed."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write("  00_00  =  zoom_in  \n")
            f.write("\t00_08\t=\tpan_right\t\n")
            f.flush()
            result = compile_video.load_manual_overrides(f.name)
        os.unlink(f.name)

        assert result == {
            "00_00": "zoom_in",
            "00_08": "pan_right",
        }

    def test_lines_without_equals_skipped(self):
        """Lines without '=' are ignored."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write("00_00=zoom_in\n")
            f.write("invalid line no equals\n")
            f.write("00_10=static\n")
            f.flush()
            result = compile_video.load_manual_overrides(f.name)
        os.unlink(f.name)

        assert result == {
            "00_00": "zoom_in",
            "00_10": "static",
        }

    def test_empty_lines_skipped(self):
        """Blank lines are ignored."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write("\n\n00_00=zoom_in\n\n00_10=static\n\n")
            f.flush()
            result = compile_video.load_manual_overrides(f.name)
        os.unlink(f.name)

        assert result == {
            "00_00": "zoom_in",
            "00_10": "static",
        }