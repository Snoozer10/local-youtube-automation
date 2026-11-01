"""Production stages must stop before dispatch when authority resolution fails."""

from pathlib import Path

import pytest

from youtube_automation.production import cli
from youtube_automation.production.authority import AuthorityError


@pytest.mark.unit
def test_polished_audio_adoption_preserves_authority_error_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = AuthorityError("Synthetic authority resolution failure")
    dispatched = []

    def unavailable_database() -> Path:
        raise failure

    monkeypatch.setattr(cli, "resource_database", unavailable_database)
    monkeypatch.setattr(cli, "_run_stage_attempt", lambda *args: dispatched.append(args))

    with pytest.raises(AuthorityError) as raised:
        cli.main(
            [
                "adopt-polished-audio",
                "--run-dir", str(tmp_path),
                "--polished-audio-file", str(tmp_path / "polished.wav"),
                "--polished-audio-sha256", "a" * 64,
                "--audio-acceptance-file", str(tmp_path / "acceptance.json"),
                "--audio-acceptance-sha256", "b" * 64,
            ]
        )

    assert raised.value is failure
    assert dispatched == []
