### Architectural Overview & Data Flow

In an automated YouTube narration pipeline, voice direction acts as the bridge between raw text generation and text-to-speech (TTS) or audio synthesis. This stage translates script semantics, punctuation, and colloquial markers into concrete vocal dynamics: tempo changes, melodic pitch curves, breath points, and dramatic pauses.

```
+-----------------------------------+
| Input Script (Egyptian Arabic)    |
| + Tone / Energy Metadata          |
+-----------------+-----------------+
                  |
                  v
+-----------------+-----------------+
| Deterministic Fingerprinter       |  --> Hash: SHA-256(script + tags + prompt_ver)
+-----------------+-----------------+
                  |
                  v
+-----------------+-----------------+
| Cached Plan Exists?               | --- Yes ---> [ Return Cached VoiceDirectionPlan ]
+-----------------+-----------------+
                  | No
                  v
+-----------------+-----------------+
| LLM Voice Director (Gemini)       | <--- System Prompt (Egyptian Phrasing Rules)
+-----------------+-----------------+
                  |
                  v
+-----------------+-----------------+
| Strict Pydantic v2 Validation     |
| (Schema, Enums, Timestamps)       |
+--------+-----------------+--------+
         |                 |
     Success            Failure (Malformed / Schema / Timestamp Error)
         |                 |
         v                 v
[ Emit Plan ]     +--------+-----------------+
                  | Bounded Retry Loop       | (Max 3 attempts, backoff + jitter)
                  +--------+-----------------+
                           | Exceeded
                           v
                  +--------+-----------------+
                  | Deterministic Rule-Based | (Regex/punctuation fallback)
                  | Fallback Generator       |
                  +--------+-----------------+
                           |
                           v
                  [ Emit Fallback Plan ]

```

---

### 1. Pydantic v2 Schemas

