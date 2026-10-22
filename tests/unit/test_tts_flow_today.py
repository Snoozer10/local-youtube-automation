"""Offline checks of the AI Studio TTS settings flow against today's speech UI (probed 2026-10-07).

The fake page models the live evidence in docs/sessions/CLAUDE_INTERIM_RESULT.md ("Live AI Studio
findings"): landing page -> "Create new dialog" -> placeholder editor -> hydrated editor with a
Text | Composer toggle, the run-settings panel (model card, voice settings, temperature) and a
voice dialog. The fake is strict: any selector it does not model fails the test.
"""

import contextlib
from types import SimpleNamespace

import pytest

from youtube_automation.audio import tts_generator

MODEL = "gemini-2.5-pro-preview-tts"
SPEECH_URL = f"https://aistudio.google.com/generate-speech?model={MODEL}"
GATE_ERROR = tts_generator.TTSWorkspaceUnavailableError

# Selectors exactly as observed live (probe/voice_v4_report.json, text_mode_report.json,
# rehearsal_report.json).
CREATE = "[data-testid='create-new-dialog-card']"
TEXT = "button[role='radio'][data-value='TEXT']"
PROMPT = "textarea[aria-label='Enter a prompt']"
PANEL = "ms-run-settings"
PANEL_TOGGLE = "button[aria-label='Toggle run settings panel']"
PANEL_CLOSE = "button[aria-label='Close run settings panel']"
CARD = "ms-run-settings button.model-selector-card [data-test-id='model-name']"
VOICE_NAME = "ms-voice-settings .voice-display-name"
VOICE_OPEN = "ms-voice-settings button[aria-label='Open voice settings']"
VOICE_CLOSE = "mat-dialog-container button[aria-label='Close panel']"
EXPANDER = "ms-run-settings button[aria-label='Expand or collapse Model settings']"
TEMPERATURE = "ms-run-settings input.slider-number-input"
SWITCH = ":is(mat-dialog-container, [role='dialog']):has-text('Switch model')"
SWITCH_CANCEL = f"{SWITCH} button:has-text('Cancel')"
RUN = "button[type='submit'], button:has-text('Run')"
MARKERS = (
    "text='Turn text into natural-sounding speech...'",
    PROMPT,
    PANEL,
    "ms-run-settings .active-voice-card",
    "ms-run-settings .voice-card",
    "ms-run-settings [aria-label*='Speaker' i]",
    "ms-run-settings :text('Speaker 1')",
)
# rehearsal_report.json clicks[2]: the real temperature input.
TEMPERATURE_ATTRS = {
    "ms-input": "",
    "type": "text",
    "inputmode": "decimal",
    "role": "spinbutton",
    "class": "slider-number-input small",
    "aria-valuemin": "0",
    "aria-valuemax": "2",
}

ALL_VOICES = ("Zephyr", "Achird", "Charon")


def voice_card(voice):
    return f"mat-dialog-container div.voice-card[data-voice-name='{voice}']"


def option(voice):
    return f"{voice_card(voice)} button.voice-card-content"


def play(voice):
    return f"{voice_card(voice)} button[aria-label='Play voice sample']"


def selected(voice):
    return f"mat-dialog-container div.voice-card.selected[data-voice-name='{voice}']"


class _Sent(BaseException):
    """Stops the run right after the first Run click so the test can count one real send."""


class FakeElement:
    def __init__(self, page, selector, text="", attrs=None, visible=True):
        self.page = page
        self.selector = selector
        self.text = text
        self.attrs = dict(attrs or {})
        self.visible = visible

    def is_visible(self):
        return self.visible

    def inner_text(self, **_kwargs):
        return self.text

    def get_attribute(self, name, **_kwargs):
        if self.selector == TEMPERATURE and name == "aria-valuenow":
            return self.page.aria_valuenow
        return self.attrs.get(name)

    def click(self, *_args, **_kwargs):
        self.page.on_click(self)

    def fill(self, value, **_kwargs):
        self.page.temperature = value

    def blur(self, **_kwargs):
        if self.page.temperature_commits:
            self.page.aria_valuenow = self.page.temperature

    def input_value(self, **_kwargs):
        if self.selector != TEMPERATURE:
            return getattr(self.page, "typed_text", "")  # the speech prompt read-back
        return self.page.temperature_readback or self.page.temperature

    def is_enabled(self, **_kwargs):
        return True

    def scroll_into_view_if_needed(self):
        return None

    def bounding_box(self):
        return {"x": 0, "y": 0, "width": 10, "height": 10}


