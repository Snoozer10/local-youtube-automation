"""Duck-typed Playwright CDP fakes for Gemini injection/readback testing.

No playwright import at module scope: these are pure-Python stand-ins shaped
after the subset of the Playwright API the pipeline touches (keyboard
insertion, locator inner_text readback, page lifecycle).

Readback-gate semantics mirrored from gemini_controller:
- keyboard.insert_text appends into the recorded buffer.
- A partial_insertion_ratio < 1.0 truncates each insertion, simulating a
  dropped tail so callers' >=95% readback gates must reject.
- unstable_reads drives the 3x-stability handshake: inner_text returns a
  DIFFERENT value N times, then freezes on the injected buffer.
- state_queue scripts generation lifecycle transitions (generating/done/error).
"""

from __future__ import annotations

from collections.abc import Callable


class MockKeyboard:
    def __init__(self, page: MockCDPPage) -> None:
        self._page = page

    def insert_text(self, text: str) -> None:
        ratio = self._page.partial_insertion_ratio
        stored = text[: max(0, int(len(text) * ratio))]
        self._page.injected_text += stored
        self._page.insertion_calls.append(stored)

    def press(self, key: str) -> None:
        self._page.pressed_keys.append(key)


class MockLocator:
    def __init__(self, page: MockCDPPage, selector: str) -> None:
        self._page = page
        self.selector = selector

    def inner_text(self) -> str:
        return self._page.read_buffer()

    def count(self) -> int:
        return 1


class MockCDPPage:
    def __init__(self, url: str = "https://gemini.example/app") -> None:
        self.url = url
        self.keyboard = MockKeyboard(self)
        self.injected_text: str = ""
        self.insertion_calls: list[str] = []
        self.pressed_keys: list[str] = []
        self.partial_insertion_ratio: float = 1.0
        self.unstable_reads_left: int = 0
        self.unstable_reads_served: int = 0
        self.unstable_value: str = "...thinking"
        self.is_generating: bool = False
        self.error_card_visible: bool = False
        self.state_queue: list[str] = []
        self.closed: bool = False
        self.on_close: Callable[[], None] | None = None

    def __enter__(self) -> MockCDPPage:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def locator(self, selector: str) -> MockLocator:
        return MockLocator(self, selector)

    def goto(self, url: str) -> None:
        self.url = url

    def read_buffer(self) -> str:
        if self.unstable_reads_left > 0:
            self.unstable_reads_left -= 1
            self.unstable_reads_served += 1
            return f"{self.unstable_value}{self.unstable_reads_served}"
        return self.injected_text

    def set_unstable_reads(self, count: int, value: str = "...thinking") -> None:
        self.unstable_reads_left = count
        self.unstable_reads_served = 0
        self.unstable_value = value

    def script_generation(self, *states: str) -> None:
        self.state_queue = list(states)

    def advance_generation_state(self) -> str:
        if not self.state_queue:
            return "idle"
        state = self.state_queue.pop(0)
        if state == "generating":
            self.is_generating = True
            self.error_card_visible = False
        elif state == "done":
            self.is_generating = False
        elif state == "error":
            self.error_card_visible = True
            self.is_generating = False
        return state

    def simulate_error_card(self) -> None:
        self.error_card_visible = True
        self.is_generating = False

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            if self.on_close is not None:
                self.on_close()


class MockCDPContext:
    def __init__(self, browser: MockCDPBrowser) -> None:
        self.browser = browser
        self.pages: list[MockCDPPage] = []

    def new_page(self, url: str = "https://gemini.example/app") -> MockCDPPage:
        page = MockCDPPage(url)
        page.on_close = lambda: self.pages.remove(page) if page in self.pages else None
        self.pages.append(page)
        return page

    @property
    def open_pages(self) -> list[MockCDPPage]:
        return [p for p in self.pages if not p.closed]


class MockCDPBrowser:
    def __init__(self) -> None:
        self.context = MockCDPContext(self)
        self.connected: bool = True

    def new_page(self, url: str = "https://gemini.example/app") -> MockCDPPage:
        return self.context.new_page(url)

    def close(self) -> None:
        self.connected = False


if __name__ == "__main__":
    browser = MockCDPBrowser()
    with browser.new_page() as page:
        page.partial_insertion_ratio = 0.6
        page.keyboard.insert_text("ABCDEFGHIJ")
        assert page.injected_text == "ABCDEF", page.injected_text
        assert page.locator("model-response").inner_text() == "ABCDEF"

        fresh = browser.new_page()
        fresh.keyboard.insert_text("كِدَه")
        fresh.set_unstable_reads(3, "~draft")
        reads = [fresh.locator("model-response").inner_text() for _ in range(5)]
        assert reads[:3] == ["~draft1", "~draft2", "~draft3"], reads
        assert reads[3:] == ["كِدَه", "كِدَه"], reads

        fresh.script_generation("generating", "generating", "done")
        fresh.advance_generation_state()
        assert fresh.is_generating and not fresh.error_card_visible
        assert fresh.advance_generation_state() == "generating"
        assert fresh.advance_generation_state() == "done" and not fresh.is_generating
        fresh.simulate_error_card()
        assert fresh.error_card_visible
    assert browser.context.open_pages == [fresh], "only unclosed page remains"
    print("mock_cdp_session self-test OK")
