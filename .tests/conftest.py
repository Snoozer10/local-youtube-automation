"""Shared pytest bootstrap for the Al-Daheeh pipeline audit suite (.tests/).

Inserts the repository root onto sys.path and installs lightweight stubs for
optional heavy dependencies (python-docx) BEFORE any production module import,
so pure-logic units are testable without GUI/document dependencies.
"""

import os
import sys
import types

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p in (REPO_ROOT, TESTS_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _install_docx_stub() -> None:
    try:
        import docx  # noqa: F401

        return
    except ImportError:
        pass

    class _FakeParagraph:
        def __init__(self, *args, **kwargs):
            self._p = types.SimpleNamespace(get_or_add_pPr=lambda: [])

        def __call__(self, *args, **kwargs):
            return self

    class _FakeDocument:
        def add_heading(self, *args, **kwargs):
            return _FakeParagraph()

        def add_paragraph(self, *args, **kwargs):
            return _FakeParagraph()

        def save(self, *args, **kwargs):
            pass

    docx_mod = types.ModuleType("docx")
    docx_mod.Document = _FakeDocument

    enum_mod = types.ModuleType("docx.enum")
    text_mod = types.ModuleType("docx.enum.text")
    text_mod.WD_ALIGN_PARAGRAPH = types.SimpleNamespace(RIGHT=2, LEFT=0)

    oxml_mod = types.ModuleType("docx.oxml")

    def _fake_oxml_element(*args, **kwargs):
        return types.SimpleNamespace(tag="w:bidi", set=lambda *a, **k: None)

    oxml_mod.OxmlElement = _fake_oxml_element

    ns_mod = types.ModuleType("docx.oxml.ns")
    ns_mod.qn = lambda name: name

    docx_mod.enum = enum_mod
    enum_mod.text = text_mod
    docx_mod.oxml = oxml_mod
    oxml_mod.ns = ns_mod

    sys.modules.setdefault("docx", docx_mod)
    sys.modules.setdefault("docx.enum", enum_mod)
    sys.modules.setdefault("docx.enum.text", text_mod)
    sys.modules.setdefault("docx.oxml", oxml_mod)
    sys.modules.setdefault("docx.oxml.ns", ns_mod)


_install_docx_stub()


@pytest.fixture
def repo_cwd(monkeypatch):
    """Run the test with CWD at repository root (daheeh_config.json discovery)."""
    monkeypatch.chdir(REPO_ROOT)
    return REPO_ROOT


@pytest.fixture
def fresh_tashkeel_engine():
    """Yields a factory producing DialectTashkeelEngine instances with cache reset."""
    import refine_script

    def _factory():
        refine_script.DialectTashkeelEngine._instance = None
        refine_script.DialectTashkeelEngine._regex = None
        refine_script.DialectTashkeelEngine._lexicon = {}
        engine = refine_script.DialectTashkeelEngine()
        engine._initialize()
        return engine

    yield _factory

    refine_script.DialectTashkeelEngine._instance = None
    refine_script.DialectTashkeelEngine._regex = None
    refine_script.DialectTashkeelEngine._lexicon = {}
