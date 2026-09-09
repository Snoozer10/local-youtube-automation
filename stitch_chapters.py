import os
import sys
import types

_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import youtube_automation.audio.chapter_stitcher as stitcher_mod  # noqa: E402
from youtube_automation.audio.chapter_stitcher import *  # noqa: E402, F401, F403


class _FacadeProxy(types.ModuleType):
    """Dynamic facade proxy ensuring 100% backward compatibility and bidirectional
    monkeypatching synchronization across youtube_automation.audio.chapter_stitcher.
    """

    def __init__(self, target, sync_modules=None):
        super().__init__(target.__name__, getattr(target, "__doc__", None))
        self._target = target
        self._sync_modules = sync_modules or []

    def __getattr__(self, name):
        return getattr(self._target, name)

    def __setattr__(self, name, value):
        if name in ("_target", "_sync_modules"):
            super().__setattr__(name, value)
            return

        super().__setattr__(name, value)
        setattr(self._target, name, value)

        for mod_name in self._sync_modules:
            mod = sys.modules.get(mod_name)
            if mod and hasattr(mod, name):
                setattr(mod, name, value)

    def __delattr__(self, name):
        if name in ("_target", "_sync_modules"):
            super().__delattr__(name)
            return
        try:
            super().__delattr__(name)
        except AttributeError:
            pass
        if hasattr(self._target, name):
            delattr(self._target, name)

    def __dir__(self):
        return dir(self._target)


sys.modules[__name__] = _FacadeProxy(
    stitcher_mod,
    sync_modules=[
        "youtube_automation.audio",
        "youtube_automation.audio.chapter_stitcher",
    ],
)

if __name__ == "__main__":
    import runpy
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("youtube_automation.audio.chapter_stitcher", run_name="__main__")
