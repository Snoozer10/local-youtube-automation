# Claude Code delegation: finish adaptive branch production

**Status:** prepared for the user to paste into Claude Code. This delegation has not started. Current repository facts below were independently recorded by Codex at the preparation checkpoint; Claude must verify mutable state before acting.

## Copy/paste start prompt

```text
Complete the remaining authorized production work on the current adaptive multi-channel branch, following docs/sessions/CLAUDE_FULL_COMPLETION_DELEGATION_20261009.md. Start by reading docs/sessions/HANDOFF.md, docs/short-term-plan/CONTINUITY.md, this delegation, docs/sessions/CLAUDE_TO_CODEX_RETURN_20261009.md, tasks/adaptive-branch-closeout.md, tasks/claude-feedback-coverage.md, docs/sessions/CLAUDE_INTERIM_RESULT.md, docs/sessions/CLAUDE_INTERIM_DELEGATION.md, and the current H10 critic result. Verify each claim against current files, hashes and receipts. Work only on production completion and its documentation. Preserve the accepted Professor preview exactly. Do not perform any Git/GitHub mutation: Codex owns staging, commits, push, PR creation/update/comments, formal PR and CodeRabbit reviews, merge, and history/worktree changes. Use only the listed provider caps; stop on first failure. Keep a durable receipt and update HANDOFF/CONTINUITY before stopping. Return results in docs/sessions/CLAUDE_TO_CODEX_RETURN_20261009.md even if you exhaust your available usage. Do not claim 100% completion while a production gate, approval, cap or receipt is still open.
```

## Mission and authority

- Finish remaining **production acceptance and local verification** for the existing branch `codex/adaptive-multi-channel-visual-engine`; do not broaden product scope.
- Current recorded HEAD: `41d02eba1fa17467ac8fdbfcbb6d445e5fd9f64b`. The branch is dirty and associated with draft PR #21. Recheck these values on start; preserve all existing user and delegate changes.
- User reserves **every Git/GitHub mutation** for Codex after returning: staging, commits, push, PR create/update/comments, formal PR review, CodeRabbit, merge, history rewriting, and worktree operations. Local `git status`, `git log`, `git diff`, and read-only review are allowed.
- You may edit production source, tests, data, and durable docs required by the existing closeout plan. Use current repository contracts and preserve compatibility. External upload and public release are not authorized. Guarded local `active_master.json` activation is part of production completion when current lineage, recipe, preview, human approval, and publication journal all validate. Do not transfer proposal-run approval to canonical activation.
- The user may return to Codex at any time; keep a resumable cursor and do not promise a reset date.
- Treat this brief as task scope, not blanket authorization for additional Gemini, TTS, Flow, browser, or other provider actions.

## Start and checkpoint discipline

1. Run `git status --short --branch` and `git log -5 --oneline`; record HEAD, dirty paths, and any running jobs before editing. Do not clean, reset, stash, or overwrite work.
2. Read the files listed in the start prompt, plus the applicable `AGENTS.md` files and `GEMINI.md`. Read only the relevant slices of long documents. Check whether the current QMD collection covers these docs and whether it is fresh before relying on it.
3. Verify every mutable claim below against the worktree and its receipt. A hash copied from this brief is a locator/check value, not a substitute for hashing the actual bytes.
4. Make a fresh exclusive attempt directory under `.runtime/claude_full_completion_20261009/` for each distinct attempt. Preserve failed outputs, command/stdout/stderr, inputs, timestamps, and exact result. Never overwrite an earlier attempt.
5. For any exact source preimage, use a bounded fixed-path **binary** reader and exclusive-create archive. Verify source hash before, archive hash, and source hash again after copying. Keep the helper and receipt with the attempt. Do not reconstruct preimages from chat, compressed output, diffs, or normalized text.
6. Before a long or live action, save a concise resume cursor in the return file and update `HANDOFF.md` and `CONTINUITY.md`. Keep these useful to a fresh Codex session: exact next command/action, evidence path, caps spent/remaining, blockers, and failures/fixes.

