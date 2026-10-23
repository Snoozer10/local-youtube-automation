"""No live Win32 calls or application launches: subprocess and APIs are fakes."""

import ctypes
import json
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from youtube_automation.core import audacity_windows as aw
from youtube_automation.core.window_readiness import WindowRole

EXE = r"C:\Program Files\Audacity\Audacity.exe"
IDENTITY = {"ok": True, "pid": 42, "executable": EXE,
            "creation_ticks": "133800000000000000", "creation_time": 1735526400.0}


def owned(monkeypatch, tmp_path):
    replies = [dict(IDENTITY)]
    runner = Mock(side_effect=lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=json.dumps(replies.pop(0)), stderr=""))
    monkeypatch.setattr(aw.subprocess, "run", runner)
    process = SimpleNamespace(pid=42, poll=lambda: None)
    backend = aw.OwnedAudacityWindows(process, EXE, tmp_path)
    return backend, replies, runner


def test_creation_identity_and_subprocess_isolation(monkeypatch, tmp_path):
    backend, _, runner = owned(monkeypatch, tmp_path)
    assert backend.creation_time == IDENTITY["creation_time"]
    args, kwargs = runner.call_args
    assert args[0][1:3] == ["-I", "-B"]
    assert args[0][-1] == "--native-helper"
    assert kwargs["timeout"] == 2.0
    assert "creationflags" in kwargs


@pytest.mark.parametrize("change", [
    {"creation_ticks": "133800000000000001"}, {"pid": 43},
    {"executable": r"C:\Other\Audacity.exe"},
])
def test_observe_rejects_process_reuse_or_path_drift(monkeypatch, tmp_path, change):
    backend, replies, _ = owned(monkeypatch, tmp_path)
    replies.append({**IDENTITY, **change, "windows": []})
    with pytest.raises(aw.OwnedWindowError, match="process_identity_mismatch"):
        backend.observe(42)


def test_observe_rejects_foreign_hwnd_payload(monkeypatch, tmp_path):
    backend, replies, _ = owned(monkeypatch, tmp_path)
    replies.append({**IDENTITY, "windows": [{"hwnd": 100, "pid": 43,
                    "visible": True, "modal": False, "role": "main"}]})
    with pytest.raises(aw.OwnedWindowError, match="invalid_window_observation"):
        backend.observe(42)


@pytest.mark.parametrize("title,cls,enabled,owner,role", [
    ("Audacity", "wxWindowClassNR", True, 0, WindowRole.MAIN),
    ("Project - Audacity", "wxWindowClassNR", True, 0, WindowRole.MAIN),
    ("Audacity", "wxWindowClassNR", False, 0, WindowRole.MODAL),
    ("Automatic Crash Recovery", "#32770", True, 100, WindowRole.RECOVERY),
    ("Welcome to Audacity!", "wxWindowClassNR", True, 100, WindowRole.WELCOME),
    ("Other utility", "wxWindowClassNR", True, 0, WindowRole.MODAL),
    ("Audacity", "OtherClass", True, 0, WindowRole.MODAL),
    ("", "wxWindowNR", True, 0, WindowRole.OTHER),
])
def test_conservative_window_classification(title, cls, enabled, owner, role):
    assert aw._role(title, cls, enabled, owner) == role.value


def test_capture_timeout_and_identity_refusal(monkeypatch, tmp_path):
    backend, _, runner = owned(monkeypatch, tmp_path)
    runner.side_effect = aw.subprocess.TimeoutExpired("helper", 0.1)
    with pytest.raises(aw.OwnedWindowError, match="capture_identity_mismatch"):
        backend.capture(100, 43, backend.creation_time, "modal", 1)
    assert runner.call_count == 1
    with pytest.raises(aw.OwnedWindowError, match="native_deadline"):
        backend.capture(100, 42, backend.creation_time, "modal", 0.1)
    assert runner.call_args.kwargs["timeout"] == 0.1


def test_helper_error_is_redacted(monkeypatch, tmp_path):
    backend, _, runner = owned(monkeypatch, tmp_path)
    runner.side_effect = RuntimeError("secret token")
    with pytest.raises(aw.OwnedWindowError, match="^native_helper_failed$") as failure:
        backend.observe(42)
    assert failure.value.__cause__ is None


@pytest.mark.parametrize("payload", [[], {"ok": False}, {"ok": True, "pid": 42}])
def test_missing_or_malformed_native_receipt_blocks(monkeypatch, tmp_path, payload):
    backend, replies, _ = owned(monkeypatch, tmp_path)
    replies.append(payload)
    with pytest.raises(aw.OwnedWindowError):
        backend.observe(42)


