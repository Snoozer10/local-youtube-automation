"""Unit tests for run_agency SHA-256 script invalidation and CDP loopback binding."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import run_agency


class TestAgencyScriptInvalidation:
    def test_new_run_without_script_sets_initial_hash_when_script_appears(self, tmp_path: Path):
        """Test 1: New run without script sets initial hash when script appears."""
        script_file = tmp_path / "refined_script.txt"
        script_content = "هذا نص تجريبي للمرحلة الأولى من المعالجة".encode()
        script_file.write_bytes(script_content)
        expected_hash = hashlib.sha256(script_content).hexdigest()

        state = run_agency.get_pipeline_state(str(tmp_path))
        assert "script_hash" not in state or state["script_hash"] is None

        # Execute script invalidation check
        invalidated = run_agency.check_script_invalidation(str(tmp_path), state, "video_test")
        assert invalidated is False
        assert state.get("script_hash") == expected_hash

        # Verify persisted state on disk
        persisted = run_agency.get_pipeline_state(str(tmp_path))
        assert persisted.get("script_hash") == expected_hash

    def test_refine_step_success_records_script_hash(self, tmp_path: Path, monkeypatch):
        """Test 1b: Verify refine step completion in _execute_folder_steps stores script_hash and saves state."""
        script_file = tmp_path / "refined_script.txt"
        script_content = "نص بعد الصقل والتعديل".encode()
        expected_hash = hashlib.sha256(script_content).hexdigest()

        state = run_agency.get_pipeline_state(str(tmp_path))
        state["translate"] = True
        run_agency.save_pipeline_state(str(tmp_path), state)

        # Mock subprocess.run to create refined_script.txt and return 0
        def fake_run(cmd, *args, **kwargs):
            script_file.write_bytes(script_content)
            res = MagicMock()
            res.returncode = 0
            return res

        monkeypatch.setattr("subprocess.run", fake_run)
        monkeypatch.setattr("run_agency.clean_browser_tabs", lambda: None)
        monkeypatch.setattr("time.sleep", lambda _: None)

        folder_steps = [
            {
                "key": "refine",
                "script": "refine_script.py",
                "desc": "Phase 2: Arabic Script Refinement",
            }
        ]

        success = run_agency._execute_folder_steps(
            str(tmp_path), state, folder_steps, "video_test", step_timeout=300
        )
        assert success is True
        assert state["refine"] is True
        assert state.get("script_hash") == expected_hash

        persisted = run_agency.get_pipeline_state(str(tmp_path))
        assert persisted.get("refine") is True
        assert persisted.get("script_hash") == expected_hash

    def test_modified_script_invalidates_downstream_stages_preserving_translate_and_refine(
        self, tmp_path: Path, capsys
    ):
        """Test 2: Modified script invalidates downstream stages but preserves translate and refine."""
        old_content = "النص الأصلي غير المعدل".encode()
        old_hash = hashlib.sha256(old_content).hexdigest()

        state = {
            "translate": True,
            "refine": True,
            "voice": True,
            "audacity": True,
            "stitch": True,
            "transcribe": True,
            "images": True,
            "fixtimes": True,
            "video": True,
            "thumbnail": True,
            "script_hash": old_hash,
        }
        run_agency.save_pipeline_state(str(tmp_path), state)

        # Now write modified script
        new_content = "النص الجديد بعد تعديل جوهري في السيناريو".encode()
        new_hash = hashlib.sha256(new_content).hexdigest()
        (tmp_path / "refined_script.txt").write_bytes(new_content)

        video_title = "episode_42"
        invalidated = run_agency.check_script_invalidation(str(tmp_path), state, video_title)
        assert invalidated is True

        # Check console log
        captured = capsys.readouterr().out
        assert f"🔄 [SCRIPT MODIFIED] '{video_title}' script changed. Invalidating downstream stages." in captured

        # Preserved stages
        assert state["translate"] is True
        assert state["refine"] is True

        # Downstream stages invalidated
        downstream = ["voice", "audacity", "stitch", "transcribe", "images", "fixtimes", "video", "thumbnail"]
        for stage in downstream:
            assert state[stage] is False, f"Expected {stage} to be invalidated (False)"

        # script_hash updated
        assert state["script_hash"] == new_hash

        # Verify disk persistence
        persisted = run_agency.get_pipeline_state(str(tmp_path))
        assert persisted["translate"] is True
        assert persisted["refine"] is True
        for stage in downstream:
            assert persisted[stage] is False
        assert persisted["script_hash"] == new_hash

    def test_unmodified_script_preserves_all_completed_stages(self, tmp_path: Path, capsys):
        """Test 3: Unmodified script preserves all completed stages and does not trigger invalidation."""
        script_content = "نص ثابت لم يتغير".encode()
        script_hash = hashlib.sha256(script_content).hexdigest()
        (tmp_path / "refined_script.txt").write_bytes(script_content)

        state = {
            "translate": True,
            "refine": True,
            "voice": True,
            "audacity": True,
            "stitch": True,
            "transcribe": True,
            "images": True,
            "fixtimes": True,
            "video": True,
            "thumbnail": True,
            "script_hash": script_hash,
        }
        run_agency.save_pipeline_state(str(tmp_path), state)

        video_title = "episode_fixed"
        invalidated = run_agency.check_script_invalidation(str(tmp_path), state, video_title)
        assert invalidated is False

        captured = capsys.readouterr().out
        assert "[SCRIPT MODIFIED]" not in captured

        # All stages should remain True
        for key in ["translate", "refine", "voice", "audacity", "stitch", "transcribe", "images", "fixtimes", "video", "thumbnail"]:
            assert state[key] is True
        assert state["script_hash"] == script_hash

        persisted = run_agency.get_pipeline_state(str(tmp_path))
        for key in ["translate", "refine", "voice", "audacity", "stitch", "transcribe", "images", "fixtimes", "video", "thumbnail"]:
            assert persisted[key] is True

    def test_process_folder_skips_when_video_and_thumbnail_done_and_script_unchanged(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """Verify process_folder fast-path skips folder when video+thumbnail done and script unchanged."""
        script_content = "نص مكتمل تماما".encode()
        script_hash = hashlib.sha256(script_content).hexdigest()
        (tmp_path / "refined_script.txt").write_bytes(script_content)

        state = {
            "translate": True,
            "refine": True,
            "voice": True,
            "audacity": True,
            "stitch": True,
            "transcribe": True,
            "images": True,
            "fixtimes": True,
            "video": True,
            "thumbnail": True,
            "script_hash": script_hash,
        }
        run_agency.save_pipeline_state(str(tmp_path), state)

        # Mock _execute_folder_steps so we can assert it is NOT called
        mock_execute = MagicMock(return_value=True)
        monkeypatch.setattr("run_agency._execute_folder_steps", mock_execute)

        result = run_agency.process_folder(str(tmp_path))
        assert result is True
        assert not mock_execute.called

        out = capsys.readouterr().out
        assert "is already fully compiled and processed. Skipping." in out

    def test_process_folder_invalidates_and_executes_when_script_changed(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """Verify process_folder invalidates downstream stages and calls _execute_folder_steps on modified script."""
        old_content = "النص القديم".encode()
        old_hash = hashlib.sha256(old_content).hexdigest()

        state = {
            "translate": True,
            "refine": True,
            "voice": True,
            "audacity": True,
            "stitch": True,
            "transcribe": True,
            "images": True,
            "fixtimes": True,
            "video": True,
            "thumbnail": True,
            "script_hash": old_hash,
        }
        run_agency.save_pipeline_state(str(tmp_path), state)

        # Write modified script
        new_content = "النص الجديد كليا".encode()
        new_hash = hashlib.sha256(new_content).hexdigest()
        (tmp_path / "refined_script.txt").write_bytes(new_content)

        # Mock _execute_folder_steps to observe it being called
        mock_execute = MagicMock(return_value=True)
        monkeypatch.setattr("run_agency._execute_folder_steps", mock_execute)

        result = run_agency.process_folder(str(tmp_path))
        assert result is True
        assert mock_execute.called

        out = capsys.readouterr().out
        assert "[SCRIPT MODIFIED]" in out
        assert "Invalidating downstream stages" in out

        # State on disk should reflect downstream stages invalidated
        persisted = run_agency.get_pipeline_state(str(tmp_path))
        assert persisted["video"] is False
        assert persisted["thumbnail"] is False
        assert persisted["voice"] is False
        assert persisted["translate"] is True
        assert persisted["refine"] is True
        assert persisted["script_hash"] == new_hash


class TestAgencyCDPLoopback:
    def test_clean_browser_tabs_connects_to_127_0_0_1_and_not_localhost(self):
        """Test 4: Verify clean_browser_tabs connects to 127.0.0.1 and not localhost."""
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_context.pages = [mock_page]
        mock_browser.contexts = [mock_context]
        mock_p.chromium.connect_over_cdp.return_value = mock_browser

        with patch("run_agency.sync_playwright") as mock_playwright:
            mock_playwright.return_value.__enter__.return_value = mock_p
            run_agency.clean_browser_tabs()

            assert mock_p.chromium.connect_over_cdp.called
            call_args, call_kwargs = mock_p.chromium.connect_over_cdp.call_args
            endpoint_url = call_args[0]

            assert "127.0.0.1" in endpoint_url
            assert "localhost" not in endpoint_url
            assert endpoint_url.startswith("http://127.0.0.1:")