## Verified starting evidence to recheck

### Professor Yashrah

- The user accepted the exact 76.5-second preview at `.runtime/codex_allowance_20261008_45_to55/professor_r14/root_render_attempt_01/attempt1/preview.mp4`, SHA-256 `15ec1c7dfc01764665e84a5941c076fb8e3cc980b3e6b2e9874ea370f4b1b782`.
- The user recorded 4/5 for each of seven dimensions: narration match, hook, visual appeal, progression, continuity, readability, and motion. All proposed improvements are deferred to a future feature after this branch is merged. Keep that acceptance bound to this preview hash.
- Its approval is in `.runtime/codex_closeout_20261009_final20/professor_acceptance/proposal_run`; the evidence file is `.runtime/codex_closeout_20261009_final20/professor_acceptance/public_approval_receipt.json`, SHA-256 `f35862082e1fbef15b6d130f9b75540982a0066b4b274874adab5376281c49ac`. Do not transfer this proposal-run approval to canonical/master activation without the supported current-lineage procedure.
- A prior 1.5/5 rejection remains bound to its older preview hash. Do not transfer it to, or use it to revoke, the newly accepted preview.
- The preview is an excerpt, not the complete original episode used for G6. A historical wrapper exited 1 because manifest input metadata did not match actual render inputs; this does not prove the full runner passed.
- Canonical read-only source evidence is under `.runtime/codex_full_completion_20261007/professor_isolated_migration/rescue_04/run`. Recheck the current checklist before any migration or activation.
- The rescue run contains `full_episode_voice.wav` (7,348,878 bytes, SHA-256 `7a89334ef0c8023d0a0f464810c6df18887688be37631fd2f4f45e0af9a92fa0`) and a 76.52-second timeline. This is a pilot cut; its word-review binding says prepared, not reviewed. The saved pilot provenance files under `youtube_runs/adaptive-pilot-professor-yashrah/` and `youtube_runs/adaptive-pilot-professor-yashrah-local-narration/` identify published URL `https://www.youtube.com/watch?v=AvTeNM10wZQ`. This locates historical provenance; it does not prove the complete source or current raw-text lineage.
- G6 source investigation receipt: `.runtime/codex_claude_full_completion_20261009/g6_source_locator_receipt.json`. The user suggested `https://www.youtube.com/watch?v=So5zO7DL17I` tentatively; do not treat it as confirmed Schulte-source identity. YouTube watch/oEmbed fetches were throttled, so the live title is unverified. The checked Terrence Howard archive WAV does not match the import receipt's original-media hash and must not be adopted as the Professor full episode. The rescue raw-text hash also differs from the historical pilot source hash; determine whether this is documented curation or stale lineage before G6. Verify a complete source/script/audio relationship instead of inferring it from filenames or recorded hashes.

### Other pilots and scripts