class _Absent(FakeElement):
    def is_visible(self):
        return False

    def click(self, *_args, **_kwargs):
        raise TimeoutError(f"{self.selector} is not on the page")


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    def all(self):
        return self.page.elements(self.selector)

    @property
    def first(self):
        found = self.all()
        return found[0] if found else _Absent(self.page, self.selector)

    def is_visible(self):
        return self.first.is_visible()

    def count(self):
        return len(self.all())

    def nth(self, index):
        return self.all()[index]

    def all_text_contents(self):
        return self.page.texts(self.selector)


class Recorder:
    def __init__(self):
        self.presses = []
        self.downs = 0

    def press(self, key):
        self.presses.append(key)

    def type(self, text):
        self.presses.append(f"type:{text}")

    def move(self, *_args):
        return None

    def down(self):
        self.downs += 1

    def up(self):
        return None


class StudioPage:
    """Today's generate-speech page: landing -> placeholder (~3 s) -> hydrated editor."""

    instances = []

    def __init__(self, **overrides):
        self.url = SPEECH_URL
        self.stage = "landing"
        self.mode = "composer"
        self.panel_open = True
        self.dialog = None
        self.voice = "Zephyr"
        self.picked = None
        self.model_names = [MODEL]
        self.expanded = False
        self.temperature = "1"
        self.aria_valuenow = "1"
        self.temperature_readback = None
        self.temperature_commits = True
        self.temperature_inputs = 1
        self.text_toggles = 1
        self.prompt_visibility = [True]
        self.text_label = "edit_note\nText"  # Angular may drop the space between the spans
        self.voices = set(ALL_VOICES)
        self.voice_sticks = True
        self.display_updates = True
        self.card_after = None  # polls before the landing card renders; None = at once
        self.create_works = True
        self.relands = 0  # times a later navigation resets the editor back to landing
        self.reland_after = 2  # polls after a Create click before that reset
        self.hydrate_after = 12  # polls; None = never
        self.close_panel_on_hydrate = False
        self.panel_toggle_present = True
        self.temperature_present = True
        self.switch_on_click = None
        self.switch_delay = 0  # polls before the "Switch model?" dialog shows
        self.switch_cancel_present = True
        self.sleeps = 0
        self.stage_since = 0
        self.switch_at = None
        self.clicks = []
        self.cancel_clicks = 0
        self.gotos = []
        self.reloads = 0
        self.unknown = []
        self.keyboard = Recorder()
        self.mouse = Recorder()
        for key, value in overrides.items():
            assert hasattr(self, key), key
            setattr(self, key, value)
        if self.card_after is not None and self.stage == "landing":
            self.stage = "loading"
        StudioPage.instances.append(self)

    # -- time ---------------------------------------------------------------------------
    def wait_for_timeout(self, milliseconds):
        self.tick(milliseconds / 1000)

    def tick(self, *_args):
        self.sleeps += 1
        if self.sleeps > 2000:
            raise RuntimeError("unbounded wait")
        waited = self.sleeps - self.stage_since
        if self.stage == "loading" and waited >= self.card_after:
            self._enter("landing")
        elif self.stage == "placeholder" and self.relands and waited >= self.reland_after:
            self.relands -= 1
            self._enter("landing")
        elif (
            self.stage == "placeholder"
            and self.hydrate_after is not None
            and waited >= self.hydrate_after
        ):
            self._enter("editor")
            if self.close_panel_on_hydrate:
                self.panel_open = False
        if self.switch_at is not None and self.sleeps >= self.switch_at:
            self.switch_at = None
            self.dialog = "switch"

    def _enter(self, stage):
        self.stage = stage
        self.stage_since = self.sleeps

    # -- DOM ----------------------------------------------------------------------------
    def _unknown(self, selector):
        self.unknown.append(selector)
        raise AssertionError(f"fake page does not model selector {selector!r}")

    def elements(self, selector):
        editor = self.stage == "editor"
        panel = self.panel_open and self.stage in ("landing", "placeholder", "editor")

        def el(text="", attrs=None, count=1):
            return [FakeElement(self, selector, text, attrs) for _ in range(count)]

        if selector in (CARD, VOICE_NAME):
            return [FakeElement(self, selector, text) for text in self.texts(selector)]

        if selector == CREATE:
            return el("add Create new dialog") if self.stage == "landing" else []
        if selector == TEXT:
            on = self.stage in ("placeholder", "editor")
            return (
                el(self.text_label, {"role": "radio", "data-value": "TEXT"}, self.text_toggles)
                if on
                else []
            )
        if selector == PROMPT:
            if not editor or self.mode != "text":
                return []
            return [
                FakeElement(self, selector, visible=visible)
                for visible in self.prompt_visibility
            ]
        if selector == PANEL or selector == "ms-run-settings .active-voice-card":
            return el() if panel else []
        if selector in MARKERS:
            return []
        if selector == PANEL_TOGGLE:
            return el("tune") if editor and not panel and self.panel_toggle_present else []
        if selector == PANEL_CLOSE:
            return el("close") if editor and panel else []
        if selector in (VOICE_OPEN, EXPANDER):
            return el() if editor and panel else []
        if selector == TEMPERATURE:
            visible = editor and panel and self.expanded and self.temperature_present
            attrs = dict(TEMPERATURE_ATTRS)
            return el(self.temperature, attrs, self.temperature_inputs) if visible else []
        if selector == VOICE_CLOSE:
            return el("close") if self.dialog == "voice" else []
        if selector == SWITCH:
            return el("Switch model? Cancel Continue") if self.dialog == "switch" else []
        if selector == SWITCH_CANCEL:
            on = self.dialog == "switch" and self.switch_cancel_present
            return el("Cancel") if on else []
        for voice in ALL_VOICES:
            in_dialog = self.dialog == "voice" and voice in self.voices
            if selector in (option(voice), play(voice)):
                return el(voice if selector == option(voice) else "play_arrow") if in_dialog else []
            if selector == f"{voice_card(voice)} button":
                return (
                    [FakeElement(self, option(voice), voice), FakeElement(self, play(voice))]
                    if in_dialog
                    else []
                )
            if selector == selected(voice):
                return el() if in_dialog and self.picked == voice else []
        if selector == RUN:
            return el("Run")
        if selector == "body":
            return el()
        return self._unknown(selector)

    def texts(self, selector):
        panel = self.panel_open and self.stage in ("landing", "editor")
        if selector == CARD:
            return list(self.model_names) if panel else []
        if selector == VOICE_NAME:
            return [f" {self.voice} "] if panel and self.stage == "editor" else []
        return self._unknown(selector)

    def locator(self, selector):
        return FakeLocator(self, selector)

    def on_click(self, element):
        selector = element.selector
        if selector == RUN:
            self.clicks_before_run = len(self.clicks)
            handler = getattr(self, "run_click_handler", None)
            if handler is not None:
                handler(self, element)
            return
        self.clicks.append(selector)
        if self.switch_on_click == selector:
            if not self.switch_delay:
                self.dialog = "switch"
                return
            self.switch_at = self.sleeps + self.switch_delay  # the click also takes effect
        if selector == CREATE:
            if self.create_works:
                self._enter("placeholder")
        elif selector == TEXT and self.stage == "editor" and element.text == self.text_label:
            self.mode = "text"
        elif selector == PANEL_TOGGLE:
            self.panel_open = True
        elif selector == PANEL_CLOSE:
            self.panel_open = False
        elif selector == VOICE_OPEN:
            self.dialog = "voice"
        elif selector == VOICE_CLOSE:
            self.dialog = None
            if self.picked and self.display_updates:
                self.voice = self.picked
        elif selector == SWITCH_CANCEL:
            self.cancel_clicks += 1
            self.dialog = None
        elif selector == EXPANDER:
            self.expanded = not self.expanded
        else:
            for voice in self.voices:
                if selector == option(voice) and self.voice_sticks:
                    self.picked = voice

    # -- page API used by the pipeline -------------------------------------------------
    def goto(self, url, **_kwargs):
        self.gotos.append(url)
        self.url = url

    def bring_to_front(self):
        return None

    def reload(self, **_kwargs):
        """Today's reload drops the editor: back to landing, Composer, default voice."""
        self.reloads += 1
        self._enter("landing")
        self.mode = "composer"
        self.dialog = None
        self.voice = "Zephyr"
        self.picked = None
        self.expanded = False
        self.panel_open = True

    def on(self, *_args):
        return None

    def add_init_script(self, *_args):
        return None

    def close(self):
        return None

    def wait_for_selector(self, selector, **_kwargs):
        raise TimeoutError(f"{selector} never appeared")


