"""Prompts domain package: Pydantic schemas, Socratic curation, and validation."""

from youtube_automation.prompts.notebooklm_client import NotebookLMClient
from youtube_automation.prompts.notebooklm_discover import (
    DEFAULT_RESEARCH_QUERIES,
    NotebookLMDiscoverEngine,
)
from youtube_automation.prompts.research_cache import ResearchCache
from youtube_automation.prompts.socratic_engine import (
    CuratedVisualPromptPayload,
    EpistemicClass,
    LayoutClassification,
    ResearchClusterDossier,
    SemioticTopology,
    SocraticCurationEngine,
    SocraticDialogueTurn,
)
from youtube_automation.prompts.validator import (
    STRICT_NEGATIVE_PROMPT,
    FrameItem,
    SequenceMetadata,
    VisualPrompt,
    enforce_arabic_in_prompt,
    flatten_visual_prompt_to_diffusion_text,
    purge_subtitle_phrases,
    verify_pipeline_integrity,
)

__all__ = [
    "CuratedVisualPromptPayload",
    "DEFAULT_RESEARCH_QUERIES",
    "EpistemicClass",
    "FrameItem",
    "LayoutClassification",
    "NotebookLMClient",
    "NotebookLMDiscoverEngine",
    "ResearchCache",
    "ResearchClusterDossier",
    "SemioticTopology",
    "SocraticCurationEngine",
    "SocraticDialogueTurn",
    "STRICT_NEGATIVE_PROMPT",
    "SequenceMetadata",
    "VisualPrompt",
    "enforce_arabic_in_prompt",
    "flatten_visual_prompt_to_diffusion_text",
    "purge_subtitle_phrases",
    "verify_pipeline_integrity",
]
