"""Unit tests: utils module health, config plumbing, runtime state, port probe."""

import importlib
import json
import socket


def test_utils_module_imports_cleanly():
    """Repro: CONFIG = PipelineConfig.from_env() executed before get_config_value
    definition -> NameError at import; every consumer module crashed."""
    sys_modules = importlib.sys.modules
    sys_modules.pop("utils", None)
    try:
        mod = importlib.import_module("utils")
        assert hasattr(mod, "CONFIG")
    finally:
        sys_modules.pop("utils", None)


class TestMapProfileIndex:
    def test_one_and_below_maps_default(self):
        from utils import map_profile_index

        assert map_profile_index("1") == "Default"
        assert map_profile_index("0") == "Default"

    def test_two_maps_profile_1(self):
        from utils import map_profile_index

        assert map_profile_index("2") == "Profile 1"
        assert map_profile_index("10") == "Profile 9"

    def test_garbage_falls_back_default(self):
        from utils import map_profile_index

        assert map_profile_index("abc") == "Default"


class TestPipelineConfigFromEnv:
    def test_defaults_applied_without_env(self, monkeypatch):
        for key in (
            "CDP_PORT", "REFINE_MODEL", "BROWSER_TYPE",
            "REFINE_PARAGRAPH_TIMEOUT", "FAILOVER_RETRY_LIMIT",
            "SWITCH_ACCOUNTS_ENABLED",
        ):
            monkeypatch.delenv(key, raising=False)
        from utils import PipelineConfig

        cfg = PipelineConfig.from_env()
        assert cfg.cdp_port == 9222
        assert cfg.model_name == "Pro"
        assert cfg.max_retries == 4
        assert cfg.switch_accounts is False

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("CDP_PORT", "9333")
        monkeypatch.setenv("FAILOVER_RETRY_LIMIT", "7")
        monkeypatch.setenv("SWITCH_ACCOUNTS_ENABLED", "true")
        from utils import PipelineConfig

        cfg = PipelineConfig.from_env()
        assert cfg.cdp_port == 9333
        assert cfg.max_retries == 7
        assert cfg.switch_accounts is True


class TestRuntimeState:
    def _patch_state_file(self, tmp_path, monkeypatch):
        import utils

        state_file = str(tmp_path / "runtime_state.json")
        monkeypatch.setattr(utils, "STATE_FILE", state_file)
        return utils

    def test_roundtrip_in_tmp_location(self, tmp_path, monkeypatch):
        utils = self._patch_state_file(tmp_path, monkeypatch)
        utils.set_runtime_state("profile_index", "3")
        assert utils.get_runtime_state("profile_index", None) == "3"

    def test_missing_key_returns_default(self, tmp_path, monkeypatch):
        utils = self._patch_state_file(tmp_path, monkeypatch)
        assert utils.get_runtime_state("nope", "fallback") == "fallback"

    def test_corrupt_state_file_recovers_default(self, tmp_path, monkeypatch):
        utils = self._patch_state_file(tmp_path, monkeypatch)
        with open(utils.STATE_FILE, "w", encoding="utf-8") as f:
            f.write("{CORRUPT")
        assert utils.get_runtime_state("k", "dflt") == "dflt"
        utils.set_runtime_state("k", "v")
        with open(utils.STATE_FILE, encoding="utf-8") as f:
            assert json.load(f)["k"] == "v"


class TestIsPortInUse:
    def test_free_ephemeral_port_is_false(self):
        from utils import is_port_in_use

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
        assert is_port_in_use(free_port) is False

    def test_bound_port_is_true(self):
        from utils import is_port_in_use

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            port = s.getsockname()[1]
            assert is_port_in_use(port) is True
