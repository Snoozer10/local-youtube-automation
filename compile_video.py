import sys

import youtube_automation.video.compiler as compiler_mod
from youtube_automation.video.compiler import *  # noqa: F401, F403


class _FacadeProxy:
    def __init__(self, target):
        self._target = target

    def __getattr__(self, name):
        return getattr(self._target, name)

    def __setattr__(self, name, value):
        if name == '_target':
            super().__setattr__(name, value)
            return

        setattr(self._target, name, value)

        for mod_name in ['encoder', 'ken_burns', 'subtitles', 'filter_graph']:
            mod = sys.modules.get(f"youtube_automation.video.{mod_name}")
            if mod and hasattr(mod, name):
                setattr(mod, name, value)

sys.modules[__name__] = _FacadeProxy(compiler_mod)

if __name__ == '__main__':
    compiler_mod.main(sys.argv[1:])