- Soldier’s Sledger: the selected voice for new war-documentary narration is Charon. Existing published pilot narration stays unchanged. The old Pro refusal is closed.
- The active user-authorized cap is recorded in `.runtime/codex_full_completion_20261007/soldier_flash_action/execution_budget.json`: status `authorized_not_started`, two single-use submissions, zero sends, required observed model `3.8 Flash`, original then one refinement after local review, stop on first failure. Its `action_manifest.json`, `original_script_prompt.txt`, and `refinement_prompt.txt` are the active request/source packet. The historical alternative proposal in `soldier_script_action/fresh_flash_action_proposal.md` still says INACTIVE; use the fresh scope's actual budget, never the closed Pro budget or its counters.
- The execution budget still names stale PID 5832 for Profile 2. Before any send, preserve its exact preimage and perform a reviewed administrative rebind to the verified currently registered PID 108264/process-creation identity for the same `C:\\ChromeDebugProfile` / Profile 2. Preserve task identity, model, prompt hashes, and both zero-send counters; verify the resulting budget/manifest bytes and receipt. This is a preflight correction, not permission for another send. If the current guard/helper cannot rebind safely, stop without sending and return the blocker.
- The prepared prompt targets a 60–90-second Battle off Samar narration using the supplied research/factual checklist. Use only its source packet; do not browse for more claims, add another model/research request, or claim full source/PDF review. Perform local fact review between the two authorized requests.
- Event 9 used the local TTS 1/1 guard and went to Flash text chat. The user decided it remains spent as a failed attempt; no audio was produced and external TTS quota is unknown. Never reset or exempt it.
- H10’s corrected Arabic script is `youtube_runs/adaptive-h10-professor-dog-cues-phase2-20261005T080653Z-codex-cache-rebuild-20261007T094309Z/refined_script.txt` (recorded 1,796 bytes, 171 words, 3 paragraphs). The user-approved narrow copy corrections are already applied. Voice is Achird; there is no chapter WAV and no new TTS authorization.
- H10 tag extraction, the reviewed TTS-flow proposal’s local/dry-run checks, and the F8 stale-message/helper compatibility fix were reported completed; verify actual files and receipts rather than replaying old sends. The full original H10 plan critic is evidence, not approval.
- Snoozer Anime has a historical accepted 71.44-second master and eight assets. Validate the current recipe and four-cap checkpoint; do not restamp an approval onto copied or stale outputs.

### Software and browser evidence

- Latest recorded integrated software run: 1,279 unit tests passed in 167.29 seconds, Ruff passed, and scoped production mypy passed 20 files. The integrated receipt is `.runtime/codex_closeout_20261009_final20/integrated_gates/attempt_01/receipt.json`, SHA-256 `b24d95ce809c7ac8ad21c046206f8d913b186b0552f675199b357b65bc309e3a`; overall status failed solely because a database-hash isolation guard changed while Codex ran browser-lease checks concurrently. Treat full-suite database isolation as **inconclusive**, not passed.
- A serialized targeted follow-up passed 9 ledger/cleanup tests in 1.89 seconds and found the database unchanged: `.runtime/codex_closeout_20261009_final20/integrated_gates/attempt_02_targeted_isolation/receipt.json`, SHA-256 `69dda96daa20b27b940f88258bf19abbf73dc1b2136c2efe1f8aec5eb0ebe050`.
- Historical 1,049-test count is stale. Current unit command uses the pinned plugin `.runtime/claude_interim_20261006T083743Z/wave2/ledger_redirect_plugin.py` (SHA-256 `ea3cfd55fbb81c50b4023468fcef8b7851bccd16f57b0d959b9b19182775efc4`) and the repo virtualenv. See current test contract in `tests/AGENTS.md` and the closeout plan. Serialize DB isolation checks against all production/browser lease activity.
- Full-repository mypy previously reported 188 legacy import diagnostics. Use the scoped production command prescribed by the current plan and state its scope accurately; do not claim whole-repository typing success.
- Pipeline Chrome PID 108264, `C:/ChromeDebugProfile`, Profile 2, port 9222 was user-designated and registered. One 5-second CDP connection succeeded with zero Gemini tabs; live model/UI readiness remains unknown. Before an authorized live stage, revalidate exact process creation time, profile, listener, ownership registry, and lease. Never kill a process based only on port or path. Browser MCP extension installation does not prove an MCP backend is connected.
- Keep the mixed CRLF/LF bytes of `src/youtube_automation/audio/tts_generator.py` intact unless an explicitly reviewed code change requires otherwise. Do not normalize line endings.

## Execution plan: parallelize safely, keep live work serial