```python
"""Voice Direction Domain Models (Pydantic v2).

Defines structured audio performance instructions for Arabic narration,
enforcing monotonic cue sequencing, timestamp sanity, and JSON schema export.
"""

from __future__ import annotations

import enum
import hashlib
import json
from typing import Annotated, List, Optional
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


class PacingRate(str, enum.Enum):
    VERY_SLOW = "very_slow"      # ~0.75x - solemn, highly suspenseful reveals
    SLOW = "slow"                # ~0.85x - dramatic gravity, complex concepts
    MODERATE = "moderate"        # 1.0x   - default conversational storytelling
    BRISK = "brisk"              # ~1.15x - narrative propulsion, comedic buildup
    FAST = "fast"                # ~1.3x  - urgent hooks, punchlines, comedic panic


class PitchShift(str, enum.Enum):
    DEEP_DROP = "deep_drop"      # Low pitch finish for authority/finality
    LOW = "low"                  # Conspiratorial / whispering
    BASELINE = "baseline"        # Natural vocal baseline
    HIGH = "high"                # Surprise, questioning, exclamation
    FALSETTO_SPIKE = "falsetto"  # Comedic exaggeration / sarcastic disbelief


class EmphasisLevel(str, enum.Enum):
    NONE = "none"
    SUBTLE = "subtle"            # Micro-stress on operative words
    MODERATE = "moderate"        # Sentence-level rhythmic beat
    PUNCHY = "punchy"            # Direct accentuation (e.g. comedic punchline)
    MAXIMAL = "maximal"          # Peak emotional climax or retention hook


class EgyptianEmotion(str, enum.Enum):
    CONSPIRATORIAL = "conspiratorial"    # نبرة سرية / "بيننا وبين بعض"
    SARCASTIC_SARDONIC = "sarcastic"     # تهكم / سخرية مصرية لاذعة
    SUSPENSEFUL = "suspenseful"          # ترقب وتشويق درامي
    MOCK_DISBELIEF = "mock_disbelief"    # استنكار واستغراب كوميدي ("مش معقول!")
    EXCITED_HOOK = "excited_hook"        # حماس خاطف للانتباه
    SOLEMN_GRAVE = "solemn_grave"        # جدية ورصانة
    WARM_STORYTELLER = "warm_story"      # حكواتي دافئ وجذاب
    TRIUMPHANT = "triumphant"            # نصر أو وصول لنتيجة مبهرة


class EnergyLevel(str, enum.Enum):
    LOW = "low"
    CONTROLLED = "controlled"
    DYNAMIC = "dynamic"
    HIGH = "high"
    HYPER = "hyper"


class DirectionCue(BaseModel):
    """A granular voice performance instruction bound to a script span."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
    )

    cue_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        ...,
        description="Unique identifier for the cue (e.g. 'cue_001').",
    )
    start_ms: Annotated[int, Field(ge=0)] = Field(
        ...,
        description="Relative cue start time in milliseconds from segment start.",
    )
    end_ms: Annotated[int, Field(ge=0)] = Field(
        ...,
        description="Relative cue end time in milliseconds from segment start.",
    )
    anchor_phrase: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        ...,
        description="Exact Arabic script fragment this cue governs.",
    )
    pacing: PacingRate = Field(
        default=PacingRate.MODERATE,
        description="Speech rate override for this phrase.",
    )
    pitch: PitchShift = Field(
        default=PitchShift.BASELINE,
        description="Relative pitch deviation.",
    )
    emphasis: EmphasisLevel = Field(
        default=EmphasisLevel.NONE,
        description="Acoustic stress level applied to key terms.",
    )
    pause_after_ms: Annotated[int, Field(ge=0, le=5000)] = Field(
        default=0,
        description="Dramatic or breathing pause immediately following the anchor phrase.",
    )
    emotion: EgyptianEmotion = Field(
        default=EgyptianEmotion.WARM_STORYTELLER,
        description="Dominant emotional color adapted for Egyptian dialect.",
    )
    performer_notes: Optional[str] = Field(
        default=None,
        description="Targeted inflection hint in colloquial Arabic (e.g. 'مد حرف الواو مع سخرية خفيفة').",
    )

    @model_validator(mode="after")
    def verify_time_bounds(self) -> DirectionCue:
        if self.end_ms < self.start_ms:
            raise ValueError(
                f"end_ms ({self.end_ms}) cannot precede start_ms ({self.start_ms}) in cue '{self.cue_id}'."
            )
        return self


class VoiceDirectionPlan(BaseModel):
    """Complete voice direction blueprint for a narration segment."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
    )

    plan_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        ...,
        description="Unique execution run or plan identifier.",
    )
    input_fingerprint: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")] = Field(
        ...,
        description="SHA-256 hash computed over input script, tags, and prompt version.",
    )
    overall_energy: EnergyLevel = Field(
        default=EnergyLevel.DYNAMIC,
        description="Global energy baseline for the segment.",
    )
    dialect_accent: str = Field(
        default="cairo_urban",
        description="Target sub-dialect flavor (e.g. 'cairo_urban', 'alexandrian', 'modern_informal').",
    )
    target_duration_ms: Annotated[int, Field(gt=0)] = Field(
        ...,
        description="Estimated audio duration target for the whole block.",
    )
    cues: List[DirectionCue] = Field(
        default_factory=list,
        description="Chronologically ordered sequence of voice performance cues.",
    )

    @field_validator("cues")
    @classmethod
    def verify_chronological_integrity(cls, cues: List[DirectionCue]) -> List[DirectionCue]:
        """Enforces strictly non-decreasing start times and non-overlapping progression."""
        for i in range(len(cues) - 1):
            curr = cues[i]
            nxt = cues[i + 1]

            if nxt.start_ms < curr.start_ms:
                raise ValueError(
                    f"Out-of-order cues detected: cue '{nxt.cue_id}' starts at {nxt.start_ms}ms "
                    f"before previous cue '{curr.cue_id}' start time at {curr.start_ms}ms."
                )

            if nxt.start_ms < curr.end_ms:
                raise ValueError(
                    f"Temporal overlap detected: cue '{nxt.cue_id}' starts at {nxt.start_ms}ms "
                    f"before previous cue '{curr.cue_id}' ends at {curr.end_ms}ms."
                )

        return cues

    @classmethod
    def export_schema_json(cls, indent: int = 2) -> str:
        """Exports the compliant JSON Schema for Gemini structured output enforcement."""
        return json.dumps(cls.model_json_schema(), indent=indent, ensure_ascii=False)

```

