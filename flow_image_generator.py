import os
import sys
import types

_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import youtube_automation.visuals.flow_generator as flow_mod  # noqa: E402
from youtube_automation.visuals.flow_generator import *  # noqa: E402, F401, F403


class _FacadeProxy(types.ModuleType):
    """Dynamic facade proxy ensuring 100% backward compatibility and bidirectional
    monkeypatching synchronization across youtube_automation.visuals and browser packages.
    """

    def __init__(self, target):
        super().__init__(target.__name__, getattr(target, "__doc__", None))
        self._target = target

    def __getattr__(self, name):
        return getattr(self._target, name)

    def __setattr__(self, name, value):
        if name == "_target":
            super().__setattr__(name, value)
            return

        super().__setattr__(name, value)
        setattr(self._target, name, value)

        # Bidirectional synchronization across decomposed visual and browser modules
        for mod_name in [
            "youtube_automation.visuals.asset_studio",
            "youtube_automation.visuals.image_extractor",
            "youtube_automation.visuals.text_gate",
            "youtube_automation.browser.cdp_client",
        ]:
            mod = sys.modules.get(mod_name)
            if mod and hasattr(mod, name):
                setattr(mod, name, value)

    def __dir__(self):
        return dir(self._target)


sys.modules[__name__] = _FacadeProxy(flow_mod)

if __name__ == "__main__":
    import runpy
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("youtube_automation.visuals.flow_generator", run_name="__main__")
