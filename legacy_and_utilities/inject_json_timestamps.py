"""Deprecated compatibility tombstone for inject_json_timestamps.py."""

from __future__ import annotations

import importlib
import runpy
import sys
import warnings
from types import ModuleType
from typing import Any

warnings.warn(
    "legacy_and_utilities/inject_json_timestamps.py is deprecated and will be removed in a future release. "
    "Please use 'python fix_timestamps.py' or import 'youtube_automation.timeline.fix_timestamps'.",
    category=FutureWarning,
    stacklevel=2,
)


class _TombstoneProxy(ModuleType):
    def __init__(self, target_module_name: str) -> None:
        self._target_module_name = target_module_name
        self._module: ModuleType | None = None

    def _get_module(self) -> ModuleType:
        if self._module is None:
            self._module = importlib.import_module(self._target_module_name)
        return self._module

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_module(), name)

    def __setattr__(self, name: str, value: object) -> None:
        if name in ("_target_module_name", "_module"):
            super().__setattr__(name, value)
        else:
            setattr(self._get_module(), name, value)

    def __dir__(self) -> list[str]:
        return dir(self._get_module())


sys.modules[__name__] = _TombstoneProxy("youtube_automation.timeline.fix_timestamps")

if __name__ == "__main__":
    runpy.run_module("youtube_automation.timeline.fix_timestamps", run_name="__main__")