---

### 2. Gemini System Prompt (Nuanced Egyptian Arabic)

```text
You are an elite Voice Director and Performance Coach specializing in high-retention Arabic YouTube content, specifically focusing on Cairo urban Egyptian Arabic (العامية المصرية).

Your job is to read raw Egyptian Arabic narration scripts and emit an audio performance blueprint conforming to the `VoiceDirectionPlan` schema. You dictate tempo, dramatic breathing pauses, melodic pitch changes, and vocal intensity.

---

### Core Performance Principles for Egyptian Arabic Narration

1. The Narrative Hook (أول 15 ثانية):
   - Fast, punchy delivery (`pacing: "fast"`, `energy: "high"`, `emotion: "excited_hook"`).
   - Use high pitch shifts on rhetorical openings ("عارف مين ده؟", "تخيل معايا...").
   - Cut pauses to under 150ms to prevent viewer drop-off.

2. Rhetorical Inquiry & Sarcasm (الاستنكار والتهكم المصري):
   - Egyptian Arabic relies on melodic musicality for irony.
   - For sarcastic transitions ("وده كان رأي العباقرة برضه!", "يا راجل؟"), apply `pitch: "falsetto"` or `"high"`, followed by a 400ms-600ms pregnant silence (`pause_after_ms: 500`).
   - Elongate operative syllables in `performer_notes` (e.g., "مدّ صوت الألف في 'ياااا راجل' بنبرة استنكار").

3. Suspense & Conspiratorial Drops (الساسبنس ونبرة الأسرار):
   - Drop the voice to a lower register (`pitch: "low"` or `"deep_drop"`) and slow down (`pacing: "slow"`, `emotion: "conspiratorial"`).
   - Insert significant pauses (600ms - 1200ms) before revealing key facts or numbers ("وفجأة... لقى نفسه مطلوب دولياً").

4. Transition Markers & Colloquial Anchors (المطبات اللغوية):
   - Pay attention to Egyptian discourse markers: "المهم", "بص بقى", "تخيل يا سيدي", "من الآخر", "الغريب في الموضوع".
   - Accelerate into the phrase, place a punchy stress on the marker, and pause briefly after it before delivering the proposition.

5. Monotonic & Temporal Invariants:
   - Every cue's `start_ms` must be >= previous cue's `end_ms`.
   - `end_ms` must always exceed `start_ms`.
   - Allocate reasonable duration based on word count (~150-180 words per minute average for Egyptian Arabic storytelling).

---

### Schema Constraints
You must respond with valid JSON matching the `VoiceDirectionPlan` schema. Do not output conversational filler, markdown explanations, or unquoted text.

```

---

### 3. Pipeline Implementation: Idempotency, Retries, and Graceful Fallback

