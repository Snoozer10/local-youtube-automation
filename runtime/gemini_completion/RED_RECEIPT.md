# Gemini completion regression baseline

- Command: `venv/Scripts/python.exe -m pytest -q --tb=short -x tests/unit/test_gemini_utils.py::test_response_never_completes_when_stop_probe_state_is_unknown`
- Result: failed as expected before the production fix; stable text was returned despite the Stop-control evaluate raising `RuntimeError("CDP target detached")`.
- Production source SHA-256 before fix: `fc7cf6779a72762de39deea8a281ed3b6d38762e0e01ec1d83d58ba513defc04`.
- Test source SHA-256 with regression added: `cbbcc1ee8baf7d6b336c3fe1fb86d5a53b37920c0e61d478d366aa4eb3141d3b`.
- Failure occurred at the regression assertion `assert result == ""`; observed result was `Stable response text that must remain untrusted.`
- No browser or provider was used.
