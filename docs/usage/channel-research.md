# Channel research and external REA

In this guide, **REA** means the external project [morluto/rea](https://github.com/morluto/rea), whose name expands to “Reverse Engineer Anything.” It is a separate MCP-oriented project for inspecting software and runtime behavior. Its browser-observation documentation describes bounded, passive observation of an already-open page through a user-owned Chrome-family browser's CDP connection; it is not general browser automation or remote control. These are upstream project capabilities, not features shipped or integrated by this repository. See the [official REA README](https://github.com/morluto/rea/blob/main/README.md) and [browser observation guide](https://github.com/morluto/rea/blob/main/docs/browser-observation.md) for current upstream scope (checked 2026-11-02).

This pipeline's implemented study APIs support an **offline substitution**: people can manually study reference material, then enter attributable evidence and reviewed traits to derive a channel profile. The project does not bundle REA, expose an REA command or MCP integration, or implement a live REA collector. Live external Windows collection has not been qualified for this repository. Do not treat the Python study APIs below as a bridge to the external project.

## Offline reference-channel study

An offline study records observable channel patterns to inform a distinct production profile. It records evidence, uncertainty and human interpretations; it is not a promise to clone another creator, and it does not automatically collect channel data or approve a derived profile for production.

## Research scope and evidence

Start with an explicit study question: what channel-level patterns do you need to understand, and for what intended audience or production decision? Select representative source items using a documented rationale. Capture enough variety to test whether a pattern recurs, and record the items and portions examined. Avoid treating one unusually successful upload as a channel-wide rule.

For each source observation, distinguish:

- **Direct observation:** what is visible or audible in the source and exactly which item or time range supports it.
- **Interpretation:** what you infer about its narrative purpose, audience need, tone, structure, visual motion, sound or packaging.
- **Uncertainty:** which source items were unavailable or atypical, what could have another explanation, and what evidence would change the interpretation.
- **Human decision:** whether the pattern is suitable for your own channel. A repeated pattern in a reference is not by itself a reason to adopt it.

The study model stores candidate videos, a sampling policy, selected sample, evidence records, core and optional traits, readiness gaps and cumulative spend. Evidence records include a video identifier, modality, examined range, SHA-256, byte count, owner-supplied status and notes. Keep source attribution and examination notes accurate; do not convert a guess into an observed fact.

The evidence collector stores evidence bytes beneath the study directory's `evidence/` folder and records integrity metadata. Keep private, licensed or account-bound source evidence outside Git. Commit neither secrets nor private media/transcripts. The study's hashes help detect changed evidence; they do not establish permission, authenticity or correctness.

## What is implemented

The implemented offline interfaces are in [`study.py`](../../src/youtube_automation/production/study.py) and [`profile_activation.py`](../../src/youtube_automation/production/profile_activation.py):

| Interface | Purpose |
|---|---|
| `StudyCollector.initialize_study(...)` | Create and persist a study from a study ID, channel ID, candidate list and optional `SamplingPolicy`. |
| `StudyCollector.add_evidence(...)` | Store evidence bytes and metadata for a selected candidate. |
| `StudyCollector.record_core_trait(...)` | Record an interpretation with the source video and evidence IDs it relies on. |
| `StudyCollector.verify_evidence_integrity(...)` | Check recorded evidence files against their hashes and sizes. |
| `evaluate_study_readiness(study)` | Return the status and actionable gaps for the current study. |
| `derive_production_profile(study, owner_settings=None)` | Derive a profile only when the study is `CORE_READY`, combining evidence-derived guidance with owner settings. |
| `ProfileActivationManager.publish_and_activate(...)` | Publish an immutable profile revision and atomically update the active revision pointer. |
| `ProfileActivationManager.recover_interrupted_activation()` | Recover an interrupted activation journal using the supported recovery path. |
| `ProfileActivationManager.get_active_revision()` / `resolve_channel()` | Read the active revision identity or resolve it as a validated `Channel`. |

The repository exposes no REA CLI, REA client, or live collection interface. The offline APIs do not perform web searches, browser attachment, video downloads, transcript extraction or human review for you. You can perform research manually and supply the resulting attributable evidence through the Python API; do not infer that a study API is a live collector or an integration with morluto/rea. Any future integration would need its own documented entry point, permission boundary, limits and evidence contract.

## Create an offline study record

This minimal example uses only synthetic metadata and a temporary directory. It demonstrates study initialization and readiness reporting; it is not a real reference-channel study and will not become ready without qualifying evidence and reviewed traits.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from youtube_automation.production.study import (
    CandidateVideo,
    StudyCollector,
    evaluate_study_readiness,
)

candidates = [
    CandidateVideo(
        video_id="offline-example-01",
        title="Synthetic candidate one",
        published_at="2025-01-01",
        duration_sec=600,
    ),
    CandidateVideo(
        video_id="offline-example-02",
        title="Synthetic candidate two",
        published_at="2025-02-01",
        duration_sec=720,
    ),
]

with TemporaryDirectory(prefix="channel-study-example-") as temp:
    collector = StudyCollector(Path(temp))
    study = collector.initialize_study(
        study_id="offline-demo",
        channel_id="example-channel",
        candidates=candidates,
    )
    status, gaps = evaluate_study_readiness(study)
    print(status.value)
    print("; ".join(gaps))
```

The temporary record is removed when the block ends. For a real study, use a durable private directory, real candidate metadata, the configured sampling policy, and evidence you are permitted to examine. Record source IDs and the examined range when adding evidence. Do not add empty or fabricated evidence just to move readiness forward.

## Readiness and profile derivation

Readiness is policy-bound. `evaluate_study_readiness` checks the distinct selected sample against the study's `SamplingPolicy`, the duration, evidence-byte, external-attempt and external-time limits, evidence presence and integrity, and evidence references for recorded traits. Do not copy a historical sample count or spend cap from an old note; inspect the active policy on the study and report its gaps.

The required core traits are:

| Trait key | Research question |
|---|---|
| `subject_promise` | What subject or promise consistently defines the reference channel? |
| `viewer_need` | What recurring viewer need does its format appear to serve? |
| `tone_register` | What tone and register are supported across sampled items? |
| `narrative_structure` | What recurring narrative structure is evidenced by the sample? |

Optional study areas are `visual_motion`, `soundtrack` and `packaging`. A study can be `PARTIAL` while evidence or trait coverage is incomplete. `CORE_READY` means the program's current mandatory evidence and trait rules pass; it does not mean a researcher has reached certainty or an owner has approved the style for production.

Only derive after reviewing every core claim against its linked items and evidence. The API rejects a non-`CORE_READY` study. `derive_production_profile` returns a `DerivedProductionProfile`, not a `Channel` JSON profile. It contains study-derived guidance and provenance plus owner-provided choices; it cannot decide whether those patterns are desirable, faithful, original or appropriate for a particular episode. Keep owner voice, language, policy and other settings explicit, then review the derived object before using the separate activation flow below.

Hand-authored profiles follow the simpler path in [Channel profiles and bundles](./channel-bundles.md). They do not require creating a study or activating a research-derived revision.

## Publish, activate and recover revisions

The activation manager publishes profile revisions immutably. Published `profile.json` bytes carry a separate `profile.sha256` integrity receipt. This exact-byte receipt is distinct from canonical profile digests and revision naming; the active revision is selected through the manager's atomic pointer/journal flow. A revised study or channel policy should produce a new revision; do not edit files inside an activated revision or alter the active pointer by hand.

After reviewing the derived object and its source-to-claim links, the implemented sequence is `derive_production_profile(study, owner_settings)` → human review → `ProfileActivationManager(channel_dir).publish_and_activate(derived)` → resolve the activated channel with `ProfileActivationManager(channel_dir).resolve_channel()` or `load_channel(channel_dir)`. The resolver maps the active derived revision into the runtime `Channel` contract. `load_channel` accepts either a hand-authored Channel JSON file or an activated channel directory; it does not convert an unactivated `DerivedProductionProfile` JSON file into a `Channel`.

`publish_and_activate` changes active channel configuration, so treat it as an explicit owner action after profile review. For Adaptive staged mode, pass the activated channel directory to `analyze --channel-profile <channel-dir>`; use a hand-authored Channel JSON path when selecting a personal profile directly. A successful activation is a configuration state change, not editorial approval for future scripts or generated media.

The supported recovery API is `recover_interrupted_activation()`. It exists for interrupted activation state; it is not a general-purpose rollback command. The inspected manager exposes active-revision reading and interrupted-activation recovery, but no dedicated rollback method. If you need to return to an earlier profile revision, use a separately documented and reviewed supported operation when available; never improvise by changing the pointer or rewriting immutable revision files.

## Research record checklist

- State the study question and intended use.
- Preserve the candidate pool, selection rationale and active sampling policy with the study record.
- Attribute evidence to a source item and modality; record examined ranges, file hashes, sizes and notes.
- Keep observed facts, inferences, uncertainties and owner choices distinct.
- Support each core trait with evidence across the selected sample; do not derive from a single item's distinctive flourish.
- Record actionable gaps and review them before derivation.
- Store private evidence outside Git and protect it with the same access controls as the source.
- Preserve the study and activated revision lineage so later changes can be compared without mutating prior evidence.

## Related documentation

- [Adaptive staged mode](./adaptive-mode.md) — use a selected profile in a production run.
- [Channel profiles and bundles](./channel-bundles.md) — create and validate a hand-authored profile.
- [Study implementation](../../src/youtube_automation/production/study.py) and [profile activation implementation](../../src/youtube_automation/production/profile_activation.py) — authoritative Python contracts.
- [Production contract](../../src/youtube_automation/production/AGENTS.md) — production ownership and operational constraints.