```python
"""Voice Direction Pipeline Engine.

Handles deterministic input hashing, bounded retries with jitter,
Pydantic parsing, and deterministic fallback generation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
from typing import Any, Callable, Dict, Optional

from pydantic import ValidationError

# Configure logger
logger = logging.getLogger("voice_direction_pipeline")
PROMPT_VERSION = "v2.1.0-egyptian"


def compute_stage_fingerprint(
    script_text: str,
    tone_tags: list[str],
    prompt_version: str = PROMPT_VERSION,
) -> str:
    """Produces a deterministic SHA-256 hash identifying this exact input state."""
    canonical_payload = {
        "script": script_text.strip(),
        "tags": sorted(tag.strip().lower() for tag in tone_tags),
        "prompt_version": prompt_version,
    }
    serialized = json.dumps(canonical_payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class FallbackVoiceDirectionEngine:
    """Deterministic, rule-based fallback when model inference or parsing fails repeatedly."""

    @staticmethod
    def generate(
        script_text: str,
        fingerprint: str,
        overall_energy: EnergyLevel = EnergyLevel.DYNAMIC,
    ) -> VoiceDirectionPlan:
        """Splits script into sentences/clauses using Arabic punctuation and creates baseline cues."""
        raw_clauses = re.split(r"([،.؟!…\n]+)", script_text)
        clauses: list[str] = []
        for i in range(0, len(raw_clauses) - 1, 2):
            clause = (raw_clauses[i] + raw_clauses[i + 1]).strip()
            if clause:
                clauses.append(clause)
        if len(raw_clauses) % 2 == 1 and raw_clauses[-1].strip():
            clauses.append(raw_clauses[-1].strip())

        if not clauses:
            clauses = [script_text.strip() or "نص تجريبي"]

        cues: list[DirectionCue] = []
        current_time_ms = 0

        for idx, clause in enumerate(clauses):
            word_count = max(1, len(clause.split()))
            # Standard conversational pacing: ~320ms per word in Egyptian narrative
            duration_ms = word_count * 320

            pause_ms = 250
            emotion = EgyptianEmotion.WARM_STORYTELLER
            pitch = PitchShift.BASELINE
            pacing = PacingRate.MODERATE
            emphasis = EmphasisLevel.NONE

            if "؟" in clause:
                pitch = PitchShift.HIGH
                pause_ms = 400
                emotion = EgyptianEmotion.MOCK_DISBELIEF
            elif "!" in clause:
                emphasis = EmphasisLevel.PUNCHY
                pause_ms = 450
                emotion = EgyptianEmotion.EXCITED_HOOK
            elif "..." in clause or "…" in clause:
                pacing = PacingRate.SLOW
                pause_ms = 700
                emotion = EgyptianEmotion.SUSPENSEFUL
                pitch = PitchShift.LOW

            cue = DirectionCue(
                cue_id=f"fb_cue_{idx+1:03d}",
                start_ms=current_time_ms,
                end_ms=current_time_ms + duration_ms,
                anchor_phrase=clause,
                pacing=pacing,
                pitch=pitch,
                emphasis=emphasis,
                pause_after_ms=pause_ms,
                emotion=emotion,
                performer_notes="توليد تلقائي احتياطي مستند إلى علامات الترقيم",
            )
            cues.append(cue)
            current_time_ms += duration_ms + pause_ms

        return VoiceDirectionPlan(
            plan_id=f"fallback_{fingerprint[:12]}",
            input_fingerprint=fingerprint,
            overall_energy=overall_energy,
            dialect_accent="cairo_urban",
            target_duration_ms=max(current_time_ms, 1000),
            cues=cues,
        )


class VoiceDirectionStage:
    """Robust orchestration stage with bounded retries, schema parsing, and fallback."""

    def __init__(
        self,
        llm_caller: Callable[[str, str], str],
        max_retries: int = 3,
        base_backoff_sec: float = 0.5,
    ) -> None:
        self.llm_caller = llm_caller
        self.max_retries = max_retries
        self.base_backoff_sec = base_backoff_sec

    def process(
        self,
        script_text: str,
        tone_tags: list[str],
        energy_level: EnergyLevel = EnergyLevel.DYNAMIC,
    ) -> VoiceDirectionPlan:
        fingerprint = compute_stage_fingerprint(script_text, tone_tags)
        system_prompt = "..."  # Load system prompt
        user_prompt = json.dumps(
            {
                "script": script_text,
                "tags": tone_tags,
                "fingerprint": fingerprint,
                "overall_energy": energy_level.value,
            },
            ensure_ascii=False,
        )

        for attempt in range(1, self.max_retries + 1):
            try:
                raw_response = self.llm_caller(system_prompt, user_prompt)
                plan = VoiceDirectionPlan.model_validate_json(raw_response)
                logger.info("Successfully validated VoiceDirectionPlan on attempt %d", attempt)
                return plan

            except (ValidationError, json.JSONDecodeError, ValueError) as err:
                logger.warning(
                    "Attempt %d/%d failed validation for fingerprint %s: %s",
                    attempt,
                    self.max_retries,
                    fingerprint,
                    str(err),
                )
                if attempt == self.max_retries:
                    break

                backoff = self.base_backoff_sec * (2 ** (attempt - 1)) + random.uniform(0.05, 0.2)
                time.sleep(backoff)

        logger.error(
            "Exhausted %d retries for fingerprint %s. Triggering fallback.",
            self.max_retries,
            fingerprint,
        )
        return FallbackVoiceDirectionEngine.generate(
            script_text=script_text,
            fingerprint=fingerprint,
            overall_energy=energy_level,
        )

```

