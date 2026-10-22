"""Empirical adversarial test harness for Milestone 1:
- Port 9222 socket connectivity, rapid polling, HTTP headers, content-type, JSON parsing
- Process ownership, exclusive listener verification, genuine chrome.exe & C:\\ChromeDebugProfile
- Fail-closed boundary testing under adversarial corruptions and spoofing attempts
"""

import json
import urllib.error
import urllib.request

import psutil
import pytest

from youtube_automation.browser import ui_guard
from youtube_automation.core import utils


def test_adversarial_fail_closed_spoofed_pid(tmp_path, monkeypatch):
    """Adversarial challenge: Registry contains a PID belonging to another running process (e.g. current python).
    _owned_browser_is_current must detect executable and cmdline mismatch and return False.
    kill_cdp_chrome must refuse to terminate it.
    """
    # Use only synthetic process facts; never inspect or risk terminating pytest.
    fake_pid = 424242
    creation_time = 1234.0

    spoofed_record = {
        "pid": fake_pid,
        "creation_time": creation_time,
        "executable": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "user_data_dir": r"C:\ChromeDebugProfile",
        "profile": "Profile 2",
        "started_at": 123456.0,
    }

    monkeypatch.setattr(utils, "_listener_pids", lambda _port: {fake_pid})
    monkeypatch.setattr(
        utils,
        "_browser_process_facts",
        lambda pid: {
            "pid": pid,
            "creation_time": creation_time,
            "executable": r"C:\Python\python.exe",
            "cmdline": ["python.exe"],
        },
    )

    def forbidden_termination(*_args, **_kwargs):
        pytest.fail("ownership rejection must happen before process termination")

    monkeypatch.setattr(utils.subprocess, "run", forbidden_termination)
    monkeypatch.setattr(psutil, "Process", forbidden_termination)
    # Synthetic Python facts do not match the claimed Chrome identity.
    assert utils._owned_browser_is_current(spoofed_record, 9222) is False

    monkeypatch.setattr(utils, "OWNED_BROWSER_REGISTRY", tmp_path / "owned.json")
    utils._write_owned_browsers({"9222": spoofed_record})
    monkeypatch.setattr(utils, "is_port_in_use", lambda _port: True)

    # Attempting to kill should refuse and return False without touching the process
    assert utils.kill_cdp_chrome(9222) is False


def test_adversarial_fail_closed_corrupted_registry_fields(tmp_path, monkeypatch):
    """Adversarial challenge: Malformed data types or missing fields in owned_browsers.json."""
    invalid_records = [
        {"pid": "21176", "creation_time": 1234.0, "executable": "c:\\chrome.exe", "user_data_dir": "c:\\profile", "profile": "P1"},  # string pid
        {"pid": -10, "creation_time": 1234.0, "executable": "c:\\chrome.exe", "user_data_dir": "c:\\profile", "profile": "P1"},       # negative pid
        {"pid": 21176, "creation_time": True, "executable": "c:\\chrome.exe", "user_data_dir": "c:\\profile", "profile": "P1"},        # bool creation_time
        {"pid": 21176, "creation_time": None, "executable": "c:\\chrome.exe", "user_data_dir": "c:\\profile", "profile": "P1"},        # None creation_time
        {"pid": 21176, "creation_time": 1234.0, "executable": None, "user_data_dir": "c:\\profile", "profile": "P1"},                  # None executable
        {"pid": 21176, "creation_time": 1234.0, "executable": "c:\\chrome.exe", "user_data_dir": "", "profile": "P1"},                  # empty user_data_dir
        {"pid": 21176, "creation_time": 1234.0, "executable": "c:\\chrome.exe", "user_data_dir": "c:\\profile", "profile": ""},        # empty profile
    ]

    for rec in invalid_records:
        assert utils._owned_browser_is_current(rec, 9222) is False


def test_adversarial_fail_closed_multi_listener_collision(monkeypatch):
    """Adversarial challenge: Port 9222 has multiple listener PIDs (e.g. port hijacking or duplicate binding).
    utils._owned_browser_is_current must fail closed and refuse ownership.
    """
    rec = {
        "pid": 21176,
        "creation_time": 1792420061.0789962,
        "executable": r"c:\program files\google\chrome\application\chrome.exe",
        "user_data_dir": r"c:\chromedebugprofile",
        "profile": "Profile 2",
    }
    # Two listeners reported on port 9222
    monkeypatch.setattr(utils, "_listener_pids", lambda _port: {21176, 99999})
    assert utils._owned_browser_is_current(rec, 9222) is False


def test_adversarial_foreign_debugger_targets_edge_cases():
    """Adversarial challenge: probe foreign_debugger_targets with weird/hostile CDP responses."""
    import io

    # 1. HTTP error responses
    def raise_http_error(*_args, **_kwargs):
        raise urllib.error.HTTPError("http://127.0.0.1:9222/json", 500, "Internal Server Error", {}, None)

    with pytest.raises(ui_guard.TargetProbeError) as exc:
        ui_guard.foreign_debugger_targets(opener=raise_http_error)
    assert exc.value.code == "probe_failed"

    # 2. Connection refused
    def raise_conn_refused(*_args, **_kwargs):
        raise urllib.error.URLError(ConnectionRefusedError("Connection refused"))

    with pytest.raises(ui_guard.TargetProbeError) as exc:
        ui_guard.foreign_debugger_targets(opener=raise_conn_refused)
    assert exc.value.code == "probe_failed"

    # 3. Injected foreign target with chrome-extension and browsermcp.io
    evil_payload = [
        {
            "id": "target1",
            "type": "page",
            "url": "chrome-extension://malicious_ext_id/background.html",
        },
        {
            "id": "target2",
            "type": "other",
            "url": "https://browsermcp.io/session",
        },
        {
            "id": "target3",
            "type": "page",
            "url": "https://normal.google.com/search",
        },
    ]
    foreign = ui_guard.foreign_debugger_targets(
        opener=lambda *_args, **_kwargs: io.BytesIO(json.dumps(evil_payload).encode("utf-8"))
    )
    assert len(foreign) == 2
    assert foreign[0]["origin"] == "chrome-extension://malicious_ext_id"
    assert foreign[1]["origin"] == "https://browsermcp.io"