OPTIONS = {"model": MODEL, "temperature": "1.1", "voice": "Achird"}
HAPPY_CLICKS = [CREATE, TEXT, VOICE_OPEN, option("Achird"), VOICE_CLOSE, EXPANDER]


@pytest.fixture(autouse=True)
def strict_fake_pages():
    """Every selector the code asks for must be modelled (errors inside helpers are swallowed)."""
    StudioPage.instances = []
    yield
    for page in StudioPage.instances:
        assert page.unknown == [], f"unmodelled selectors: {page.unknown}"


@pytest.fixture
def studio(monkeypatch):
    def make(**overrides):
        page = StudioPage(**overrides)
        monkeypatch.setattr(tts_generator.time, "sleep", page.tick)
        monkeypatch.setattr(
            tts_generator, "human_click", lambda *_a: pytest.fail("coordinate click in settings")
        )
        return page

    return make


def model_card_clicks(page):
    return [s for s in page.clicks if "model-selector-card" in s or "model-name" in s]


def test_landing_to_text_mode_sets_and_verifies_the_voice(studio):
    page = studio()
    tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.stage == "editor"
    assert page.mode == "text"
    assert page.voice == "Achird"
    assert page.panel_open is True
    assert page.dialog is None
    assert page.clicks == HAPPY_CLICKS  # full list: no close-panel, no Play sample, no extras
    assert PANEL_CLOSE not in page.clicks
    assert play("Achird") not in page.clicks
    assert page.keyboard.presses == []
    assert page.mouse.downs == 0
    assert model_card_clicks(page) == []
    tts_generator._require_active_tts_model(page, MODEL)


