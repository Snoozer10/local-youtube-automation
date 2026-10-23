"""Browser failover may terminate only a listener launched by this workspace."""

import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from youtube_automation.core import utils


def test_profile_switch_commits_state_only_after_verified_owned_launch(monkeypatch):
    state = []
    registry = {}
    monkeypatch.setattr(utils, "get_runtime_state", lambda *_: "2")
    monkeypatch.setattr(utils, "get_config_value", lambda key, default: default)
    monkeypatch.setattr(utils, "is_port_in_use", lambda _port: bool(registry))
    monkeypatch.setattr(utils, "kill_cdp_chrome", lambda _port: registry.clear() is None)

    def launch(_browser, profile, port):
        registry[str(port)] = {"profile": utils.map_profile_index(profile)}
        return True

    monkeypatch.setattr(utils, "launch_browser_with_profile", launch)
    monkeypatch.setattr(utils, "_read_owned_browsers", lambda: dict(registry))
    monkeypatch.setattr(utils, "set_runtime_state", lambda key, value: state.append((key, value)))

    assert utils.switch_owned_browser_profile("3") is True
    assert state == [("ACTIVE_PROFILE_INDEX", "3")]
    assert registry["9222"]["profile"] == "Profile 2"


def test_profile_switch_keeps_state_and_rolls_back_after_unverified_launch(monkeypatch):
    state = []
    launches = []
    registry = {"9222": {"profile": "Profile 1"}}
    monkeypatch.setattr(utils, "get_runtime_state", lambda *_: "2")
    monkeypatch.setattr(utils, "get_config_value", lambda key, default: default)
    monkeypatch.setattr(utils, "is_port_in_use", lambda _port: bool(registry))
    monkeypatch.setattr(utils, "kill_cdp_chrome", lambda _port: registry.clear() is None)

    def launch(_browser, profile, port):
        launches.append(str(profile))
        if str(profile) == "2":
            registry[str(port)] = {"profile": "Profile 1"}
            return True
        return False

    monkeypatch.setattr(utils, "launch_browser_with_profile", launch)
    monkeypatch.setattr(utils, "_read_owned_browsers", lambda: dict(registry))
    monkeypatch.setattr(utils, "set_runtime_state", lambda key, value: state.append((key, value)))

    assert utils.switch_owned_browser_profile("3") is False
    assert state == []
    assert launches == ["3", "2"]


def test_quota_failover_switches_next_profile_only_after_verification(monkeypatch):
    switched = []
    notified = []
    monkeypatch.setattr(utils, "get_runtime_state", lambda *_: "Profile 4")
    monkeypatch.setattr(
        utils, "switch_owned_browser_profile", lambda target: switched.append(target) or True
    )
    monkeypatch.setattr(utils, "send_telegram_notification", notified.append)

    assert utils.failover_owned_browser_profile() == 5
    assert switched == [5]
    assert notified and "Account 5" in notified[0]
    assert utils.next_profile_index(5) == 2


def test_quota_failover_does_not_notify_or_advance_after_failed_switch(monkeypatch):
    notified = []
    monkeypatch.setattr(utils, "get_runtime_state", lambda *_: "3")
    monkeypatch.setattr(utils, "switch_owned_browser_profile", lambda _target: False)
    monkeypatch.setattr(utils, "send_telegram_notification", notified.append)

    import pytest

    with pytest.raises(RuntimeError, match="account 3 to account 4"):
        utils.failover_owned_browser_profile()
    assert notified == []


def test_unregistered_cdp_listener_is_never_terminated(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "OWNED_BROWSER_REGISTRY", tmp_path / "owned.json")
    monkeypatch.setattr(utils, "is_port_in_use", lambda _port: True)
    monkeypatch.setattr(
        utils.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Unregistered listener must not be queried or terminated")
        ),
    )
    assert utils.kill_cdp_chrome(9222) is False


def _browser_facts(
    pid=4321,
    *,
    executable=r"C:\Chrome\chrome.exe",
    user_data_dir=r"C:\ChromeDebugProfile",
    profile="Profile 2",
    creation_time=1234.5,
):
    return {
        "pid": pid,
        "creation_time": creation_time,
        "executable": executable,
        "cmdline": [
            executable,
            f"--user-data-dir={user_data_dir}",
            f"--profile-directory={profile}",
        ],
    }


def _ownership_record(facts):
    return {
        "pid": facts["pid"],
        "creation_time": facts["creation_time"],
        "executable": utils._normalized_browser_path(facts["executable"]),
        "user_data_dir": utils._normalized_browser_path(
            facts["cmdline"][1].split("=", 1)[1]
        ),
        "profile": facts["cmdline"][2].split("=", 1)[1],
    }


def _forbid_taskkill(monkeypatch):
    monkeypatch.setattr(
        utils.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Rejected browser identity must never reach taskkill")
        ),
    )


