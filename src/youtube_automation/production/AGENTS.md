# Purpose
Adaptive channel policy, editorial planning, validated assets and local production state.

## Ownership
- This package owns versioned production contracts and adaptive execution; browser selectors remain in browser/visuals adapters.

## Local Contracts
- Explicit channel selection; topic analysis cannot override stable identity.
- Episode analysis must declare whether claims are factual, fictional or mixed. `evidence_needs` is only for external verification of real-world claims; fictional identities, relationships, settings and visible states belong in `continuity_anchors`. Figurative language cannot silently become literal staging.
- Canonical speech timing is read-only input. Editorial shots reference it.
- Shot plan version 2 persists a deterministic editorial policy resolved from the selected channel and analyzed script. Enforce its shot-duration ceiling, framing diversity, selective-motion cap and contiguous canonical coverage before generation.
- Every shot declares visible stable entity IDs. A recurring entity in one scene must reuse or reference an established asset; add/remove/reframe/replace semantics determine compatible entity-set changes. Declared entities must appear in the visible description, and obvious literalized figurative transformations block the plan.
- Persist source/profile/recipe hashes. Missing or unverified inputs block publication.
- Preserve accepted artifacts; retries cannot silently select unrelated references. If Flow no longer mounts a provider card after reload, restore only the receipt-bound content-addressed accepted PNG and verify exactly one attached prompt ingredient.
- Device entrypoints acquire the installation-wide browser, Audacity or encoder lease. Short artifact activation runs under publication_guard; never hold its SQLite transaction during browser calls, DSP or encoding.
- Accepted image copies and final videos use content-derived names. active_master.json is the only adaptive master activation pointer.
- Approval requires a current preview and binds its plan, assets, audio and render recipe.
- Adaptive narration derives chapters from validated refined writing and requires an exact script/channel/voice recipe plus matching WAV digest for completed chapters.
- `source-audio` imports a bounded excerpt of owner-provided local media, preserves the caption-derived script exactly, and publishes a verified WAV and source receipt. Profiles with a null synthesis voice and imported runs cannot enter adaptive TTS. Source media remains external; its hash, excerpt bounds and accepted WAV hash are recorded. Transcription still creates the canonical timeline before shots.
- Adaptive voice, Audacity and stitching require an explicit run. Voice generation stops once any polished or stitched audio exists. Audacity requires a known preset and bounded, explicitly successful pipe commands; stalled or failed effects cannot publish output. Audacity and stitching require all validated voice chapters, gapless physical offsets and complete polished WAVs. Stitching verifies saved polished hashes without changing the manifest. The voice-generation manifest remains a raw-synthesis checkpoint. Audio chapter, manifest and master activation use short publication fences.
- Adaptive thumbnails derive prompts from the selected brief, accept landscape images only after full-frame OCR passes, and require a content-bound receipt to skip generation. Missing OCR blocks acceptance. Their browser work uses the shared resource lease.
- Adaptive image and thumbnail OCR request English and Arabic recognition. Missing language data or OCR failure blocks technical acceptance.
- Render aspect crops must use the selected focal point and accepted source dimensions before zoom/pan. Non-hold motion needs visible safe travel; changing the camera recipe invalidates cached clips and approval.

## Work Guidance
- New adaptive execution is opt-in until reviewed pilots pass.
- Do not equate technical verification with editorial approval.

## Verification
- Run tests/unit/test_production_*.py and full unit suite before closeout.
- Run `python -m mypy src/youtube_automation/production --follow-imports=silent` and workspace `ruff check .`.
- Real FFmpeg regressions verify decoded static frames, frame budgets, overlay encoding, cache integrity and approval gates. Live visual quality remains a separate pilot gate.

## Child DOX Index
- None.