def test_editor_already_in_text_mode_with_voice_set_needs_no_settings_clicks(studio):
    page = studio(stage="editor", mode="text", voice="Achird", expanded=True, temperature="1.1")
    tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.clicks == []  # the visible temperature input means: never touch the expander
    assert page.expanded is True
    assert page.keyboard.presses == []


def test_hydration_timeout_raises_and_is_bounded(studio):
    page = studio(hydrate_after=None)
    with pytest.raises(GATE_ERROR, match="did not finish loading"):
        tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.clicks == [CREATE]
    limit = int(tts_generator._TTS_UI_WAIT_SEC / tts_generator._TTS_UI_POLL_SEC)
    assert page.sleeps <= limit
    assert page.keyboard.presses == []


def test_placeholder_editor_is_not_mistaken_for_the_hydrated_editor(studio):
    page = studio(hydrate_after=12)
    tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.sleeps >= 12  # waited for the real model card, not just for the toggle
    assert page.clicks == HAPPY_CLICKS


def test_card_that_renders_late_is_clicked_inside_the_poll(studio):
    page = studio(card_after=6)
    tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.sleeps >= 6
    assert page.clicks == HAPPY_CLICKS
    assert page.voice == "Achird"


def test_card_reappearing_once_after_a_late_navigation_is_clicked_again(studio):
    page = studio(relands=1)
    tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.clicks == [CREATE] + HAPPY_CLICKS
    assert page.mode == "text"
    assert page.voice == "Achird"


def test_card_that_keeps_reappearing_fails_closed_after_two_clicks(studio):
    page = studio(relands=5)
    with pytest.raises(GATE_ERROR, match="Create new dialog"):
        tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.clicks == [CREATE, CREATE]
    assert page.keyboard.presses == []