def test_registered_listener_terminates_only_exact_verified_process(tmp_path, monkeypatch):
    facts = _browser_facts()
    monkeypatch.setattr(utils, "OWNED_BROWSER_REGISTRY", tmp_path / "owned.json")
    utils._write_owned_browsers({"9222": _ownership_record(facts)})
    monkeypatch.setattr(utils, "_listener_pids", lambda _port: {facts["pid"]})
    monkeypatch.setattr(utils, "_browser_process_facts", lambda _pid: facts)
    monkeypatch.setattr(utils, "is_port_in_use", lambda _port: False)
    calls = []

    def run(args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(utils.subprocess, "run", run)
    assert utils.kill_cdp_chrome(9222) is True
    assert calls == [["taskkill", "/F", "/T", "/PID", str(facts["pid"])]]
    assert utils._read_owned_browsers() == {}


@pytest.mark.parametrize(
    "field,value",
    [
        ("executable", r"C:\Other\chrome.exe"),
        ("user_data_dir", r"C:\OtherProfile"),
        ("profile", "Profile 9"),
        ("creation_time", 1234.6),
    ],
)
def test_reused_or_mismatched_process_identity_never_reaches_taskkill(
    tmp_path, monkeypatch, field, value
):
    registered = _browser_facts()
    current = _browser_facts()
    if field == "executable":
        current["executable"] = value
    elif field == "user_data_dir":
        current["cmdline"][1] = f"--user-data-dir={value}"
    elif field == "profile":
        current["cmdline"][2] = f"--profile-directory={value}"
    else:
        current[field] = value
    monkeypatch.setattr(utils, "OWNED_BROWSER_REGISTRY", tmp_path / "owned.json")
    utils._write_owned_browsers({"9222": _ownership_record(registered)})
    monkeypatch.setattr(utils, "_listener_pids", lambda _port: {registered["pid"]})
    monkeypatch.setattr(utils, "_browser_process_facts", lambda _pid: current)
    _forbid_taskkill(monkeypatch)
    assert utils.kill_cdp_chrome(9222) is False


def test_legacy_registry_without_creation_time_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "OWNED_BROWSER_REGISTRY", tmp_path / "owned.json")
    utils._write_owned_browsers(
        {"9222": {"pid": 4321, "executable": r"C:\Chrome\chrome.exe"}}
    )
    monkeypatch.setattr(
        utils,
        "_browser_process_facts",
        lambda _pid: pytest.fail("legacy record must fail before inspection"),
    )
    _forbid_taskkill(monkeypatch)
    assert utils.kill_cdp_chrome(9222) is False


def test_foreign_listener_or_listener_race_never_reaches_taskkill(tmp_path, monkeypatch):
    facts = _browser_facts()
    monkeypatch.setattr(utils, "OWNED_BROWSER_REGISTRY", tmp_path / "owned.json")
    utils._write_owned_browsers({"9222": _ownership_record(facts)})
    listeners = iter([{facts["pid"]}, {9999}])
    monkeypatch.setattr(utils, "_listener_pids", lambda _port: next(listeners))
    monkeypatch.setattr(utils, "_browser_process_facts", lambda _pid: facts)
    _forbid_taskkill(monkeypatch)
    assert utils.kill_cdp_chrome(9222) is False


class _FakeBrowserProcess:
    def __init__(self, pid):
        self.pid = pid
        self.terminated = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True


class _SuccessfulResponse:
    status = 200

    def __init__(self, body=None):
        self.body = body or (
            b'{"Browser":"Chrome/123.0",'
            b'"webSocketDebuggerUrl":"ws://127.0.0.1:9222/devtools/browser/test"}'
        )

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _prepare_launch(tmp_path, monkeypatch, *, listener_sets, facts):
    process = _FakeBrowserProcess(4321)
    monkeypatch.setattr(utils, "map_profile_index", lambda _index: "Profile 2")
    monkeypatch.setattr(utils, "get_chrome_path", lambda: r"C:\Chrome\chrome.exe")
    monkeypatch.setattr(
        utils,
        "get_config_value",
        lambda key, default: str(tmp_path) if "USER_DATA_DIR" in key else default,
    )
    monkeypatch.setattr(utils, "is_port_in_use", lambda _port: False)
    monkeypatch.setattr(utils.subprocess, "Popen", lambda _cmd: process)
    monkeypatch.setattr(
        utils.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _SuccessfulResponse(),
    )
    monkeypatch.setattr(utils.time, "sleep", lambda _seconds: None)
    listeners = iter(listener_sets)
    monkeypatch.setattr(utils, "_listener_pids", lambda _port: next(listeners))
    monkeypatch.setattr(utils, "_browser_process_facts", lambda _pid: facts)
    monkeypatch.setattr(utils, "OWNED_BROWSER_REGISTRY", tmp_path / "owned.json")
    return process


def test_launch_rejects_a_sole_foreign_listener_instead_of_adopting_it(
    tmp_path, monkeypatch
):
    facts = _browser_facts(user_data_dir=str(tmp_path))
    process = _prepare_launch(tmp_path, monkeypatch, listener_sets=[{9999}], facts=facts)
    assert utils.launch_browser_with_profile("chrome", 2, 9222) is False
    assert process.terminated is True
    assert utils._read_owned_browsers() == {}


