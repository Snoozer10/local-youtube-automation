import sys
import importlib

class _FacadeProxy:
    def __init__(self, target_module_name):
        self._target_module_name = target_module_name
        self._module = None

    def _get_module(self):
        if self._module is None:
            self._module = importlib.import_module(self._target_module_name)
        return self._module

    def __getattr__(self, name):
        return getattr(self._get_module(), name)

    def __setattr__(self, name, value):
        if name in ("_target_module_name", "_module"):
            super().__setattr__(name, value)
        else:
            setattr(self._get_module(), name, value)

    def __dir__(self):
        return dir(self._get_module())

sys.modules[__name__] = _FacadeProxy("youtube_automation.nlp.json_sanitizer")

if __name__ == "__main__":
    import runpy
    runpy.run_module("youtube_automation.nlp.json_sanitizer", run_name="__main__")