def test_card_that_never_goes_away_is_clicked_only_once(studio):
    page = studio(create_works=False)
    with pytest.raises(GATE_ERROR, match="did not finish loading"):
        tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.clicks == [CREATE]


@pytest.mark.parametrize(
    "overrides",
    [{"text_toggles": 0}, {"text_toggles": 2}, {"text_label": "dashboard Composer"}],
    ids=["no-toggle", "two-toggles", "label-not-text"],
)
def test_text_toggle_must_match_exactly_once(studio, overrides):
    page = studio(**overrides)
    with pytest.raises(GATE_ERROR):
        tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert TEXT not in page.clicks
    assert page.mode == "composer"
    assert page.keyboard.presses == []


def test_text_mode_rejects_two_visible_prompts_before_any_send(studio):
    page = studio(stage="editor", mode="text", prompt_visibility=[True, True])
    with pytest.raises(GATE_ERROR, match="exactly one visible"):
        tts_generator._select_tts_text_mode(page)
    assert page.clicks == []


def test_text_toggle_is_required_even_after_hydration(studio):
    page = studio(stage="editor", text_toggles=2)
    with pytest.raises(GATE_ERROR):
        tts_generator._select_tts_text_mode(page)
    assert page.clicks == []


@pytest.mark.parametrize(
    "overrides",
    [{"voice_sticks": False}, {"voices": {"Zephyr", "Charon"}}, {"display_updates": False}],
    ids=["selection-does-not-stick", "voice-not-offered", "display-name-stays-old"],
)
def test_unverified_voice_fails_closed(studio, overrides):
    page = studio(**overrides)
    with pytest.raises(GATE_ERROR, match="Achird"):
        tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.voice == "Zephyr"
    assert play("Achird") not in page.clicks
    assert page.keyboard.presses == []


@pytest.mark.parametrize("voice", ["", "Achird']", "Ach ird", None])
def test_voice_name_must_be_a_plain_name(studio, voice):
    page = studio(stage="editor", mode="text")
    with pytest.raises(GATE_ERROR, match="plain name"):
        tts_generator._select_tts_voice(page, voice)
    assert page.clicks == []


@pytest.mark.parametrize("names", [["gemini-3.8-flash"], [MODEL, MODEL]])
def test_wrong_model_card_raises_before_voice_or_typing(studio, names):
    page = studio(model_names=names)
    with pytest.raises(GATE_ERROR, match="model card names"):
        tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert VOICE_OPEN not in page.clicks
    assert model_card_clicks(page) == []


def test_missing_model_card_never_counts_as_hydrated(studio):
    page = studio(model_names=[])
    with pytest.raises(GATE_ERROR):
        tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert TEXT not in page.clicks


@pytest.mark.parametrize("trigger", [TEXT, VOICE_OPEN, option("Achird"), EXPANDER])
def test_switch_model_dialog_is_cancelled_and_fails_closed(studio, trigger):
    page = studio(switch_on_click=trigger)
    with pytest.raises(GATE_ERROR, match="Switch model"):
        tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.cancel_clicks == 1
    assert page.clicks[-1] == SWITCH_CANCEL
    assert page.keyboard.presses == []  # never Enter (or any key) on the dialog


def test_late_switch_model_dialog_after_the_expander_stops_before_the_temperature(studio):
    page = studio(switch_on_click=EXPANDER, switch_delay=2)
    with pytest.raises(GATE_ERROR, match="Switch model"):
        tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.clicks[-2:] == [EXPANDER, SWITCH_CANCEL]
    assert page.temperature == "1"  # nothing was filled while the dialog was up
    assert page.keyboard.presses == []


def test_switch_model_dialog_without_cancel_still_fails_closed(studio):
    page = studio(switch_on_click=VOICE_OPEN, switch_cancel_present=False)
    with pytest.raises(GATE_ERROR, match="Switch model"):
        tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.cancel_clicks == 0
    assert page.clicks == [CREATE, TEXT, VOICE_OPEN]
    assert page.keyboard.presses == []


def test_closed_run_settings_panel_is_reopened_for_the_model_gate(studio):
    page = studio(close_panel_on_hydrate=True)
    tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.clicks == [CREATE, TEXT, PANEL_TOGGLE] + HAPPY_CLICKS[2:]
    assert page.panel_open is True
    tts_generator._require_active_tts_model(page, MODEL)


