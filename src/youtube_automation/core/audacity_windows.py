"""Owned Audacity HWND inspection and capture in a disposable native helper.

No desktop DC, window activation, dismissal or input is used. Native calls run
only in the helper, which its parent kills on timeout, including a hung PrintWindow.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import math
import ntpath
import os
import struct
import subprocess
import sys
import uuid
from collections.abc import Callable
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from youtube_automation.core.window_readiness import (
    ProcessLike,
    WindowObservation,
    WindowRole,
    WindowSnapshot,
)

MAX_WINDOWS = 64
MAX_PIXELS = 16_000_000
MAX_HELPER_OUTPUT = 65_536


class _IdentityRequestRequired(TypedDict):
    pid: int
    executable: str


class _IdentityRequest(_IdentityRequestRequired, total=False):
    creation_ticks: str


class _CaptureRequest(_IdentityRequest):
    hwnd: int
    evidence_dir: str
    reason: str


class _NativeIdentity(TypedDict):
    pid: int
    executable: str
    creation_ticks: str
    creation_time: float


class _NativeWindow(TypedDict):
    hwnd: int
    pid: int
    visible: bool
    role: str
    modal: bool
    class_name: str
    title_hash: str
    rect: list[int]


class _NativeObservation(_NativeIdentity):
    windows: list[_NativeWindow]


class _NativeCapture(_NativeIdentity):
    hwnd: int
    utc: str
    reason: str
    image_path: str
    receipt_path: str
    sha256: str
    width: int
    height: int
    window: _NativeWindow


class OwnedWindowError(RuntimeError):
    """A redacted failure; callers must not continue to pipe commands."""


def _path_key(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(path))


class OwnedAudacityWindows:
    """Verify the launched process, then observe/capture only its HWNDs."""

    def __init__(
        self, process: ProcessLike, executable_path: str | Path, evidence_dir: str | Path,
    ) -> None:
        self.process = process
        self.pid = process.pid
        self.executable = str(executable_path)
        self.evidence_dir = Path(evidence_dir).resolve()
        if type(self.pid) is not int or self.pid <= 0 or process.poll() is not None:
            raise OwnedWindowError("owned_process_exited")
        self._identity = self._invoke("identity", {}, 2.0)
        self.creation_time = self._check_identity(self._identity, first=True)
        if process.poll() is not None:
            raise OwnedWindowError("owned_process_exited")

    def _invoke(self, action: str, extra: dict[str, str | int], timeout: float) -> dict[str, Any]:
        # Native-helper stdout is untrusted JSON, validated by the action-specific guards.
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise OwnedWindowError("native_deadline")
        request: dict[str, str | int] = {"action": action, "pid": self.pid, "executable": self.executable}
        if hasattr(self, "_identity"):
            request["creation_ticks"] = self._identity["creation_ticks"]
        request.update(extra)
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--native-helper"],
                input=json.dumps(request), text=True, encoding="utf-8",
                capture_output=True,
                timeout=min(timeout, 5.0), check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode or len(result.stdout) > MAX_HELPER_OUTPUT:
                self._record_helper_failure(request, result)
                raise OwnedWindowError("native_helper_failed")
            response = json.loads(result.stdout)
            if not isinstance(response, dict) or response.get("ok") is not True:
                self._record_helper_failure(request, result, response)
                raise OwnedWindowError("native_helper_failed")
            return response
        except subprocess.TimeoutExpired:
            raise OwnedWindowError("native_deadline") from None
        except OwnedWindowError:
            raise
        except Exception as exc:
            self._record_helper_failure(request, None, str(exc))
            raise OwnedWindowError("native_helper_failed") from None

    def _record_helper_failure(
        self, request: dict[str, str | int], result: subprocess.CompletedProcess[str] | None,
        extra: object = None,
    ) -> None:
        try:
            if hasattr(self, "evidence_dir") and self.evidence_dir:
                self.evidence_dir.mkdir(parents=True, exist_ok=True)
                log_file = self.evidence_dir / "native_helper_failure.json"
                data = {
                    "action": request.get("action"),
                    "request": request,
                    "returncode": result.returncode if result else None,
                    "stdout": result.stdout[:2048] if result and result.stdout else None,
                    "stderr": result.stderr[:2048] if result and result.stderr else None,
                    "extra": extra,
                }
                log_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _check_identity(self, identity: dict[str, Any], *, first: bool = False) -> float:
        creation = identity.get("creation_time")
        ticks = identity.get("creation_ticks")
        if (
            type(identity.get("pid")) is not int or identity.get("pid") != self.pid
            or not isinstance(identity.get("executable"), str)
            or _path_key(identity["executable"]) != _path_key(self.executable)
            or type(creation) not in (int, float) or not isinstance(creation, (int, float)) or not math.isfinite(creation)
            or creation <= 0 or not isinstance(ticks, str)
            or not (1 <= len(ticks) <= 20) or not ticks.isascii() or not ticks.isdigit()
            or int(ticks) <= 0
            or (not first and ticks != self._identity["creation_ticks"])
            or (not first and creation != self.creation_time)
        ):
            raise OwnedWindowError("process_identity_mismatch")
        return creation

    def observe(self, pid: int) -> WindowSnapshot:
        if pid != self.pid or self.process.poll() is not None:
            raise OwnedWindowError("owned_process_exited_or_mismatched")
        result = self._invoke("observe", {}, 2.0)
        self._check_identity(result)
        rows = result.get("windows")
        if not isinstance(rows, list) or len(rows) > MAX_WINDOWS:
            raise OwnedWindowError("invalid_window_observation")
        windows = []
        for row in rows:
            if (not isinstance(row, dict) or type(row.get("hwnd")) is not int
                or row["hwnd"] <= 0 or row.get("pid") != self.pid
                or type(row.get("visible")) is not bool
                or type(row.get("modal")) is not bool):
                raise OwnedWindowError("invalid_window_observation")
            try:
                role = WindowRole(row["role"])
            except (KeyError, ValueError, TypeError):
                raise OwnedWindowError("invalid_window_observation") from None
            windows.append(WindowObservation(row["hwnd"], self.pid, role,
                                             row["visible"], row["modal"]))
        if self.process.poll() is not None:
            raise OwnedWindowError("owned_process_exited")
        try:
            if hasattr(self, "evidence_dir") and self.evidence_dir:
                self.evidence_dir.mkdir(parents=True, exist_ok=True)
                with (self.evidence_dir / "observations.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "windows": [
                            {"hwnd": w.hwnd, "role": w.role.value, "modal": w.modal, "visible": w.visible}
                            for w in windows
                        ]
                    }) + "\n")
        except Exception:
            pass
        return WindowSnapshot(self.pid, self.creation_time, self.executable, windows)

    def capture(
        self, hwnd: int, pid: int, creation_time: float, reason: str, timeout: float,
    ) -> dict[str, Any]:
        if (type(hwnd) is not int or hwnd <= 0 or pid != self.pid
            or creation_time != self.creation_time or self.process.poll() is not None):
            raise OwnedWindowError("capture_identity_mismatch")
        result = self._invoke("capture", {
            "hwnd": hwnd, "evidence_dir": str(self.evidence_dir),
            "reason": str(reason)[:120],
        }, timeout)
        self._check_identity(result)
        if result.get("hwnd") != hwnd:
            raise OwnedWindowError("capture_identity_mismatch")
        try:
            path = Path(result["image_path"]).resolve()
            if path.parent != self.evidence_dir:
                raise ValueError
            size = path.stat().st_size
            if size < 58 or size > MAX_PIXELS * 4 + 54:
                raise ValueError
            data = path.read_bytes()
            if data[:2] != b"BM" or hashlib.sha256(data).hexdigest() != result["sha256"]:
                raise ValueError
            if self.process.poll() is not None:
                raise ValueError
        except Exception:
            raise OwnedWindowError("capture_evidence_invalid") from None
        return result


def _role(title: str, class_name: str, enabled: bool, owner: int) -> str:
    title = title.strip().casefold()
    if title == "automatic crash recovery":
        return WindowRole.RECOVERY.value
    if title in ("welcome to audacity!", "welcome to audacity", "welcome"):
        return WindowRole.WELCOME.value
    if (enabled and not owner and (class_name.startswith("wxWindowClass") or class_name.startswith("wxWindow"))
        and (title == "audacity" or title.endswith(" - audacity"))):
        return WindowRole.MAIN.value
    if ("starting up" in title or "splash" in title) or (not title and not owner and class_name.startswith("wxWindow")):
        return WindowRole.OTHER.value
    return WindowRole.MODAL.value


class _NativeWindows:
    """ctypes calls; construct only inside the bounded child process."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise OwnedWindowError("windows_backend_required")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        signatures = [
            (self.kernel, "OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            (self.kernel, "CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
            (self.kernel, "GetExitCodeProcess", [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            (self.kernel, "GetProcessTimes", [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4, wintypes.BOOL),
            (self.kernel, "QueryFullProcessImageNameW", [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            (self.user, "EnumWindows", [self.callback_type, wintypes.LPARAM], wintypes.BOOL),
            (self.user, "GetWindowThreadProcessId", [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            (self.user, "IsWindow", [wintypes.HWND], wintypes.BOOL),
            (self.user, "IsWindowVisible", [wintypes.HWND], wintypes.BOOL),
            (self.user, "IsWindowEnabled", [wintypes.HWND], wintypes.BOOL),
            (self.user, "GetWindow", [wintypes.HWND, wintypes.UINT], wintypes.HWND),
            (self.user, "GetWindowTextW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            (self.user, "GetClassNameW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            (self.user, "GetWindowRect", [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            (self.user, "GetWindowDC", [wintypes.HWND], wintypes.HDC),
            (self.user, "ReleaseDC", [wintypes.HWND, wintypes.HDC], ctypes.c_int),
            (self.user, "PrintWindow", [wintypes.HWND, wintypes.HDC, wintypes.UINT], wintypes.BOOL),
            (self.gdi, "CreateCompatibleDC", [wintypes.HDC], wintypes.HDC),
            (self.gdi, "CreateCompatibleBitmap", [wintypes.HDC, ctypes.c_int, ctypes.c_int], wintypes.HBITMAP),
            (self.gdi, "SelectObject", [wintypes.HDC, wintypes.HGDIOBJ], wintypes.HGDIOBJ),
            (self.gdi, "DeleteObject", [wintypes.HGDIOBJ], wintypes.BOOL),
            (self.gdi, "DeleteDC", [wintypes.HDC], wintypes.BOOL),
            (self.gdi, "GetDIBits", [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT], ctypes.c_int),
        ]
        for library, name, args, result in signatures:
            function = getattr(library, name)
            function.argtypes, function.restype = args, result

    def identity(self, request: _IdentityRequest) -> _NativeIdentity:
        handle = self.kernel.OpenProcess(0x1000, False, request["pid"])
        if not handle:
            raise OwnedWindowError("process_open_failed")
        try:
            code = wintypes.DWORD()
            times = [wintypes.FILETIME() for _ in range(4)]
            image = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(image))
            if (not self.kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259
                or not self.kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times))
                or not self.kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length))):
                raise OwnedWindowError("process_identity_unreadable")
            ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            if (_path_key(image.value) != _path_key(request["executable"])
                or ticks <= 0 or ("creation_ticks" in request and str(ticks) != request["creation_ticks"])):
                raise OwnedWindowError("process_identity_mismatch")
            return {"pid": request["pid"], "executable": image.value,
                    "creation_ticks": str(ticks), "creation_time": ticks / 10_000_000 - 11644473600}
        finally:
            if not self.kernel.CloseHandle(handle):
                raise OwnedWindowError("process_handle_cleanup_failed")

    def window(self, hwnd: int, pid: int) -> _NativeWindow:
        owner_pid = wintypes.DWORD()
        if (not self.user.IsWindow(hwnd)
            or not self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
            or owner_pid.value != pid):
            raise OwnedWindowError("window_identity_mismatch")
        title, class_name = ctypes.create_unicode_buffer(512), ctypes.create_unicode_buffer(256)
        title_length = self.user.GetWindowTextW(hwnd, title, len(title))
        class_length = self.user.GetClassNameW(hwnd, class_name, len(class_name))
        if title_length >= 511 or class_length <= 0 or class_length >= 255:
            raise OwnedWindowError("window_metadata_unreadable")
        enabled = bool(self.user.IsWindowEnabled(hwnd))
        owner = int(self.user.GetWindow(hwnd, 4) or 0)
        rect = wintypes.RECT()
        if not self.user.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise OwnedWindowError("window_geometry_unreadable")
        role_str = _role(title.value, class_name.value, enabled, owner)
        return {"hwnd": int(hwnd), "pid": pid,
                "visible": bool(self.user.IsWindowVisible(hwnd)),
                "role": role_str,
                "modal": bool((owner or not enabled) and role_str != WindowRole.OTHER.value),
                "class_name": class_name.value,
                "title_hash": hashlib.sha256(title.value.encode("utf-8")).hexdigest(),
                "rect": [rect.left, rect.top, rect.right, rect.bottom]}

    def observe(self, request: _IdentityRequest) -> _NativeObservation:
        before = self.identity(request)
        owned: list[_NativeWindow] = []
        errors: list[str] = []

        def visit(hwnd: int, _: int) -> bool:
            try:
                pid = wintypes.DWORD()
                if not self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
                    return True
                if pid.value == request["pid"] and self.user.IsWindowVisible(hwnd):
                    cls_buf = ctypes.create_unicode_buffer(256)
                    self.user.GetClassNameW(hwnd, cls_buf, len(cls_buf))
                    cls_val = cls_buf.value
                    if cls_val.startswith("UAC") or cls_val in ("MSCTFIME UI", "CiceroUIWndFrame"):
                        return True
                    if len(owned) >= MAX_WINDOWS:
                        raise OwnedWindowError("window_count_exceeded")
                    owned.append(self.window(hwnd, request["pid"]))
                return True
            except Exception as e:
                errors.append(f"{type(e).__name__}:{e}")
                return False

        callback = self.callback_type(visit)
        enum_ok = self.user.EnumWindows(callback, 0)
        last_error = ctypes.get_last_error()
        if errors or (not enum_ok and last_error != 0):
            raise OwnedWindowError(f"window_enumeration_failed:errors={errors}:enum_ok={enum_ok}:last_error={last_error}")
        if self.identity(request) != before:
            raise OwnedWindowError("process_identity_mismatch")
        return {**before, "windows": owned}

    def pixels(self, hwnd: int, width: int, height: int) -> bytes:
        dc = memory = bitmap = previous = None
        cleanup_ok = True
        try:
            dc = self.user.GetWindowDC(hwnd)
            if not dc:
                raise OwnedWindowError("window_dc_failed")
            memory = self.gdi.CreateCompatibleDC(dc)
            if not memory:
                raise OwnedWindowError("capture_dc_failed")
            bitmap = self.gdi.CreateCompatibleBitmap(dc, width, height)
            if not bitmap:
                raise OwnedWindowError("capture_bitmap_failed")
            previous = self.gdi.SelectObject(memory, bitmap)
            if not previous or previous == ctypes.c_void_p(-1).value:
                previous = None
                raise OwnedWindowError("capture_select_failed")
            if not self.user.PrintWindow(hwnd, memory, 2):
                raise OwnedWindowError("owned_capture_failed")
            # GetDIBits requires a bitmap deselected from every DC.
            restored = self.gdi.SelectObject(memory, previous)
            if not restored or restored == ctypes.c_void_p(-1).value:
                raise OwnedWindowError("capture_deselect_failed")
            previous = None
            dib = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0,
                              width * height * 4, 0, 0, 0, 0)
            info = ctypes.create_string_buffer(dib + bytes(4))
            pixels = ctypes.create_string_buffer(width * height * 4)
            if self.gdi.GetDIBits(memory, bitmap, 0, height, pixels, info, 0) != height:
                raise OwnedWindowError("capture_pixels_failed")
            raw = pixels.raw
            if not (any(raw[0::4]) or any(raw[1::4]) or any(raw[2::4])):
                raise OwnedWindowError("capture_pixels_empty")
            return struct.pack("<2sIHHI", b"BM", 54 + len(raw), 0, 0, 54) + dib + raw
        finally:
            cleanup_calls: list[tuple[Callable[..., int], tuple[int, ...]]] = []
            if previous and memory:
                cleanup_calls.append((self.gdi.SelectObject, (memory, previous)))
            if bitmap:
                cleanup_calls.append((self.gdi.DeleteObject, (bitmap,)))
            if memory:
                cleanup_calls.append((self.gdi.DeleteDC, (memory,)))
            if dc:
                cleanup_calls.append((self.user.ReleaseDC, (hwnd, dc)))
            for function, args in cleanup_calls:
                try:
                    result = function(*args)
                    cleanup_ok = bool(result) and result != ctypes.c_void_p(-1).value and cleanup_ok
                except Exception:
                    cleanup_ok = False
            if not cleanup_ok:
                raise OwnedWindowError("capture_cleanup_failed")

    def capture(self, request: _CaptureRequest) -> _NativeCapture:
        before = self.identity(request)
        window = self.window(request["hwnd"], request["pid"])
        width = window["rect"][2] - window["rect"][0]
        height = window["rect"][3] - window["rect"][1]
        if (not window["visible"] or width <= 0 or height <= 0
            or width > 8192 or height > 8192 or width * height > MAX_PIXELS):
            raise OwnedWindowError("capture_geometry_invalid")
        image = self.pixels(request["hwnd"], width, height)
        if self.window(request["hwnd"], request["pid"]) != window or self.identity(request) != before:
            raise OwnedWindowError("capture_identity_changed")
        directory = Path(request["evidence_dir"]).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        capture_time = datetime.now(timezone.utc).isoformat()
        stem = f"audacity-{request['pid']}-{request['hwnd']}-{uuid.uuid4().hex}"
        path = directory / (stem + ".bmp")
        receipt_path = directory / (stem + ".json")
        receipt: _NativeCapture = {**before, "hwnd": request["hwnd"], "utc": capture_time,
                   "reason": request["reason"], "image_path": str(path),
                   "receipt_path": str(receipt_path), "sha256": hashlib.sha256(image).hexdigest(),
                   "width": width, "height": height, "window": window}
        with path.open("xb") as output:
            output.write(image)
        with receipt_path.open("x", encoding="utf-8") as output:
            json.dump(receipt, output, sort_keys=True)
        return receipt


def _helper_main() -> int:
    try:
        raw = sys.stdin.read(8193)
        if len(raw) > 8192:
            raise ValueError("request_too_large")
        request = json.loads(raw)
        api = _NativeWindows()
        action = request["action"]
        if action not in ("identity", "observe", "capture"):
            raise ValueError(f"invalid_action:{action}")
        result = getattr(api, action)(request)
        print(json.dumps({"ok": True, **result}, ensure_ascii=True))
        return 0
    except Exception as exc:
        err_msg = f"{type(exc).__name__}:{exc}"
        try:
            sys.stderr.write(f"helper_error:{err_msg}\n")
        except Exception:
            pass
        print(json.dumps({"ok": False, "error": err_msg}))
        return 1


if __name__ == "__main__":
    raise SystemExit(_helper_main() if sys.argv[1:] == ["--native-helper"] else 2)
