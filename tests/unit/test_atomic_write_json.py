"""Unit tests for utils.atomic_write_json (ERR-05 crash-safe writer)."""

import json
import os

import pytest

from utils import atomic_write_json


class TestAtomicWriteJson:
    def test_roundtrip_preserves_payload_and_kwargs(self, tmp_path):
        target = tmp_path / "state.json"
        payload = {"name": "الحلقة", "count": 3, "nested": [1, 2]}
        atomic_write_json(str(target), payload, ensure_ascii=False, indent=4)
        assert json.loads(target.read_text(encoding="utf-8")) == payload

    def test_no_temp_files_left_behind_after_success(self, tmp_path):
        target = tmp_path / "state.json"
        atomic_write_json(str(target), {"ok": True})
        leftovers = [p for p in os.listdir(tmp_path) if p != "state.json"]
        assert leftovers == []

    def test_overwrite_existing_file_replaces_content(self, tmp_path):
        target = tmp_path / "state.json"
        target.write_text('{"old": true}', encoding="utf-8")
        atomic_write_json(str(target), {"old": False})
        assert json.loads(target.read_text(encoding="utf-8")) == {"old": False}

    def test_serialization_failure_cleans_tmp_and_keeps_original(self, tmp_path):
        target = tmp_path / "state.json"
        target.write_text('{"original": 1}', encoding="utf-8")
        with pytest.raises(TypeError):
            atomic_write_json(str(target), {"bad": object()})
        assert json.loads(target.read_text(encoding="utf-8")) == {"original": 1}
        leftovers = [p for p in os.listdir(tmp_path) if p != "state.json"]
        assert leftovers == []

    def test_writes_into_missing_directory_raises(self, tmp_path):
        with pytest.raises(OSError):
            atomic_write_json(str(tmp_path / "ghost" / "state.json"), {})
