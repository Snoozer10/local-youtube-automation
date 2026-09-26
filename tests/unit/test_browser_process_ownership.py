"""Browser failover may terminate only a listener launched by this workspace."""

from types import SimpleNamespace

from youtube_automation.core import utils


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
