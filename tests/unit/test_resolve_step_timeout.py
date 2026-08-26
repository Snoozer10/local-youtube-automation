"""Unit tests for run_agency.resolve_step_timeout supervisor ceilings (ERR-08)."""

import pytest

import run_agency


class TestResolveStepTimeout:
    @staticmethod
    def _raw(raw):
        return lambda key, default: raw

    def test_missing_key_falls_back_to_default_ceiling(self, monkeypatch):
        monkeypatch.setattr(run_agency, "get_config_value", lambda key, default: default)
        assert run_agency.resolve_step_timeout() == 7200

    @pytest.mark.parametrize("raw", ["abc", "", None])
    def test_unparseable_value_warns_and_returns_default(self, monkeypatch, capsys, raw):
        monkeypatch.setattr(run_agency, "get_config_value", self._raw(raw))
        assert run_agency.resolve_step_timeout() == 7200
        assert "[WARNING]" in capsys.readouterr().out

    @pytest.mark.parametrize("raw", ["0", "-5"])
    def test_non_positive_value_disables_cap(self, monkeypatch, raw):
        monkeypatch.setattr(run_agency, "get_config_value", self._raw(raw))
        assert run_agency.resolve_step_timeout() == 0

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("100", 300), ("300", 300), ("5400", 5400)],
        ids=["below-floor-clamps", "at-floor-kept", "above-floor-passes"],
    )
    def test_positive_values_clamp_to_minimum_floor(self, monkeypatch, raw, expected):
        monkeypatch.setattr(run_agency, "get_config_value", self._raw(raw))
        assert run_agency.resolve_step_timeout() == expected