Use Claude’s native subagent feature if available (`Agent`, or `Task` on an older CLI). If unavailable, work serially. Probe capabilities once. Do not install MCPs, skills, plugins, or tools just to match Codex. Use no more than **two bounded offline workers** plus the main Claude session. Give every worker one named file or evidence question, a time/output bound, and a return format. Workers may not commit, push, or mutate the shared browser/provider state. Reuse completed workers for independent reviews when useful.

| Work package | Owner | Acceptance |
| --- | --- | --- |
| Verify current branch/status, hashes, receipt lineage, prior Claude feedback and checklist dependencies | Main; one read-only worker may audit feedback | Evidence index distinguishes verified, stale, failed, unknown, and not attempted |
| Offline repairs and deterministic source/test changes from the existing plan | Main assigns disjoint file ownership to at most two workers | Small scoped diffs, focused tests, no overlapping writes; main inspects every diff |
| Soldier original request, local factual review, one refinement | Main only; no concurrent browser actor | Exact two-request cap; receipt after each; stop on first failure |
| Live browser UI work that has separate authorization | Main only, serialized under owned profile and shared lease | Fresh readiness evidence before entry; exact scope/counter; stop on first unexpected UI state |
| Independent review, final acceptance matrix and handoff | Main; workers may review assigned offline diffs | Findings cite file/line or receipt and classify severity; all unresolved blockers retained |

Do not run tests that use shared SQLite state concurrently with browser/device leases or production work. Do not run a second instance when a shell job may still be active. If a wrapper times out, inspect its owned process/session and receipt before restarting it.

### Stage 1 — reconstruct the live cursor

- Read `tasks/adaptive-branch-closeout.md`, `tasks/claude-feedback-coverage.md`, the Claude interim result and delegation, `.runtime/claude_interim_20261006T083743Z/reviews/phase2_review.md`, relevant WIP reviews in that scope, and `docs/sessions/ANTIGRAVITY_H10_PLAN_CRITIC_RESULT.md`.
- Read only the Stage 3 cursor and evidence links needed to continue. Do not rerun historical `claude_verify.py` against later authorized changes or treat its old baseline as the new expected tree.
- Verify any claimed prior fix from source and tests. In particular, distinguish a prepared TTS redesign from a live-verified selector, a script correction from a generated WAV, a user approval from canonical activation, and a successful unit suite from a clean isolation guard.
- Use `tasks/claude-feedback-coverage.md` for the A1–A8/B1–B8 dispositions, but treat each disposition as a lead, not proof. Verify its cited source, patch, or receipt. Attribute Claude’s interim mistakes separately from Codex-side corrections/review errors; the latest database-isolation failure came from Codex running lease checks concurrently and is not a Claude defect.
- Convert findings into a gate matrix: pilot, gate, exact input recipe/hash, evidence, status, next action, authorization/cap, and blocker.

### Stage 2 — close offline defects and feedback

- Follow the existing closeout and coverage plans; do not invent parallel acceptance definitions. Resolve each open feedback item with a narrow change, a focused meaningful check, and a receipt.
- Keep the tag/parser, ledger, and TTS changes scoped to their proven defect. Preserve compatibility required by existing callers. Use existing replay cases and tests before proposing a new costly live run.
- Before using Python isolated mode (`-I`), verify import origins. `-I` ignores `PYTHONPATH`; when the root compatibility facades are required, make both repository root and `src` available through a verified supported mechanism. Do not start a browser lease or spend a request before syntax/import/preflight succeeds.
- Keep shell payloads below 8 KiB. Put larger scripts in a durable, reviewable helper file; compile and inspect it before any side effect.
- For hashes, calculate from verified bytes or a machine-generated receipt. Never copy a 64-character digest by hand where a source-of-truth can calculate it; require exactly 64 hexadecimal SHA-256 characters. Do not equate a Git diff with byte equality.

### Stage 3 — complete bounded authorized script work