def test_capture_rejects_empty_pixels_and_still_releases_gdi():
    native = native_pixels()
    native.gdi.GetDIBits = Mock(return_value=2)
    with pytest.raises(aw.OwnedWindowError, match="capture_pixels_empty"):
        native.pixels(100, 2, 2)
    native.gdi.DeleteObject.assert_called_once_with(12)
    native.gdi.DeleteDC.assert_called_once_with(11)
    native.user.ReleaseDC.assert_called_once_with(100, 10)


def native_pixels(*, print_ok=True, dib_rows=2, delete_ok=True):
    native = object.__new__(aw._NativeWindows)
    native.user = SimpleNamespace(GetWindowDC=Mock(return_value=10),
                                 ReleaseDC=Mock(return_value=1),
                                 PrintWindow=Mock(return_value=print_ok))

    def dib(_dc, _bitmap, _start, _height, pixels, _info, _usage):
        ctypes.memset(pixels, 127, 16)
        return dib_rows

    native.gdi = SimpleNamespace(CreateCompatibleDC=Mock(return_value=11),
        CreateCompatibleBitmap=Mock(return_value=12), SelectObject=Mock(return_value=13),
        DeleteObject=Mock(return_value=delete_ok), DeleteDC=Mock(return_value=1),
        GetDIBits=Mock(side_effect=dib))
    return native


@pytest.mark.parametrize("print_ok,dib_rows,delete_ok,success", [
    (True, 2, True, True), (False, 2, True, False),
    (True, 0, True, False), (True, 2, False, False),
])
def test_owned_capture_gdi_cleanup(print_ok, dib_rows, delete_ok, success):
    native = native_pixels(print_ok=print_ok, dib_rows=dib_rows, delete_ok=delete_ok)
    if success:
        image = native.pixels(100, 2, 2)
        assert image[:2] == b"BM" and len(image) == 70
    else:
        with pytest.raises(aw.OwnedWindowError):
            native.pixels(100, 2, 2)
    native.user.GetWindowDC.assert_called_once_with(100)
    native.gdi.DeleteObject.assert_called_once_with(12)
    native.gdi.DeleteDC.assert_called_once_with(11)
    native.user.ReleaseDC.assert_called_once_with(100, 10)


def test_capture_cleanup_continues_after_api_exception():
    native = native_pixels()
    native.gdi.DeleteObject.side_effect = OSError("delete failed")
    with pytest.raises(aw.OwnedWindowError, match="capture_cleanup_failed"):
        native.pixels(100, 2, 2)
    native.gdi.DeleteDC.assert_called_once_with(11)
    native.user.ReleaseDC.assert_called_once_with(100, 10)


def test_capture_reused_hwnd_creates_no_artifacts(tmp_path):
    native = object.__new__(aw._NativeWindows)
    native.identity = Mock(return_value=IDENTITY)
    native.window = Mock(side_effect=[{
        "hwnd": 100, "pid": 42, "visible": True, "rect": [0, 0, 2, 2],
    }, aw.OwnedWindowError("window_identity_mismatch")])
    native.pixels = Mock(return_value=b"fake")
    with pytest.raises(aw.OwnedWindowError, match="window_identity_mismatch"):
        native.capture({"pid": 42, "hwnd": 100, "evidence_dir": str(tmp_path), "reason": "modal"})
    assert not list(tmp_path.iterdir())


def test_exclusive_capture_receipt_and_parent_validation(monkeypatch, tmp_path):
    native = native_pixels()
    native.identity = Mock(return_value={k: v for k, v in IDENTITY.items() if k != "ok"})
    native.window = Mock(return_value={"hwnd": 100, "pid": 42, "visible": True,
        "rect": [0, 0, 2, 2], "role": "welcome", "modal": True})
    receipt = native.capture({"pid": 42, "hwnd": 100, "evidence_dir": str(tmp_path), "reason": "welcome"})
    assert Path(receipt["image_path"]).read_bytes()[:2] == b"BM"
    assert json.loads(Path(receipt["receipt_path"]).read_text())["hwnd"] == 100
    backend, replies, _ = owned(monkeypatch, tmp_path)
    replies.append({"ok": True, **receipt})
    assert backend.capture(100, 42, backend.creation_time, "welcome", 1)["sha256"] == receipt["sha256"]


def test_native_window_pid_is_verified_before_capture():
    native = object.__new__(aw._NativeWindows)

    def foreign_pid(_hwnd, pointer):
        ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD)).contents.value = 43
        return 1

    native.user = SimpleNamespace(IsWindow=Mock(return_value=True),
                                 GetWindowThreadProcessId=Mock(side_effect=foreign_pid))
    with pytest.raises(aw.OwnedWindowError, match="window_identity_mismatch"):
        native.window(100, 42)
