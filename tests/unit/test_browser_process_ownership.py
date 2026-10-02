"""Browser failover may terminate only a listener launched by this workspace."""

from types import SimpleNamespace

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


def test_registered_listener_terminates_only_exact_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "OWNED_BROWSER_REGISTRY", tmp_path / "owned.json")
    utils._write_owned_browsers({"9222": {"pid": 4321}})
    monkeypatch.setattr(utils, "_listener_pids", lambda _port: {4321, 9999})
    monkeypatch.setattr(utils, "is_port_in_use", lambda _port: False)
    calls = []

    def run(args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(utils.subprocess, "run", run)
    assert utils.kill_cdp_chrome(9222) is True
    assert calls == [["taskkill", "/F", "/T", "/PID", "4321"]]
    assert utils._read_owned_browsers() == {}


def test_registered_pid_mismatch_cannot_kill_replacement_listener(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "OWNED_BROWSER_REGISTRY", tmp_path / "owned.json")
    utils._write_owned_browsers({"9222": {"pid": 4321}})
    monkeypatch.setattr(utils, "_listener_pids", lambda _port: {9999})
    monkeypatch.setattr(utils, "is_port_in_use", lambda _port: True)
    monkeypatch.setattr(
        utils.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Mismatched listener must not be terminated")
        ),
    )
    assert utils.kill_cdp_chrome(9222) is False