- Verify the live active budget is still `authorized_not_started`, both one-use slots show zero attempts, both prompt files match their machine-recomputed SHA-256 values, observed model is exactly `3.8 Flash`, and the signed-in account/profile matches the approved scope. Resolve the budget’s stale PID 5832 through a reviewed, preimage-archived administrative rebind to verified PID108264 for the same Profile2/user-data directory, preserving task identity, hashes, and counters. If rebind or any preflight fails, stop without a send; the authorization does not permit bypassing guards.
- Before request one, archive the exact active budget, manifest, prompt bytes, and source/factual packet; record model/account/profile identity, current ownership/lease, and slot counter. Submit only the prepared original draft, then save its raw response and completion receipt immediately.
- Check duration/word count, sourced claims, chronology, names, and factual checklist locally. Do not spend request two if the draft is unusable or the first action fails.
- Submit at most one refinement, using the active `refinement_prompt.txt` only after the original response passes local factual review. Save the exact response and compare changes against the factual checklist. No extra follow-up, regenerate, provider switch, TTS, or Flow action is included.
- Record provider quota as unknown unless the service explicitly reports it. Codex’s usage API and its separate preparation allowance say nothing about Claude or Gemini quotas.

### Stage 4 — pilot gates, full episode and restart reuse

- Close the existing pilot matrix: G4 requires three contrasting 60–90-second pilots; G5 requires human review; Professor H9 requires all seven current preview scores; H10 requires a substantially different second Professor topic. Verify each exact criterion in the owning plan before marking the gate passed.
- Apply current production ceilings: no more than 400 images, lower duration budgets for short episodes, and twenty images for the current Professor pilot. Reuse accepted current assets before proposing any new Flow request. Do not add visual-quality features to this branch; the user deferred those improvements until after merge.
- For each required pilot stage, verify recipe-matched chapter WAVs, polish/stitch, canonical transcript/timing, current plan and stills with real English/Arabic OCR, current preview and human approval, thumbnail receipt and OCR, guarded local master activation, and restart reuse when prescribed by the stage contract. Do not skip a required stage to claim production completion.
- For any episode requiring TTS or Flow, identify the exact action, prerequisites, estimated request count, safe stop point, and strongest option before asking the user for a separate bounded grant. Existing grants cover only the two Soldier Gemini requests and nothing else. Never treat the Codex 1/1 TTS event as permission to send.
- For G6, the user selected the complete original Professor episode behind the accepted Schulte preview. Start from the saved published-source URL and source-investigation receipt above; establish the complete script and audio, provenance, word-level match, and exact hashes before execution. Ask the user for the full source path or identity only if bounded investigation cannot resolve it. The accepted 76.5-second excerpt does not satisfy full-original-episode acceptance.
- Verify restart reuse from the durable stage receipts and output hashes; do not rely on in-memory state, copied approvals, or an old recipe. Preserve rejected outputs and prove current activation points at the exact accepted bytes.
- If a required source, provider cap, voice, human acceptance, or live UI state is unavailable, finish independent offline work, mark the gate blocked/unknown, and hand it off. No substitute artifact or inferred approval.

### Stage 5 — final verification and Codex return

- Run the current full unit suite once after final code changes, with the pinned redirect plugin and required interpreter/environment. On PowerShell set `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPATH` to the repository root, `src`, and `.runtime/claude_interim_20261006T083743Z/wave2`; verify imported root facades and packages resolve inside this repository. Do not add `-I`, which ignores `PYTHONPATH`. Run `venv\Scripts\python.exe -B -m pytest -p no:cacheprovider -p ledger_redirect_plugin tests/unit -q --tb=short --import-mode=importlib --strict-markers --maxfail=1`; the pinned plugin SHA-256 is `ea3cfd55fbb81c50b4023468fcef8b7851bccd16f57b0d959b9b19182775efc4`. Run `venv\Scripts\python.exe -B -m ruff check .` and scoped `venv\Scripts\python.exe -B -m mypy src/youtube_automation/production --follow-imports=silent`. Report exact scopes and receipts; this does not establish full-repository mypy success. Run exercise/drill gates only where their owning contracts require them.
- Keep all database isolation verification serialized and capture before/after logical state plus required binary hashes. If the suite fails, obey the two-strike brake and preserve the failed result; do not launch a third blind attempt.
- Review the full local diff against the initial dirty state, test for accidental generated files, verify changed byte-sensitive files, review receipts and user approval/hash bindings, and update the task checklist only with evidence-backed status.
- Refresh QMD for modified durable documents if that capability is available. Verify indexed content. If not available, record exact files and mark indexing/embeddings pending; do not claim freshness. Do not create an unnecessary collection.
- Update `HANDOFF.md`, `CONTINUITY.md`, this return record, and the existing feedback coverage plan. Clearly state that Codex owns the remaining Git/GitHub closeout.

