"""Opt-in live CDP/socket/process diagnostics for M1 integration review."""

import json
import os
import re
import socket
import urllib.error
import urllib.request
from pathlib import Path

import psutil
import pytest

from youtube_automation.browser import ui_guard
from youtube_automation.core import utils


@pytest.mark.live_browser
def test_empirical_live_port_9222_socket_and_rapid_polling():
    """Verify raw socket connectivity, low-latency handshake, and rapid polling stability."""
    # 1. Raw socket connectivity
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    try:
        connect_res = sock.connect_ex(("127.0.0.1", 9222))
        assert connect_res == 0, f"Raw socket connection to 127.0.0.1:9222 failed with errno {connect_res}"
    finally:
        sock.close()

    # 2. HTTP response headers and Content-Type verification
    url = "http://127.0.0.1:9222/json/version"
    req = urllib.request.Request(url, headers={"User-Agent": "EmpiricalChallenger/1.0"})
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        status = resp.status
        headers = dict(resp.headers)
        body = resp.read()

    assert status == 200, f"Expected HTTP 200, got {status}"
    content_type = headers.get("Content-Type", "")
    assert "application/json" in content_type, f"Unexpected Content-Type: {content_type}"
    assert "charset=UTF-8" in content_type or "utf-8" in content_type.lower(), f"Charset missing in Content-Type: {content_type}"

    # 3. JSON parsing and schema completeness
    data = json.loads(body.decode("utf-8"))
    assert isinstance(data, dict), f"CDP version response is not a dict: {type(data)}"

    required_keys = ["Browser", "Protocol-Version", "User-Agent", "V8-Version", "WebKit-Version", "webSocketDebuggerUrl"]
    for k in required_keys:
        assert k in data, f"Missing required key '{k}' in /json/version payload"
        assert isinstance(data[k], str) and len(data[k]) > 0, f"Key '{k}' has empty or invalid value: {data[k]}"

    assert data["Browser"].startswith("Chrome/"), f"Browser is not Chrome: {data['Browser']}"
    ws_url = data["webSocketDebuggerUrl"]
    ws_pattern = r"^ws://127\.0\.0\.1:9222/devtools/browser/[a-f0-9\-]+$"
    assert re.match(ws_pattern, ws_url), f"webSocketDebuggerUrl format mismatch: {ws_url}"

    # 4. Rapid polling stress test (50 sequential rapid requests)
    for i in range(50):
        with urllib.request.urlopen(url, timeout=2.0) as r:
            assert r.status == 200, f"Rapid polling request {i} failed with status {r.status}"
            raw = r.read()
            parsed = json.loads(raw.decode("utf-8"))
            assert parsed["webSocketDebuggerUrl"] == ws_url, f"Debugger URL drifted during rapid poll at {i}"

