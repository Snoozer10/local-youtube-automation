# Purpose
Adaptive channel policy, editorial planning, validated assets and local production state.

## Ownership
- This package owns versioned production contracts and adaptive execution; browser selectors remain in browser/visuals adapters.

## Local Contracts
- Explicit channel selection; topic analysis cannot override stable identity.
- Episode analysis must declare whether claims are factual, fictional or mixed. `evidence_needs` is only for external verification of real-world claims; fictional identities, relationships, settings and visible states belong in `continuity_anchors`. Figurative language cannot silently become literal staging.
- Canonical speech timing is read-only input. Editorial shots reference it.
- Shot plan version 2 persists a deterministic editorial policy resolved from the selected channel and analyzed script. Enforce its shot-duration ceiling, framing diversity, selective-motion cap and contiguous canonical coverage before generation. Bound Gemini batches by narration time even when ASR spans are long. Save each validated window in a brief/timeline/window-bound partial checkpoint and resume it after transport failure; changed upstream recipes archive the checkpoint.
- Bind one Gemini chat to each planning window. Validation repair remains in that chat; transport retry reuses the exact prompt. Save atomic prompt-hash response receipts with model, window, stable `/app/<conversation-id>` URL and attempt states. Persist Ctrl+C as interrupted before re-raising it. On restart, recover stable late responses from submitted, interrupted or timed-out attempts before opening a new chat or resubmitting; never navigate the transient blank `/app` route as a receipt target.
- Every shot declares visible stable entity IDs. A recurring entity in one scene must reuse or reference an established asset; add/remove/reframe/replace semantics determine compatible entity-set changes. Declared entities must appear in the visible description, and obvious literalized figurative transformations block the plan.
- Version 2 channel profiles carry positive visual directives and exact forbidden motifs. Every new shot declares its narrative role; host-free channels reject presenters, and the deterministic forbidden-motif gate blocks named visual shortcuts before Flow.
- An `analyze` rerun may rebind only `version`, `visual_directives` and `forbidden_motifs` without another model call. It must verify existing writing/source narration, preserve their version-1-compatible narration fingerprint and canonical timeline, and invalidate the plan, asset receipts, reviews, previews, approvals, active master and thumbnail receipt. Any other profile change keeps full reanalysis/invalidation.
- Persist source/profile/recipe hashes. Missing or unverified inputs block publication.
- Preserve accepted artifacts; retries cannot silently select unrelated references. Asset publication writes a content-bound recovery journal before copying accepted bytes; recovery activates only a complete image whose hash, pixels, geometry, reference and current recipe all match. If Flow no longer mounts a provider card after reload, restore only the receipt-bound content-addressed accepted PNG and verify exactly one attached prompt ingredient.
- Browser, clipboard, Audacity and encoder entrypoints acquire their installation-wide lease in both adaptive and legacy paths. Browser and Audacity cleanup may terminate only a process whose exact PID is recorded as pipeline-owned. Short artifact activation runs under publication_guard; never hold its SQLite transaction during browser calls, DSP or encoding.
- Every adaptive CLI stage has a run-bound content recipe in the SQLite ledger. Unchanged success skips only after its output revalidates; missing/corrupt output reruns automatically. Existing output may be adopted without work only when it carries verifiable input lineage; unbound reports rerun after recipe changes. Changed inputs create a fresh attempt lineage; expired workers are reclaimed with a higher fence; three failed attempts open the circuit until an operator uses `--force-retry`. Stage and distinct device claims may nest, and every active claim must remain current before publication.
- A changed stage recipe journals and archives mutable downstream activations under `.adaptive_history/` before the new attempt. Recheck stage completion after archiving before adopting any remaining output. Restart reconciliation completes the archive first; content-addressed accepted images, immutable renders and reusable caches remain preserved.
- Accepted images and final videos use content-derived names. Asset, writing, source-audio, thumbnail, preview and master publication journals record complete activation intent before mutable files or pointers change. A retry may activate an orphan only after its input lineage and bytes revalidate. `active_master.json` is the only adaptive master activation pointer.
- Approval requires a current preview and binds its plan, assets, audio and render recipe.
- Adaptive narration derives chapters from validated refined writing and requires an exact script/channel/voice recipe plus matching WAV digest for completed chapters.
- `source-audio` imports a bounded excerpt of owner-provided local media, preserves the caption-derived script exactly, and publishes a verified WAV and source receipt. Profiles with a null synthesis voice and imported runs cannot enter adaptive TTS. Source media remains external; its hash, excerpt bounds and accepted WAV hash are recorded. Transcription still creates the canonical timeline before shots.
- Adaptive voice, Audacity and stitching require an explicit run. Voice generation stops once any polished or stitched audio exists. Audacity requires a known preset and bounded, explicitly successful pipe commands; stalled or failed effects cannot publish output. Audacity and stitching require all validated voice chapters, gapless physical offsets and complete polished WAVs. Stitching verifies saved polished hashes without changing the manifest. The voice-generation manifest remains a raw-synthesis checkpoint. Audio chapter, manifest and master activation use short publication fences.
- Adaptive thumbnails derive prompts from the selected brief, accept landscape images only after full-frame OCR passes, and require a content-bound receipt to skip generation. Missing OCR blocks acceptance. Their browser work uses the shared resource lease.
- Adaptive image and thumbnail OCR request English and Arabic recognition. Missing language data or OCR failure blocks technical acceptance.
- Render aspect crops must use the selected focal point and accepted source dimensions before zoom/pan. Non-hold motion needs visible safe travel; changing the camera recipe invalidates cached clips and approval.
- Exact grids, numerals, timers, labels, arrows and highlights are local overlay primitives. The `schulte_6x6` preset owns its deterministic 1–36 arrangement; Flow must not invent or alter those values.
- A Schulte shot is a human-free near-full-frame diagram with a local grid overlay. Do not place the exercise on a presenter-held board or an in-scene device.
- Use FFmpeg's supported `-/filter_complex` file input in both adaptive and legacy renderers; CI installs a release where the deprecated script option is absent.

## Work Guidance
- New adaptive execution is opt-in until reviewed pilots pass.
- Do not equate technical verification with editorial approval.

## Verification
- Run tests/unit/test_production_*.py and full unit suite before closeout.
- Run `python -m mypy src/youtube_automation/production --follow-imports=silent` and workspace `ruff check .`.
- Real FFmpeg regressions verify decoded static frames, frame budgets, overlay encoding, cache integrity and approval gates. Live visual quality remains a separate pilot gate.

## Child DOX Index
- None.
