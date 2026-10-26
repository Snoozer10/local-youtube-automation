from __future__ import annotations

import sys
from typing import Any

import youtube_automation.video.compiler as compiler_mod
from youtube_automation.video.compiler import *  # noqa: F401, F403


class _FacadeProxy:
    def __init__(self, target: Any) -> None:
        self._target = target

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_target":
            super().__setattr__(name, value)
            return

        setattr(self._target, name, value)

        for mod_name in ["engine", "encoder", "ken_burns", "subtitles", "filter_graph"]:
            mod = sys.modules.get(f"youtube_automation.video.{mod_name}")
            if mod and (hasattr(mod, name) or name.startswith("_test_")):
                setattr(mod, name, value)

    def __delattr__(self, name: str) -> None:
        if name == "_target":
            super().__delattr__(name)
            return

        if hasattr(self._target, name):
            delattr(self._target, name)

        for mod_name in ["engine", "encoder", "ken_burns", "subtitles", "filter_graph"]:
            mod = sys.modules.get(f"youtube_automation.video.{mod_name}")
            if mod and hasattr(mod, name):
                delattr(mod, name)


sys.modules[__name__] = _FacadeProxy(compiler_mod)  # type: ignore[assignment]

if __name__ == "__main__":
    sys.exit(compiler_mod.main(sys.argv[1:]))
