"""Fake Playwright page/locator doubles for testing Gemini stability polling."""


class FakeLocator:
    def __init__(self, count=0, text="", visible=False, evaluate_text=None):
        self._count = count
        self._text = text
        self._visible = visible
        self._evaluate_text = evaluate_text if evaluate_text is not None else text

    def count(self):
        return self._count

    @property
    def first(self):
        return self

    def is_visible(self):
        return self._visible

    def nth(self, idx):
        return self

    def evaluate(self, script, timeout=None):
        return self._evaluate_text


class FakePage:
    """Duck-typed stand-in for playwright.sync_api.Page.

    Args:
        response_locator: FakeLocator returned for the RESPONSE_SELECTOR query.
        error_visible: when True, error selectors report visible.
        generating: value returned by is_gemini_generating native JS probes.
    """

    def __init__(self, response_locator=None, error_visible=False, generating=False,
                 think_placeholder=False):
        self.response_locator = response_locator or FakeLocator()
        self.error_visible = error_visible
        self.generating = generating
        self.think_placeholder = think_placeholder
        self.locator_calls = []

    def locator(self, selector):
        self.locator_calls.append(selector)
        lowered = selector.lower()
        if "error" in lowered or "try again" in lowered or "went wrong" in lowered:
            return FakeLocator(count=1 if self.error_visible else 0,
                               visible=self.error_visible)
        if "model-response" in lowered or "response" in lowered:
            return self.response_locator
        # progress / thinking indicator probes
        return FakeLocator(count=1 if self.generating else 0, visible=self.generating)

    def evaluate(self, script, timeout=None):
        """Native JS probe used by is_gemini_generating reports the flag."""
        return bool(self.generating)

    def title(self):
        return "FakeTitle"

    @property
    def url(self):
        return "https://gemini.google.com/app/fake"


def stable_response_page(text="الرد النهائي الجاهز"):
    """Page whose last model-response node already carries a stable final text."""
    return FakePage(response_locator=FakeLocator(count=2, text=text))
