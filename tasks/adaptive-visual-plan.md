# Adaptive multi-channel visual production engine

Branch: `codex/adaptive-multi-channel-visual-engine`, from updated master `dad17b3` after PR #20. GEMINI.md controls current project guidance; preserve DOX and facade compatibility.

## Approved architecture
Selected saved channel + raw script -> whole-script analysis -> validated episode brief -> adapted restructuring/translation/refinement -> voice and canonical speech timing -> editorial shots -> reference-bound stills/local overlays -> quality review -> deterministic render -> verified publication.

For pilots built from published channel episodes, the original narration and caption excerpt are one immutable input pair. Analyze the excerpt under the selected channel, then import the matching owner-provided local audio segment and preserve the spoken script verbatim. Transcribe that accepted WAV to the canonical timeline before planning shots. This path tests the actual channels' pacing without claiming a rewrite was spoken.

Channel profiles own audience, language/dialect, narrator and host identity, brand and allowed treatments. Episode analysis proposes topics, genre, narrative form, claim basis, external fact-check questions, source-stated continuity anchors, figurative language and visual strategy within those limits. Fictional continuity is not evidence, and evidence requests are not shot requests. Analysis cannot change identity or browser selectors. Shots specify visual purpose, narration range, entities, references, composition, edits and overlays. Shots may cover multiple spans or subdivide one span. Canonical speech timing remains authoritative.

## Episode-adaptive editorial intelligence

The saved channel profile is a durable **brand constitution**, not a fixed template for every upload. Each URL must compile a separate, content-bound **episode visual strategy** from the raw source before translation, writing or shot planning. The strategy may vary the hook, visual modes, UI language, pacing, color emphasis, motion intensity and evidence treatment while preserving the channel's voice, audience, trust standard and recognizable design DNA.

### Three-layer decision model

1. **Channel constitution:** stable audience, voice, host policy, baseline palette, typography, humor, trust rules and forbidden motifs.
2. **Episode visual strategy:** inferred topic/niche, central promise, viewer question, evidence mode, emotional arc, hook archetype, interaction model, visual-mode palette, motion grammar, local UI kit, repetition limits and episode-specific forbidden shortcuts.
3. **Beat execution:** every shot binds an exact narration word/frame interval, states what the viewer must understand or feel at that instant, and declares how the proposed visual directly supports that beat.

Changing the pasted URL must invalidate and recompile layers 2 and 3. It must not mutate the saved channel constitution. A profile may provide defaults and limits, but it cannot force one illustration treatment across unrelated Professor Yashrah topics.

### Semantic alignment contract

- Split narration into claim-sized and rhetoric-sized beats rather than assigning one broad scene to a long ASR span.
- Persist the exact overlapping narration excerpt on every shot.
- Require a semantic-link field explaining the visible relationship to the spoken beat: literal demonstration, causal mechanism, contrast, evidence, analogy, emotional identification, interactive instruction or transition.
- Reject generic mood imagery when the narration makes a concrete promise, comparison, instruction, historical claim or challenge.
- Reject a shot when its rationale merely repeats topic words without showing the actual meaning. Attractive but irrelevant imagery is a failure.
- Run an independent editorial-critic pass in a separate bounded Gemini chat before Flow. The critic receives the narration excerpt, episode strategy and proposed shot, then returns accept/reject plus a concrete correction. Deterministic gates still own frame coverage, entities, references, typography and safety.
- Preserve rejected plans and critic findings as training evidence for the next retry; never send a rejected plan to Flow.

### Hook composer

The opening 8–15 seconds is a dedicated sequence, not an ordinary first shot. It must earn attention with three to five purposeful micro-beats selected from the episode strategy:

- immediate recognition of the viewer's problem;
- a surprising contradiction, test, consequence or unanswered question;
- a visible promise of what the viewer will experience or learn;
- a clean handoff into the first section.

The hook may use locally rendered UI panels, kinetic Arabic type, masks, counters, progress indicators, comparison states, focus reticles, timelines or diagram fragments. It must remain semantically tied to the opening narration, legible on mobile and visually compatible with the selected channel. It cannot use empty glitch effects, random dashboards, fake scientific telemetry or a generic montage.

### Visual-mode palette and pacing

Each episode strategy selects a limited but varied palette of modes, for example:

- human-context illustration;
- object or evidence insert;
- locally rendered UI/demo;
- diagram or mechanism;
- archival/source treatment when provenance permits it;
- spatial metaphor with an explicit semantic link;
- interactive challenge canvas;
- typographic transition or chapter card.

The planner budgets these modes across narration beats, caps repeated composition families and prevents consecutive shots from communicating the same idea in the same way. Shot duration follows information density and rhetoric: hook beats may cut quickly, explanations breathe, and playable exercises remain stable.

### Local motion and UI composition

Selective local animation expands beyond Ken Burns and static labels. The compositor should support reusable, deterministic primitives such as masked reveals, focus sweeps, progress rings, number-tile entrances, comparison sliders, trace paths, counters, cards, callouts and state transitions. Motion must explain, guide attention or create anticipation.

For the Schulte exercise, keep the grid playable while improving presentation: a branded challenge frame, restrained tile reveal, center-fixation pulse, clear rule card, animated 40-second target indicator and decisive start transition. Animation must stop or settle before it interferes with the actual search task.

### Editorial quality gates

Before Flow, calculate and persist:

- narration coverage by claim-sized beat;
- hook completeness and first-15-second visual change cadence;
- semantic critic acceptance for every shot;
- visual-mode and composition repetition;
- local-UI opportunity coverage for instructions, comparisons, mechanisms and challenges;
- unsupported-claim and fabricated-evidence checks;
- continuity/reference requirements.

Technical validity cannot promote a pilot. A preview needs explicit user ratings for semantic match, hook strength, visual attractiveness, progression, continuity, readability and motion. Any failed dimension keeps the pilot rejected and invalidates master approval.

### Professor rejected-baseline evidence

The 2026-09-26 review rated the pilot at roughly 30% improvement. The implementation solved consistency, generated-text leakage, exact references and local Schulte rendering, but failed editorial direction:

- The first doorway-amnesia image matched the opening question about foggy thinking.
- Visible keys and glasses then remained onscreen while narration promised a special sequence of mental exercises.
- A quiet kitchen image accompanied the stronger promise of restoring mental sharpness.
- Window, armchair and shelf scenes weakened narration about rejecting boring solutions, enjoying the exercises and challenging intelligence.
- Another doorway image accompanied “ready to surprise yourself?”, losing the strongest pre-challenge hook opportunity.
- The Schulte grid was readable and contextually correct, yet its surrounding presentation lacked a premium challenge frame, staged rule reveal and satisfying start transition.

The next planner must pass exact-beat semantics and hook composition before spending any Flow generation quota.

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
