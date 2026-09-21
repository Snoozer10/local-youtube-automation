# Adaptive multi-channel visual production engine

Branch: `codex/adaptive-multi-channel-visual-engine`, from updated master `dad17b3` after PR #20. GEMINI.md controls current project guidance; preserve DOX and facade compatibility.

## Approved architecture
Selected saved channel + raw script -> whole-script analysis -> validated episode brief -> adapted restructuring/translation/refinement -> voice and canonical speech timing -> editorial shots -> reference-bound stills/local overlays -> quality review -> deterministic render -> verified publication.

For pilots built from published channel episodes, the original narration and caption excerpt are one immutable input pair. Analyze the excerpt under the selected channel, then import the matching owner-provided local audio segment and preserve the spoken script verbatim. Transcribe that accepted WAV to the canonical timeline before planning shots. This path tests the actual channels' pacing without claiming a rewrite was spoken.

Channel profiles own audience, language/dialect, narrator and host identity, brand and allowed treatments. Episode analysis proposes topics, genre, narrative form, claim basis, external fact-check questions, source-stated continuity anchors, figurative language and visual strategy within those limits. Fictional continuity is not evidence, and evidence requests are not shot requests. Analysis cannot change identity or browser selectors. Shots specify visual purpose, narration range, entities, references, composition, edits and overlays. Shots may cover multiple spans or subdivide one span. Canonical speech timing remains authoritative.

## Priorities
- **Remediate / P0:** coordinate leakage, unsolicited charts, truncated edits, schema aliases, reference identity, forced movement and missing assets.
- **Update / P1:** versioned contracts and channel-aware writing/visual rules; preserve legacy entrypoints.
- **Refine / P1:** semantic visual beats, idiom handling, meaningful changes instead of compulsory progression and camera cycles.
- **Improve / P0-P1:** full-frame generated-background OCR, reference/crop/coverage checks, bounded recovery and atomic publication.
- **Enrich / P1:** prompts, decision reasons, references, attempts, quality status and review reports.
- **Enhance / P1:** full-frame scenes, factual diagrams, local Arabic typography, purposeful restrained motion and accepted-image reuse.
- **Upgrade / P2:** adaptive brief compiler, editorial graph/compositor, SQLite production ledger with artifact lineage and leases.

## Rollout and constraints
Use existing Gemini/Flow browser adapters and local Python/FFmpeg; no new cloud SDK. Complete verified output required. Land tested vertical slices; adaptive mode stays opt-in until three contrasting 60-90 second pilots pass editorial review. Preserve historical runs and assets. No automatic full-episode regeneration, publication, release or merge. Invalid adaptive inputs must not silently fall back to legacy. New recipes include source/profile/brief versions. Layered parallax follows basic editorial correctness.

## Acceptance and verification
Different channels adapt the same script without changing facts; topics vary within a consistent channel identity. Mixed topics remain explicit. Idioms do not automatically become props. Close-ups honor intent. Browser-feed changes cannot substitute references. Missing assets block publication. Backgrounds contain no accidental text; Arabic overlays shape correctly. Holds stay still, crops preserve subjects and edits cover exact audio duration. Changed inputs invalidate affected artifacts. Offline tests do not establish live browser or artistic quality.

Run focused tests per slice, full unit suite, `ruff check .`, CI-equivalent checks, exercise linter and temporary real FFmpeg clips. Track progress and exact evidence in [adaptive-visual-tasks.md](adaptive-visual-tasks.md).
