"""Unit tests for NotebookLM Web Discover & Deep Research Engine."""

from unittest.mock import MagicMock

import pytest

from youtube_automation.prompts.notebooklm_discover import (
    DEFAULT_RESEARCH_QUERIES,
    NotebookLMDiscoverEngine,
)


def test_default_research_queries_structure():
    """Validates structure and completeness of the 4 visual research queries."""
    assert len(DEFAULT_RESEARCH_QUERIES) == 4

    modes = [q["mode"] for q in DEFAULT_RESEARCH_QUERIES]
    assert modes.count("fast") == 2
    assert modes.count("deep") == 2

    for q in DEFAULT_RESEARCH_QUERIES:
        assert "id" in q
        assert "domain" in q
        assert "seed" in q
        assert "query" in q
        assert len(q["query"]) > 40
        assert q["max_sources"] == 10

    # Verify key visual prompt engineering seeds are present
    seeds = [q["seed"] for q in DEFAULT_RESEARCH_QUERIES]
    assert any("nano banana" in s.lower() for s in seeds)
    assert any("shinobi" in s.lower() for s in seeds)
    assert any("retention" in s.lower() for s in seeds)


def test_discover_engine_initialization():
    """Validates engine initialization and configuration bounds."""
    engine = NotebookLMDiscoverEngine(
        notebook_url="https://notebook.google.com/notebook/test-uuid",
        headless=True,
        mock_mode=True,
        timeout_seconds=120,
    )
    assert engine.notebook_url == "https://notebook.google.com/notebook/test-uuid"
    assert engine.headless is True
    assert engine.mock_mode is True
    assert engine.timeout_seconds == 120
    assert engine.max_source_ceiling == 300


def test_mock_batch_execution():
    """Validates end-to-end batch execution in mock mode."""
    engine = NotebookLMDiscoverEngine(mock_mode=True)
    report = engine.execute_batch()

    assert report["total_queries"] == 4
    assert report["successful_queries"] == 4
    assert report["total_ingested_sources"] == 40
    assert report["final_source_count"] == 40

    results = report["results"]
    assert len(results) == 4
    assert results[0]["id"] == "Q1"
    assert results[0]["selected_sources"] == 10
    assert results[1]["id"] == "Q2"
    assert results[2]["id"] == "Q3"
    assert results[3]["id"] == "Q4"
    assert all(r["success"] is True for r in results)


def test_source_ceiling_guard():
    """Validates that ingestion aborts when approaching the 300 source ceiling."""
    engine = NotebookLMDiscoverEngine(mock_mode=False)

    # Mock count_sources to return 295
    engine.count_sources = MagicMock(return_value=295)

    with pytest.raises(ValueError, match="exceed 300 source maximum ceiling"):
        engine.execute_query_flow(
            page=None,
            query_def={
                "id": "Q_OVERFLOW",
                "mode": "fast",
                "query": "Test overflow query",
                "max_sources": 10,
            },
        )


def test_simulated_dom_modal_and_query_injection():
    """Validates modal opening and query injection using mock Playwright page."""
    engine = NotebookLMDiscoverEngine(mock_mode=False)

    mock_page = MagicMock()
    mock_elem = MagicMock()

    # Configure locator mocks
    mock_page.locator.return_value = mock_elem
    mock_elem.first = mock_elem
    mock_elem.is_visible.return_value = True
    mock_elem.is_disabled.return_value = False
    mock_elem.text_content.return_value = "Fast Research"

    # 1. Test modal opening
    success = engine.open_discover_modal(mock_page)
    assert success is True

    # 2. Test mode toggling
    toggled = engine.set_research_mode(mock_page, mode="deep")
    assert toggled is True

    # 3. Test query submission
    submitted = engine.submit_research_query(mock_page, query="Test diffusion prompt", mode="fast")
    assert submitted is True
    mock_elem.fill.assert_called_with("Test diffusion prompt")


def test_simulated_top_sources_selection():
    """Validates top N candidate selection logic."""
    engine = NotebookLMDiscoverEngine(mock_mode=False)

    mock_page = MagicMock()
    selected = engine.select_top_sources(mock_page, max_sources=10)
    assert selected == 10