def test_closed_panel_without_its_toggle_fails_closed(studio):
    page = studio(close_panel_on_hydrate=True, panel_toggle_present=False)
    with pytest.raises(GATE_ERROR):
        tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert PANEL_TOGGLE not in page.clicks
    assert page.keyboard.presses == []


def test_temperature_is_filled_and_verified_on_the_real_spinbutton_markup(studio, capsys):
    page = studio()
    tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    assert page.temperature == "1.1"
    assert page.aria_valuenow == "1.1"
    assert page.clicks.count(EXPANDER) == 1
    assert page.expanded is True
    assert "Successfully set Temperature to: 1.1" in capsys.readouterr().out
    assert page.keyboard.presses == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"temperature_present": False},
        {"temperature_inputs": 2},
        {"temperature_readback": "1"},
        {"temperature_commits": False},
    ],
    ids=["input-missing", "two-inputs", "readback-mismatch", "aria-valuenow-not-committed"],
)
def test_unverified_temperature_logs_and_continues(studio, capsys, overrides):
    page = studio(**overrides)
    tts_generator.reapply_speech_settings(page, dict(OPTIONS))
    out = capsys.readouterr().out
    assert "Warning" in out
    assert "Successfully set Temperature" not in out
    assert page.voice == "Achird"
    assert page.clicks == HAPPY_CLICKS
    assert page.keyboard.presses == []


def test_select_ai_studio_tts_model_is_not_used_by_the_flow(studio, monkeypatch):
    page = studio()
    monkeypatch.setattr(
        tts_generator, "select_ai_studio_tts_model", lambda *_a: pytest.fail("model picker used")
    )
    tts_generator.reapply_speech_settings(page, dict(OPTIONS))


class Harness:
    """Drives the real _run_voice_generation and the real reapply_speech_settings."""

    def __init__(self, monkeypatch, tmp_path, page, *, adaptive, config=None):
        self.page = page
        self.typed = []
        self.run_clicks = 0
        config = dict(config or {})
        (tmp_path / "refined_script.txt").write_text("مرحبا بالعالم", encoding="utf-8")
        voice = dict(OPTIONS)
        manifest = {
            "voice_config": dict(voice),
            "gemini_completed": True,
            "chapters": [
                {
                    "chapter_num": 1,
                    "text": "مرحبا بالعالم",
                    "audio_file": str(tmp_path / "voice_chapters" / "Chapter_1.wav"),
                    "status": "PENDING",
                }
            ],
        }
        if adaptive:
            from youtube_automation.production import contracts, narration, writing

            (tmp_path / "episode_brief.json").write_text("{}", encoding="utf-8")
            brief = SimpleNamespace(channel=SimpleNamespace(voice="Achird"))
            # This harness drives the Pro path; Flash coverage is in test_tts_flash_adapter.py.
            monkeypatch.setenv("ADAPTIVE_TTS_MODEL", MODEL)
            monkeypatch.setattr(writing, "verify_written_episode", lambda _run: None)
            monkeypatch.setattr(contracts, "load_brief", lambda _run: brief)
            monkeypatch.setattr(narration, "require_unpolished_run", lambda _run: None)
            monkeypatch.setattr(narration, "prepare_manifest", lambda _r, m, _b, _t: m)
        context = SimpleNamespace(
            pages=[page],
            new_page=lambda: page,
            grant_permissions=lambda *_a: None,
            add_init_script=lambda *_a: None,
        )
        browser = SimpleNamespace(contexts=[context])
        tts = tts_generator
        monkeypatch.setattr(tts.sys, "argv", ["generate_voice.py", str(tmp_path)])
        monkeypatch.setattr(tts.time, "sleep", page.tick)
        monkeypatch.setattr(tts, "read_voice_options", lambda: dict(voice))
        monkeypatch.setattr(tts, "load_or_create_manifest", lambda *_a: manifest)
        monkeypatch.setattr(tts, "save_manifest", lambda *_a: None)
        monkeypatch.setattr(tts, "sync_audio_manifest", lambda *_a, **_k: {})
        monkeypatch.setattr(tts, "calculate_script_coverage", lambda *_a: 1.0)
        monkeypatch.setattr(tts.loader, "render", lambda *_a, **_k: "")
        monkeypatch.setattr(
            tts, "get_config_value", lambda key, default=None: config.get(key, default)
        )
        monkeypatch.setattr(
            tts,
            "get_runtime_state",
            lambda key, default=None: "false" if key == "SWITCH_ACCOUNTS_ENABLED" else default,
        )
        monkeypatch.setattr(tts, "rotate_profile_index", lambda: pytest.fail("no rotation"))
        monkeypatch.setattr(tts, "kill_cdp_chrome", lambda *_a: pytest.fail("no kill"))
        monkeypatch.setattr(tts, "sync_playwright", lambda: contextlib.nullcontext(object()))
        monkeypatch.setattr(tts, "connect_tts_browser", lambda *_a, **_k: browser)
        monkeypatch.setattr(tts, "check_ai_studio_errors", lambda _p: (False, ""))
        monkeypatch.setattr(tts, "human_click", lambda *_a: pytest.fail("coordinate click"))
        monkeypatch.setattr(tts, "humanize_text_input", self._type)
        if adaptive:
            page.run_click_handler = self._click
            monkeypatch.setattr(
                tts,
                "human_hover_and_click",
                lambda _page, locator: self._click(_page, locator)
                if "Download" in getattr(locator, "selector", "")
                else pytest.fail("adaptive Run must use the semantic locator"),
            )
        else:
            monkeypatch.setattr(tts, "human_hover_and_click", self._click)

    def _type(self, page, textbox, _text):
        self.typed.append(
            {
                "box": textbox.selector,
                "voice": page.voice,
                "panel_open": page.panel_open,
                "mode": page.mode,
                "clicks_before": len(page.clicks),
            }
        )
        page.typed_text = _text
        return True

    def _click(self, page, locator):
        self.run_clicks += 1
        self.clicks_at_run = getattr(page, "clicks_before_run", len(page.clicks))
        raise _Sent("first Run click")

    def run(self):
        return tts_generator._run_voice_generation()