@pytest.mark.live_browser
def test_empirical_live_process_ownership_and_exclusive_binding():
    """Verify that PID in .runtime/owned_browsers.json is genuinely running,
    points to genuine chrome.exe, uses C:\\ChromeDebugProfile, and is the EXCLUSIVE listener on 9222.
    """
    registry_path = Path(utils.PROJECT_ROOT) / ".runtime" / "owned_browsers.json"
    assert registry_path.exists(), f"Registry file {registry_path} does not exist"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert "9222" in registry, "Port 9222 not registered in owned_browsers.json"

    rec = registry["9222"]
    pid = rec["pid"]
    assert isinstance(pid, int) and pid > 0, f"Invalid PID {pid} in registry"

    # Verify PID existence
    assert psutil.pid_exists(pid), f"Registered PID {pid} is not running!"
    proc = psutil.Process(pid)

    # Verify executable identity
    exe_path = proc.exe()
    assert os.path.exists(exe_path), f"Executable does not exist on disk: {exe_path}"
    assert os.path.basename(exe_path).lower() == "chrome.exe", f"Process exe is not chrome.exe: {exe_path}"
    assert utils._normalized_browser_path(exe_path) == utils._normalized_browser_path(rec["executable"]), (
        f"Executable path mismatch: live={exe_path} vs reg={rec['executable']}"
    )

    # Verify creation time
    live_ctime = proc.create_time()
    reg_ctime = rec["creation_time"]
    assert abs(live_ctime - reg_ctime) < 0.001, f"Process creation time mismatch: {live_ctime} vs {reg_ctime}"

    # Verify command line arguments
    cmdline = proc.cmdline()
    assert any("--remote-debugging-port=9222" in arg for arg in cmdline), f"Missing port arg in cmdline: {cmdline}"
    user_data_args = [arg.split("=", 1)[1] for arg in cmdline if arg.startswith("--user-data-dir=")]
    assert len(user_data_args) == 1, f"Expected 1 user-data-dir arg, found {user_data_args}"
    assert utils._normalized_browser_path(user_data_args[0]) == utils._normalized_browser_path(r"C:\ChromeDebugProfile"), (
        f"User data dir is not C:\\ChromeDebugProfile: {user_data_args[0]}"
    )

    profile_args = [arg.split("=", 1)[1] for arg in cmdline if arg.startswith("--profile-directory=")]
    assert len(profile_args) == 1, f"Expected 1 profile-directory arg, found {profile_args}"
    assert profile_args[0] == rec["profile"], f"Profile mismatch: {profile_args[0]} vs {rec['profile']}"

    # Verify EXCLUSIVE listener on port 9222
    listeners = utils._listener_pids(9222)
    assert listeners == {pid}, f"Port 9222 listener mismatch! Expected exclusively {{{pid}}}, found {listeners}"

    # Double-check foreign debugger targets
    foreign = ui_guard.foreign_debugger_targets(9222)
    assert len(foreign) == 0, f"Unexpected foreign debugger targets detected: {foreign}"

@pytest.mark.live_browser
def test_empirical_detailed_diagnostics():
    """Print verbatim empirical observations for report."""
    import subprocess
    import time

    print("\n" + "=" * 60)
    print("EMPIRICAL DIAGNOSTICS FOR MILESTONE 1 CHALLENGE")
    print("=" * 60)

    # 1. Socket & HTTP
    t0 = time.perf_counter()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    sock.connect(("127.0.0.1", 9222))
    sock.close()
    t_sock = (time.perf_counter() - t0) * 1000
    print(f"Socket connect latency (127.0.0.1:9222): {t_sock:.2f} ms")

    req = urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=5)
    print(f"HTTP Status: {req.status}")
    for k, v in req.headers.items():
        print(f"  Header [{k}]: {v}")
    body = req.read().decode("utf-8")
    print(f"Payload:\n{body}")

    # 2. Netstat
    print("\n--- OS TCP LISTENERS (port 9222) ---")
    netstat_out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True).stdout
    for line in netstat_out.splitlines():
        if ":9222" in line:
            print(f"  {line.strip()}")

    # 3. Process
    print("\n--- PROCESS ATTRIBUTES ---")
    reg_path = Path(utils.PROJECT_ROOT) / ".runtime" / "owned_browsers.json"
    owned = json.loads(reg_path.read_text(encoding="utf-8"))
    pid = owned["9222"]["pid"]
    p = psutil.Process(pid)
    print(f"  Registered PID: {pid}")
    print(f"  Name: {p.name()}")
    print(f"  Executable: {p.exe()}")
    print(f"  Creation Time: {p.create_time()} (registry: {owned['9222']['creation_time']})")
    has_user_data = "c:\\chromedebugprofile" in " ".join(p.cmdline()).lower()
    print(f"  User Data Dir in Cmdline: {has_user_data}")
    print(f"  Full Cmdline: {p.cmdline()}")
    print(f"  Status: {p.status()}")
    print(f"  PPID: {p.ppid()}")
    print(f"  Num Threads: {p.num_threads()}")

    # 4. Targets
    print("\n--- LIVE TARGETS (/json/list) ---")
    targets_raw = urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=5).read().decode("utf-8")
    targets = json.loads(targets_raw)
    print(f"  Total targets count: {len(targets)}")
    for t in targets:
        print(f"  Target: type={t.get('type')}, title={t.get('title')}, url={t.get('url')}")
    print("=" * 60)