## Tools and delegation fallbacks

- At start, make one small capability check for Claude subagents, relevant MCP tools, browser connection, and available verification commands. Use a tool only if it is actually callable and returns current evidence.
- If lean-ctx or QMD is unavailable, use existing PowerShell, `rg`, Python, and repo scripts for bounded reads/search and hash receipts where the active harness permits them. If a hook denies the fallback, report the tool-routing blocker; do not disable hooks or rewrite configuration. Keep QMD work pending when unavailable.
- If Serena, LCO, or Codebase Memory is missing, use lexical search and direct source reads. Do not install a substitute solely for this task.
- Use an existing browser-control tool only when connected to the verified pipeline-owned profile and after confirming the stage is authorized. If none is available, stop at the live gate and report what the user must do or what tool reconnect is required.
- Never treat the user-installed Browser MCP extension as proof of a connected MCP server. Do not create another Chrome process, restart the pipeline browser, switch accounts, or rotate profiles unless a separately authorized procedure specifically requires it.

## Quota, stop conditions, and claims

- Claude Code documents `/usage` as showing session cost, plan usage limits, and activity stats; availability/details depend on the active account and provider. `/cost` and `/stats` are aliases; `/context` shows context-window use. This is not Codex’s usage API. Capture the actual display or exact limit message; never infer an unseen allowance, percentage, or reset date.
- Reserve enough remaining time/context to save receipts, update handoff, and return the current cursor. If a plan usage-limit screen offers automatic continuation, cancel/disable that wait, checkpoint, and stop; do not resume after reset without the user. A quota reset or Codex return does not authorize provider requests.
- The explicit Soldier Flash grant is exactly two requests and zero spent at the recorded checkpoint. Recheck the live counter before use. Stop on first failure and never retry.
- No new TTS, Flow, other model planning, upload, public release, or merge is authorized here. Obtain a separate bounded user grant for any such provider action.
- Two-strike brake: after the same command/build/test failure twice with no new hypothesis, stop and report. Never blindly retry. Never claim a UI send occurred without its request/response evidence, a test suite passed without its receipt, or production is complete while any required gate is open.

## Definition of production-complete

Production is 100% complete only when every required production gate passes with current evidence and every required human review is accepted. A user-owned blocker means production remains **INCOMPLETE**, though the branch has a valid resumable handoff. “Ready for Codex resume” means evidence and cursor are ready for another session; it does not mean production-complete. Production-complete does not mean externally uploaded or publicly released, committed, PR-approved, or merged.

## Claude Code references

- [CLI reference](https://code.claude.com/docs/en/cli-usage) and [commands](https://code.claude.com/docs/en/commands): session continuation, supported command behavior, and usage status.
- [Subagents](https://code.claude.com/docs/en/sub-agents): native workers, parallel research, context isolation, and usage sharing.
- [Common workflows](https://code.claude.com/docs/en/common-workflows): plan, test, delegate, and resume workflows.
- [Interactive mode](https://code.claude.com/docs/en/interactive-mode): usage-limit waits and automatic continuation controls.