def assert_typed_once_after_today_flow(harness):
    assert harness.typed == [
        {
            "box": PROMPT,
            "voice": "Achird",
            "panel_open": True,
            "mode": "text",
            "clicks_before": harness.typed[0]["clicks_before"],
        }
    ]
    assert harness.run_clicks == 1
    assert harness.clicks_at_run == harness.typed[0]["clicks_before"]  # nothing between


@pytest.mark.parametrize("adaptive", [True, False])
@pytest.mark.parametrize(
    "prompt_visibility",
    [[True], [False, True]],
    ids=["single-visible", "hidden-match"],
)
def test_pipeline_types_and_runs_once_after_today_flow(
    monkeypatch, tmp_path, adaptive, prompt_visibility
):
    page = StudioPage(prompt_visibility=prompt_visibility)
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    with pytest.raises(_Sent):
        harness.run()
    assert_typed_once_after_today_flow(harness)
    assert page.clicks == HAPPY_CLICKS
    assert "body" not in page.clicks
    assert page.keyboard.presses == []
    assert page.mouse.downs == 0
    assert model_card_clicks(page) == []
    assert page.gotos == []


def test_pipeline_waits_for_entry_before_strict_gate_and_settings(monkeypatch, tmp_path):
    page = StudioPage(card_after=3)
    harness = Harness(monkeypatch, tmp_path, page, adaptive=True)
    events = []
    original_wait = tts_generator._wait_for_speech_workspace_ready
    original_gate = tts_generator._require_speech_workspace
    original_settings = tts_generator.reapply_speech_settings
    def wait(page, model):
        events.append('entry_start')
        before = page.sleeps
        original_wait(page, model)
        assert page.sleeps > before
        events.append('entry_ready')
    def gate(*args):
        events.append('strict_gate')
        return original_gate(*args)
    def settings(*args):
        events.append('settings')
        return original_settings(*args)
    monkeypatch.setattr(tts_generator, '_wait_for_speech_workspace_ready', wait)
    monkeypatch.setattr(tts_generator, '_require_speech_workspace', gate)
    monkeypatch.setattr(tts_generator, 'reapply_speech_settings', settings)
    with pytest.raises(_Sent):
        harness.run()
    assert events[:4] == ['entry_start', 'entry_ready', 'strict_gate', 'settings']
    assert_typed_once_after_today_flow(harness)


