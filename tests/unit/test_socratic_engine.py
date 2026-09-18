"""Unit tests for the Socratic Visual Prompt Curation Engine and NotebookLM cache."""

from pathlib import Path

from youtube_automation.prompts.notebooklm_client import NotebookLMClient
from youtube_automation.prompts.research_cache import ResearchCache
from youtube_automation.prompts.socratic_engine import (
    CuratedVisualPromptPayload,
    EpistemicClass,
    ResearchClusterDossier,
    SocraticCurationEngine,
)
from youtube_automation.prompts.validator import (
    validate_english_only_prompt,
)


def test_research_cache_roundtrip(tmp_path: Path):
    """Verifies that ResearchCache stores, retrieves, and hashes deterministically."""
    cache = ResearchCache(cache_dir=tmp_path)
    notebook_id = "test-notebook"
    query = "What is 1x1 in arithmetic?"
    response = "1x1 is 1 by multiplicative identity."

    assert not cache.has(notebook_id, query)
    key = cache.set(notebook_id, query, response)
    assert cache.has(notebook_id, query)

    # Retrieval
    entry = cache.get(notebook_id, query)
    assert entry is not None
    assert entry["response"] == response
    assert entry["cache_key"] == key

    # Convenience text getter
    assert cache.get_response_text(notebook_id, query) == response

    # Purge
    deleted = cache.clear()
    assert deleted == 1
    assert not cache.has(notebook_id, query)


def test_notebooklm_client_mock_and_cache(tmp_path: Path):
    """Verifies that NotebookLMClient queries properly in mock mode and caches."""
    client = NotebookLMClient(cache_dir=tmp_path, mock_mode=True)
    question = "Mathematical proof of 1x1=1 vs 1x1=2"

    resp = client.query(question, notebook_id="test-nb")
    assert "multiplicative identity" in resp.lower() or "peano" in resp.lower()

    # Second call must hit disk cache
    cached_resp = client.query(question, notebook_id="test-nb")
    assert cached_resp == resp


def test_socratic_engine_interrogate(tmp_path: Path):
    """Verifies the 5-round dialectical interrogation loop."""
    client = NotebookLMClient(cache_dir=tmp_path, mock_mode=True)
    engine = SocraticCurationEngine(client=client, notebook_id="test-nb")

    dossier = engine.interrogate(
        cluster_id="CLUSTER_01",
        topic="Multiplicative Identity and Terrence Howard Fallacy",
        script_excerpt="واحد في واحد بيساوي اتنين لأن الضرب يعني التكرار",
    )

    assert isinstance(dossier, ResearchClusterDossier)
    assert dossier.cluster_id == "CLUSTER_01"
    assert len(dossier.turns) == 4
    assert dossier.turns[0].round_name == "Elenchus"
    assert dossier.turns[1].round_name == "Morphology"
    assert dossier.turns[2].round_name == "Antithesis"
    assert dossier.turns[3].round_name == "Semiotics"
    assert dossier.epistemic_class == EpistemicClass.DEBUNK_DISSECTION


def test_socratic_engine_synthesize_prompt(tmp_path: Path):
    """Verifies that the synthesized prompt complies with the 8-part schema and validator."""
    client = NotebookLMClient(cache_dir=tmp_path, mock_mode=True)
    engine = SocraticCurationEngine(client=client, notebook_id="test-nb")

    dossier = engine.interrogate(
        cluster_id="CLUSTER_02",
        topic="Walter Russell Periodic Spiral Vortex",
        script_excerpt="والتر راسل عمل جدول دوري حلزوني واعتبر الذرات دوامات",
    )

    payload = engine.synthesize_prompt(
        dossier=dossier,
        frame_index=15,
        timestamp="[01:12]",
        character_handle="HOST",
    )

    assert isinstance(payload, CuratedVisualPromptPayload)
    assert payload.frame_index == 15
    assert payload.timestamp == "[01:12]"
    assert payload.visual_prompt.continuity_id == "CHARACTER_HOST_MAIN"
    assert "Ahmed El-Ghandour" in payload.visual_prompt.subject

    # Validate against Pydantic VisualPrompt invariants
    assert payload.visual_prompt.subject
    assert payload.visual_prompt.style

    # Validate diffusion prompt is English only (no raw Arabic script)
    is_english, err = validate_english_only_prompt(payload.diffusion_prompt_text)
    assert is_english, f"Diffusion prompt contains un-transliterated Arabic: {err}"

    # Verify negative prompt invariants
    assert "no subtitles" in payload.diffusion_prompt_text.lower()
    assert "no photorealism" in payload.diffusion_prompt_text.lower()
