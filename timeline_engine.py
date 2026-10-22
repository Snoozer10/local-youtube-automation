import importlib
import sys
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from youtube_automation.timeline.engine import *  # noqa: F403


class _FacadeProxy(ModuleType):
    def __init__(self, target_module_name: str) -> None:
        self._target_module_name = target_module_name
        self._module: ModuleType | None = None

    def _get_module(self) -> ModuleType:
        if self._module is None:
            self._module = importlib.import_module(self._target_module_name)
        return self._module

    def __getattr__(self, name: str) -> Any:
        # Module exports are intentionally dynamic at this compatibility boundary.
        return getattr(self._get_module(), name)

    def __setattr__(self, name: str, value: object) -> None:
        if name in ("_target_module_name", "_module"):
            super().__setattr__(name, value)
        else:
            setattr(self._get_module(), name, value)

    def __dir__(self) -> list[str]:
        return dir(self._get_module())

sys.modules[__name__] = _FacadeProxy("youtube_automation.timeline.engine")

if __name__ == "__main__":
    import runpy
    runpy.run_module("youtube_automation.timeline.engine", run_name="__main__")