def test_pipeline_entry_timeout_never_calls_settings_types_or_runs(monkeypatch, tmp_path):
    page = StudioPage(card_after=999)
    harness = Harness(monkeypatch, tmp_path, page, adaptive=True)
    monkeypatch.setattr(tts_generator, 'reapply_speech_settings', lambda *_: pytest.fail('settings before entry readiness'))
    with pytest.raises(GATE_ERROR, match='within 20 seconds'):
        harness.run()
    assert page.sleeps == 80
    assert page.clicks == []
    assert harness.typed == []
    assert harness.run_clicks == 0


@pytest.mark.parametrize("adaptive", [True, False])
def test_pipeline_reload_back_to_landing_reapplies_the_whole_flow(monkeypatch, tmp_path, adaptive):
    page = StudioPage()
    config = {"TTS_PROACTIVE_RELOAD_INTERVAL": "0"}  # reload before the first chapter
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive, config=config)
    with pytest.raises(_Sent):
        harness.run()
    assert page.reloads == 1
    assert page.clicks == HAPPY_CLICKS + HAPPY_CLICKS
    assert_typed_once_after_today_flow(harness)
    assert page.keyboard.presses == []
    assert model_card_clicks(page) == []


@pytest.mark.parametrize("adaptive", [True, False])
def test_pipeline_rechecks_prompt_before_fill(monkeypatch, tmp_path, adaptive):
    page = StudioPage()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    original_guard = tts_generator._require_current_tts_settings
    guard_calls = 0

    def make_prompt_ambiguous_at_fill(page, model, voice):
        nonlocal guard_calls
        guard_calls += 1
        original_guard(page, model, voice)
        if guard_calls == 2:
            page.prompt_visibility = [True, True]

    monkeypatch.setattr(tts_generator, "_require_current_tts_settings", make_prompt_ambiguous_at_fill)
    with pytest.raises(GATE_ERROR, match="exactly one visible"):
        harness.run()
    assert guard_calls == 2
    assert harness.typed == []
    assert harness.run_clicks == 0


@pytest.mark.parametrize("adaptive", [True, False])
def test_pipeline_rechecks_prompt_before_run(monkeypatch, tmp_path, adaptive):
    page = StudioPage()
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    original_type = tts_generator.humanize_text_input

    def type_then_make_prompt_ambiguous(page, textbox, text):
        result = original_type(page, textbox, text)
        page.prompt_visibility = [True, True]
        return result

    monkeypatch.setattr(tts_generator, "humanize_text_input", type_then_make_prompt_ambiguous)
    with pytest.raises(GATE_ERROR, match="exactly one visible"):
        harness.run()
    assert len(harness.typed) == 1
    assert harness.run_clicks == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"voice_sticks": False},
        {"display_updates": False},
        {"model_names": ["gemini-3.8-flash"]},
        {"switch_on_click": TEXT},
        {"switch_on_click": TEXT, "switch_cancel_present": False},
        {"hydrate_after": None},
        {"relands": 5},
        {"text_toggles": 2},
    ],
    ids=[
        "voice-unverified",
        "display-name-stays-old",
        "wrong-model",
        "switch-model",
        "switch-model-no-cancel",
        "no-hydration",
        "card-keeps-reappearing",
        "two-text-toggles",
    ],
)
@pytest.mark.parametrize("adaptive", [True, False])
def test_pipeline_settings_failure_never_types_or_runs(monkeypatch, tmp_path, adaptive, overrides):
    page = StudioPage(**overrides)
    harness = Harness(monkeypatch, tmp_path, page, adaptive=adaptive)
    with pytest.raises(GATE_ERROR):
        harness.run()
    assert harness.typed == []
    assert harness.run_clicks == 0
    assert page.keyboard.presses == []
    assert PANEL_CLOSE not in page.clicks
    if overrides.get("switch_on_click"):
        assert page.cancel_clicks == (0 if "switch_cancel_present" in overrides else 1)