@pytest.mark.parametrize(
    "field,value",
    [
        ("executable", r"C:\Other\chrome.exe"),
        ("user_data_dir", r"C:\OtherProfile"),
        ("profile", "Profile 8"),
    ],
)
def test_launch_rejects_wrong_image_or_profile(tmp_path, monkeypatch, field, value):
    facts = _browser_facts(user_data_dir=str(tmp_path))
    if field == "executable":
        facts["executable"] = value
    elif field == "user_data_dir":
        facts["cmdline"][1] = f"--user-data-dir={value}"
    else:
        facts["cmdline"][2] = f"--profile-directory={value}"
    process = _prepare_launch(
        tmp_path, monkeypatch, listener_sets=[{4321}, {4321}], facts=facts
    )
    assert utils.launch_browser_with_profile("chrome", 2, 9222) is False
    assert process.terminated is True
    assert utils._read_owned_browsers() == {}


def test_launch_rejects_listener_change_before_registration(tmp_path, monkeypatch):
    facts = _browser_facts(user_data_dir=str(tmp_path))
    process = _prepare_launch(
        tmp_path, monkeypatch, listener_sets=[{4321}, {9999}], facts=facts
    )
    assert utils.launch_browser_with_profile("chrome", 2, 9222) is False
    assert process.terminated is True
    assert utils._read_owned_browsers() == {}


def test_valid_launch_records_exact_process_identity_and_preserves_profile_locks(
    tmp_path, monkeypatch
):
    profile_root = tmp_path / "Profile 2"
    lock_names = [
        "SingletonLock",
        "SingletonSocket",
        "SingletonCookie",
        "lockfile",
        "Preferences.bad",
    ]
    for directory in (tmp_path, profile_root):
        directory.mkdir(exist_ok=True)
        for name in lock_names:
            (directory / name).write_bytes(name.encode())
    sessions_dir = profile_root / "Sessions"
    sessions_dir.mkdir()
    session_file = sessions_dir / "Session_1"
    session_file.write_bytes(b"recoverable session data")
    before = {
        str(path): path.read_bytes()
        for directory in (tmp_path, profile_root)
        for path in (directory / name for name in lock_names)
    }
    before[str(session_file)] = session_file.read_bytes()
    facts = _browser_facts(user_data_dir=str(tmp_path))
    process = _prepare_launch(
        tmp_path, monkeypatch, listener_sets=[{4321}, {4321}], facts=facts
    )
    assert utils.launch_browser_with_profile("chrome", 2, 9222) is True
    record = utils._read_owned_browsers()["9222"]
    assert record["pid"] == process.pid
    assert record["creation_time"] == facts["creation_time"]
    assert record["executable"] == utils._normalized_browser_path(facts["executable"])
    assert record["user_data_dir"] == utils._normalized_browser_path(str(tmp_path))
    assert record["profile"] == "Profile 2"
    assert before == {path: Path(path).read_bytes() for path in before}


def test_launch_retries_connection_refused_until_cdp_is_ready(tmp_path, monkeypatch):
    facts = _browser_facts(user_data_dir=str(tmp_path))
    process = _prepare_launch(
        tmp_path, monkeypatch, listener_sets=[{4321}, {4321}], facts=facts
    )
    calls = []

    def urlopen(*_args, **_kwargs):
        calls.append(None)
        if len(calls) == 1:
            raise urllib.error.URLError(ConnectionRefusedError("starting"))
        return _SuccessfulResponse()

    monkeypatch.setattr(utils.urllib.request, "urlopen", urlopen)
    assert utils.launch_browser_with_profile("chrome", 2, 9222) is True
    assert len(calls) == 2
    assert process.terminated is False
    assert utils._read_owned_browsers()["9222"]["pid"] == process.pid


def test_launch_stops_after_fifteen_startup_transport_timeouts(tmp_path, monkeypatch):
    facts = _browser_facts(user_data_dir=str(tmp_path))
    process = _prepare_launch(tmp_path, monkeypatch, listener_sets=[], facts=facts)
    calls = []

    def urlopen(*_args, **_kwargs):
        calls.append(None)
        raise urllib.error.URLError(TimeoutError("not ready"))

    monkeypatch.setattr(utils.urllib.request, "urlopen", urlopen)
    assert utils.launch_browser_with_profile("chrome", 2, 9222) is False
    assert len(calls) == 15
    assert process.terminated is True
    assert utils._read_owned_browsers() == {}


@pytest.mark.parametrize("body", [b"{", b"{}"])
def test_launch_rejects_malformed_cdp_response_without_retry(tmp_path, monkeypatch, body):
    facts = _browser_facts(user_data_dir=str(tmp_path))
    process = _prepare_launch(
        tmp_path, monkeypatch, listener_sets=[], facts=facts
    )
    calls = []
    monkeypatch.setattr(
        utils.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (calls.append(None) or _SuccessfulResponse(body)),
    )
    assert utils.launch_browser_with_profile("chrome", 2, 9222) is False
    assert len(calls) == 1
    assert process.terminated is True
    assert utils._read_owned_browsers() == {}
