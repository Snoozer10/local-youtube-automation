"""Query faults must stop before a settings click, typing, or Run."""
from types import SimpleNamespace

import pytest

from youtube_automation.audio import tts_generator as tg


class Match:
    def __init__(self, failure, clicks):
        self.failure, self.clicks = failure, clicks

    def is_visible(self):
        if self.failure == 'visibility':
            raise RuntimeError('visibility unavailable')
        return True

    def click(self, **kwargs):
        if self.failure == 'click':
            raise RuntimeError('cancel click unavailable')
        self.clicks.append('Cancel')

class Locator:
    def __init__(self, failure, count, clicks):
        self.failure, self.length, self.clicks = failure, count, clicks

    def count(self):
        if self.failure == 'count':
            raise RuntimeError('query unavailable')
        return self.length

    def nth(self, index):
        if self.failure == 'nth':
            raise RuntimeError('match unavailable')
        return Match(self.failure, self.clicks)

class SwitchGuardPage:
    url = 'https://aistudio.google.com/generate-speech?model=gemini-2.5-pro-preview-tts'
    def __init__(self, target, failure, cancel_count=1, dialogs=1):
        self.target, self.failure = target, failure
        self.cancel_count, self.dialogs = cancel_count, dialogs
        self.clicks, self.typed, self.runs = [], 0, 0

    def locator(self, selector):
        is_cancel = selector == tg._TTS_SWITCH_MODEL_CANCEL_SELECTOR
        target = 'cancel' if is_cancel else 'dialog'
        failure = self.failure if target == self.target else None
        if failure == 'parse':
            raise RuntimeError('selector unavailable')
        return Locator(failure, self.cancel_count if is_cancel else self.dialogs, self.clicks)

@pytest.mark.parametrize('target', ['dialog', 'cancel'])
@pytest.mark.parametrize('failure', ['parse', 'count', 'nth', 'visibility'])
def test_switch_query_fault_fails_closed_before_any_send(target, failure, monkeypatch):
    page = SwitchGuardPage(target, failure)
    monkeypatch.setattr(tg, 'humanize_text_input', lambda *_a: setattr(page, 'typed', 1))
    monkeypatch.setattr(tg, 'human_hover_and_click', lambda *_a: setattr(page, 'runs', 1))
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match='Cannot verify speech safety selector'):
        tg.reapply_speech_settings(page, {'model':'gemini-2.5-pro-preview-tts'})
    assert page.clicks == []
    assert page.typed == page.runs == 0

@pytest.mark.parametrize('count', [0, 2])
def test_cancel_must_match_exactly_once(count):
    page = SwitchGuardPage(None, None, cancel_count=count)
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match='exactly one visible Cancel'):
        tg._cancel_switch_model_dialog(page)
    assert page.clicks == []

def test_cancel_click_failure_remains_closed():
    page = SwitchGuardPage('cancel', 'click')
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match='Could not cancel Switch model'):
        tg._cancel_switch_model_dialog(page)

def test_valid_zero_dialog_returns():
    page = SwitchGuardPage(None, None, dialogs=0)
    tg._cancel_switch_model_dialog(page)
    assert page.clicks == []

def test_present_dialog_cancels_and_stops():
    page = SwitchGuardPage(None, None)
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match='showed a.*Switch model'):
        tg._cancel_switch_model_dialog(page)
    assert page.clicks == ['Cancel']

def test_bounded_poll_preserves_safety_query_error():
    page = SwitchGuardPage('dialog', 'count')
    with pytest.raises(tg.TTSWorkspaceUnavailableError, match='Cannot verify'):
        tg._tts_wait_until(page, lambda: bool(tg._strict_tts_visible(page, tg._TTS_SWITCH_MODEL_DIALOG_SELECTOR)))



MODEL='gemini-2.5-pro-preview-tts'
URL=f'https://aistudio.google.com/generate-speech?model={MODEL}'

class EntryReadinessPage:
    def __init__(self,delay=0,change_url=None,change_model=None):
        self.url=URL
        self.delay,self.waits=delay,0
        self.change_url,self.change_model=change_url,change_model
        self.model=MODEL
        self.actions=[]

    def locator(self,selector):
        ready=self.waits>=self.delay
        locator=SimpleNamespace(all_text_contents=lambda:[self.model] if ready else [])
        locator.first=SimpleNamespace(is_visible=lambda:ready)
        return locator

    def wait_for_timeout(self,milliseconds):
        assert milliseconds==250
        self.waits+=1
        if self.change_url:
            self.url=self.change_url
        if self.change_model:
            self.model=self.change_model

def test_delayed_entry_hydration_pumps_events_and_preserves_no_actions():
    page=EntryReadinessPage(delay=3)
    tg._wait_for_speech_workspace_ready(page,MODEL)
    assert page.waits==3
    assert page.actions==[]

@pytest.mark.parametrize('url',['https://aistudio.google.com/prompts/new_chat',
    'https://aistudio.google.com/generate-speech?model=gemini-3.8-flash'])
def test_wrong_entry_url_or_query_fails_without_wait(url):
    page=EntryReadinessPage(delay=3)
    page.url=url
    with pytest.raises(tg.TTSWorkspaceUnavailableError,match='exact target speech URL'):
        tg._wait_for_speech_workspace_ready(page,MODEL)
    assert page.waits==0
    assert page.actions==[]

def test_wrong_url_mid_poll_stops_on_first_observation():
    page=EntryReadinessPage(delay=3,change_url='https://aistudio.google.com/prompts/new_chat')
    with pytest.raises(tg.TTSWorkspaceUnavailableError,match='exact target speech URL'):
        tg._wait_for_speech_workspace_ready(page,MODEL)
    assert page.waits==1

def test_wrong_model_mid_poll_stops_before_any_action():
    page=EntryReadinessPage(delay=1,change_model='gemini-3.8-flash')
    with pytest.raises(tg.TTSWorkspaceUnavailableError,match='active model is not verified'):
        tg._wait_for_speech_workspace_ready(page,MODEL)
    assert page.waits==1
    assert page.actions==[]

def test_wrong_visible_model_at_entry_fails_immediately():
    page=EntryReadinessPage()
    page.model='gemini-3.8-flash'
    with pytest.raises(tg.TTSWorkspaceUnavailableError,match='active model is not verified'):
        tg._wait_for_speech_workspace_ready(page,MODEL)
    assert page.waits==0

def test_entry_timeout_is_bounded_and_has_no_ui_actions():
    page=EntryReadinessPage(delay=999)
    with pytest.raises(tg.TTSWorkspaceUnavailableError,match='within 20 seconds'):
        tg._wait_for_speech_workspace_ready(page,MODEL)
    assert page.waits==80
    assert page.actions==[]

def test_entry_unknown_model_fails_without_wait():
    page=EntryReadinessPage()
    with pytest.raises(tg.TTSWorkspaceUnavailableError,match='target TTS model is empty'):
        tg._wait_for_speech_workspace_ready(page,'')
    assert page.waits==0

def test_settings_poll_uses_page_event_loop_without_native_sleep(monkeypatch):
    page=EntryReadinessPage()
    monkeypatch.setattr(tg.time,'sleep',lambda *_:pytest.fail('Native sleep blocks event delivery'))
    assert tg._tts_wait_until(page,lambda:page.waits==2)
    assert page.waits==2