---

### 4. Unit Test Fixtures (`pytest`)

```python
"""Test suite verifying validation boundaries, error handling, and recovery."""

import json
import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_plan_dict() -> dict:
    return {
        "plan_id": "plan_eg_001",
        "input_fingerprint": "a" * 64,
        "overall_energy": "dynamic",
        "dialect_accent": "cairo_urban",
        "target_duration_ms": 6000,
        "cues": [
            {
                "cue_id": "cue_001",
                "start_ms": 0,
                "end_ms": 1500,
                "anchor_phrase": "عارف مين الراجل ده؟",
                "pacing": "fast",
                "pitch": "high",
                "emphasis": "punchy",
                "pause_after_ms": 300,
                "emotion": "excited_hook",
                "performer_notes": "نبرة استفهام تشويقية مع ابتسامة صوتية",
            },
            {
                "cue_id": "cue_002",
                "start_ms": 1800,
                "end_ms": 4200,
                "anchor_phrase": "ده يا سيدي اللي قلب موازين اللعبة كلها في أسبوع واحد!",
                "pacing": "moderate",
                "pitch": "baseline",
                "emphasis": "moderate",
                "pause_after_ms": 500,
                "emotion": "warm_story",
                "performer_notes": "تركيز على كلمة 'أسبوع واحد' مع نبرة حكواتي",
            },
        ],
    }


@pytest.fixture
def malformed_json_strings() -> list[str]:
    return [
        "{ invalid_json: missing_quotes }",
        '{"plan_id": "p1", "cues": [}',  # Truncated syntax
        "",                              # Empty string
        '{"plan_id": 12345}',            # Type violation & missing fields
    ]


@pytest.fixture
def out_of_order_cues_dict(valid_plan_dict: dict) -> dict:
    invalid = json.loads(json.dumps(valid_plan_dict))
    # Flip chronological sequence: cue 2 starts before cue 1
    invalid["cues"][0]["start_ms"] = 3000
    invalid["cues"][0]["end_ms"] = 4500
    invalid["cues"][1]["start_ms"] = 1000
    invalid["cues"][1]["end_ms"] = 2500
    return invalid


@pytest.fixture
def overlapping_cues_dict(valid_plan_dict: dict) -> dict:
    invalid = json.loads(json.dumps(valid_plan_dict))
    # Cue 2 starts at 1200ms while cue 1 ends at 1500ms
    invalid["cues"][1]["start_ms"] = 1200
    return invalid


@pytest.fixture
def inverted_cue_bounds_dict(valid_plan_dict: dict) -> dict:
    invalid = json.loads(json.dumps(valid_plan_dict))
    # Single cue has end_ms < start_ms
    invalid["cues"][0]["start_ms"] = 2000
    invalid["cues"][0]["end_ms"] = 1000
    return invalid


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_valid_plan_deserialization(valid_plan_dict: dict):
    """Verifies that a valid dictionary parses cleanly into a VoiceDirectionPlan."""
    plan = VoiceDirectionPlan.model_validate(valid_plan_dict)
    assert plan.plan_id == "plan_eg_001"
    assert len(plan.cues) == 2
    assert plan.cues[0].emotion == EgyptianEmotion.EXCITED_HOOK


def test_schema_json_exportable():
    """Validates that OpenAPI / JSON Schema generation runs without error."""
    schema_str = VoiceDirectionPlan.export_schema_json()
    schema = json.loads(schema_str)
    assert schema["type"] == "object"
    assert "cues" in schema["properties"]
    assert "input_fingerprint" in schema["properties"]


@pytest.mark.parametrize("bad_json", [
    "{ invalid_json: missing_quotes }",
    '{"plan_id": "p1", "cues": [}',
    "",
])
def test_malformed_json_triggers_validation_error(bad_json: str):
    """Confirms that syntax errors and raw truncation raise ValidationError or JSONDecodeError."""
    with pytest.raises((ValidationError, json.JSONDecodeError)):
        VoiceDirectionPlan.model_validate_json(bad_json)


def test_out_of_order_timestamps_triggers_validation_error(out_of_order_cues_dict: dict):
    """Enforces rejection when cues do not progress chronologically."""
    with pytest.raises(ValidationError) as exc_info:
        VoiceDirectionPlan.model_validate(out_of_order_cues_dict)
    assert "Out-of-order cues detected" in str(exc_info.value)


def test_overlapping_timestamps_triggers_validation_error(overlapping_cues_dict: dict):
    """Enforces rejection when a cue begins before the prior cue finishes."""
    with pytest.raises(ValidationError) as exc_info:
        VoiceDirectionPlan.model_validate(overlapping_cues_dict)
    assert "Temporal overlap detected" in str(exc_info.value)


def test_inverted_single_cue_bounds_triggers_validation_error(inverted_cue_bounds_dict: dict):
    """Enforces rejection if any cue has end_ms < start_ms."""
    with pytest.raises(ValidationError) as exc_info:
        VoiceDirectionPlan.model_validate(inverted_cue_bounds_dict)
    assert "cannot precede start_ms" in str(exc_info.value)


def test_fingerprint_deterministic_and_idempotent():
    """Guarantees identical inputs yield identical SHA-256 digests regardless of tag ordering."""
    script = "بص يا سيدي... الموضوع أبسط مما تتخيل."
    tags1 = ["Dramatic", "Egyptian", "Hook"]
    tags2 = ["hook", "dramatic ", "egyptian"]

    fp1 = compute_stage_fingerprint(script, tags1)
    fp2 = compute_stage_fingerprint(script, tags2)
    assert fp1 == fp2
    assert len(fp1) == 64


def test_fallback_engine_produces_monotonic_cues():
    """Confirms rule-based fallback satisfies all schema invariants and preserves temporal order."""
    script = "عارف مين ده؟ ده يا سيدي المعلم الكبير! الغريب في الموضوع... محدش شافه قبل كده."
    fingerprint = compute_stage_fingerprint(script, ["fallback_test"])

    fallback_plan = FallbackVoiceDirectionEngine.generate(
        script_text=script,
        fingerprint=fingerprint,
        overall_energy=EnergyLevel.DYNAMIC,
    )

    # Validate output against full Pydantic v2 engine
    assert fallback_plan.input_fingerprint == fingerprint
    assert len(fallback_plan.cues) >= 3

    # Check temporal ordering
    for i in range(len(fallback_plan.cues) - 1):
        c1 = fallback_plan.cues[i]
        c2 = fallback_plan.cues[i + 1]
        assert c1.end_ms <= c2.start_ms
        assert c1.start_ms < c1.end_ms

```