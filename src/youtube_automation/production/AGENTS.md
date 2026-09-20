# Purpose
Adaptive channel policy, editorial planning, validated assets and local production state.

## Ownership
- This package owns versioned production contracts and adaptive execution; browser selectors remain in browser/visuals adapters.

## Local Contracts
- Explicit channel selection; topic analysis cannot override stable identity.
- Canonical speech timing is read-only input. Editorial shots reference it.
- Persist source/profile/recipe hashes. Missing or unverified inputs block publication.
- Preserve accepted artifacts; retries cannot silently select unrelated references.
- Device entrypoints acquire the installation-wide browser or encoder lease. Short artifact activation runs under publication_guard; never hold its SQLite transaction during browser calls or encoding.
- Accepted image copies and final videos use content-derived names. active_master.json is the only adaptive master activation pointer.
- Approval requires a current preview and binds its plan, assets, audio and render recipe.
- Adaptive narration derives chapters from validated refined writing and requires an exact script/channel/voice recipe plus matching WAV digest for completed chapters.
- Adaptive thumbnails derive prompts from the selected brief, accept landscape images only after full-frame OCR passes, and require a content-bound receipt to skip generation. Missing OCR blocks acceptance. Their browser work uses the shared resource lease.
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
