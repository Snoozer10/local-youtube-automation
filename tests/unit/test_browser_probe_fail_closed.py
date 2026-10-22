import io
import json

import pytest

from youtube_automation.audio import tts_generator
from youtube_automation.browser import ui_guard


@pytest.mark.parametrize("payload", [None, {}, [None], [{"type": "page", "url": 3}]])
def test_invalid_target_payload_fails_closed(payload):
    body = json.dumps(payload).encode("utf-8")

    with pytest.raises(ui_guard.TargetProbeError) as exc_info:
        ui_guard.foreign_debugger_targets(
            opener=lambda *_args, **_kwargs: io.BytesIO(body)
        )

    assert exc_info.value.code == "invalid_payload"


def test_adaptive_tts_probe_failure_stops_before_cdp_attach(monkeypatch):
    probe_error = ui_guard.TargetProbeError("probe_failed")
    monkeypatch.setattr(tts_generator.network_health, "require_healthy", lambda *_args: None)
    def failed_probe(*_args):
        raise probe_error

    monkeypatch.setattr(ui_guard, "foreign_debugger_targets", failed_probe)

    class Chromium:
        def connect_over_cdp(self, *_args, **_kwargs):
            pytest.fail("CDP attach must not run after a failed target probe")

    class Playwright:
        chromium = Chromium()

    with pytest.raises(ui_guard.TargetProbeError) as exc_info:
        tts_generator.connect_tts_browser(
            Playwright(), adaptive=True, browser_type="chrome", profile_index=0, port=9222
        )

    assert exc_info.value is probe_error
