# Antigravity Delegation Brief

Reusable template only. This document grants no active authorization. Fill every placeholder and attach this brief to one bounded task before starting an external session. See [ANTIGRAVITY_DELEGATION_LEARNINGS.md](ANTIGRAVITY_DELEGATION_LEARNINGS.md).

## Task and boundaries

- Read current root `AGENTS.md`, `GEMINI.md`, `HANDOFF.md` and the applicable child DOX chain before editing; read relevant `SKILL.md` instructions and use the tools actually available.
- Task ID / goal / acceptance: `[ID] / [measurable outcome] / [evidence required]`
- Baseline: `[branch + commit]`; dirty paths: `[exact list]`; input and plan SHA-256: `[hashes]`.
- Owned paths and allowed edits/actions: `[exact paths and operations]`.
- Protected bytes and pointers: `[paths, hashes, canonical refs]`; preserve pre-existing dirty work.
- Explicitly authorized external effects, if any: `[exact action and scope; otherwise none]`.
- Prohibited absent explicit authorization in this brief: activate canonical state, approve, publish, stage, commit, push, merge; send pipeline Gemini/Flow requests, operate browser profiles or call project cloud API/SDKs; install tools or change tool configuration. Antigravity's requested own subagents and existing local Skills/MCP remain part of the delegation.
- Each gate: exact command `[command]`; working directory `[absolute cwd]`; expected evidence `[path/schema/result]`; observed exit code and counts `[result]`.

## Baselines and evidence

- Before work, record exact file bytes and SHA-256 for protected inputs; use bounded fixed-path binary reads, exclusive-create archives, and verify source/archive hashes before and after copying. Preserve failed archive evidence. Preserve file encoding/newline style; run `git diff --check` and inspect unrelated line churn after edits.
- Byte-archive and hash the exact helper/runner used for each gate before execution. Do not edit an executed helper in place; if helper bytes change, bind prior results to the prior hash and rerun the gate against the new hash.
- Persist a preflight receipt with production fingerprint and audio, spend/quota, plan, state, manifest, and asset baselines before the first costly operation. Check and save the same values afterward, including on failure; an in-memory baseline lost on error leaves change/spend unverifiable.
- Parse actual proof schema and ordered shot coverage, including nested proof rows. Do not infer completion from row counts, summaries, tests, or self-scores.
- For visual review, inspect every ordered rendered shot at actual 480px display size for narration fit, progression, continuity, composition, and text readability. Inspect relevant motion frames and every relevant countdown/state transition. Label sampled artifacts as sampled evidence; report full playback separately. Human approval is a separate explicit decision and cannot be inferred from either.

## Antigravity execution

- Lead as coordinator, architect, and reviewer. Discover real available agents, Skills, and MCP tools first; report agent IDs, roles, owned paths, and results. Do not install or reconfigure tools.
- Use 2–3 bounded, non-overlapping packages only when their work is genuinely independent. Give each a self-contained capsule: `[Task ID]`, `[role]`, `[owned paths]`, `[goal and acceptance]`, `[allowed/prohibited actions]`, `[exact commands and cwd]`, `[expected evidence]`, and `[handoff format]`. Parallelize independent read-only exploration or separately owned implementation; keep dependent discovery/implementation sequential. Run tester/reviewer only after implementation is complete, then archivist after verification evidence is stable. Stop agents when their evidence is complete.
- The user starts and stops the external session. Do not claim an external action was run unless its receipt/evidence is returned.
- Use QMD for docs, LeanCTX for reads/shell, Serena for source edits, Codebase-Memory for targeted graph work, and LCO for targeted recall.
- Before any owned-browser operation, verify registry ownership, exact PID, dedicated profile, shared browser lease, and loopback listener. Inspect the exact launcher for lockfile cleanup and lease behavior; never launch from a stale registry record or invent an unverified bootstrap command.

- For a multi-step authorized task, the lead exclusive-creates the one requested result file before dispatch. Record UTC, status=in_progress, workspace/branch/HEAD/status, and initial evidence hashes there; append each return and final guards to that same file, including on failure or interruption. If the requested path exists, choose a UTC-suffixed unique path, then numeric suffix on collision; never overwrite. Create helper, attempt-receipt, or byte-preimage files only inside an explicitly authorized new .runtime phase directory listed in the brief. Keep the one requested result report as the only documentation work product; tool-owned caches/logs are incidental.
- Return exact result path and SHA-256, scope/status, actual agent/Skill/MCP capabilities and use, owned paths, before/after guards, evidence anchors, gate commands with cwd/exit/counts or NOT RUN, verified facts vs claims/unknowns, blockers, failures/deviations, and next step. Keep reports compact; no raw transcript/log/base64 dumps.

- Keep an append-only event trail in that same report: UTC, actual actor/agent ID and role, tool or exact command, cwd/environment, outcome and evidence hash. Distinguish delegate claims from lead verification and actual tool traces; separate local model inference from project-provider/network calls. Close with the full scoped before/after path inventory and explicit missing/changed paths. Without an exact pre-session byte baseline, do not claim global no-change.

## Live-send and draft controls

- Before a live step, verify the exact project interpreter, entrypoint, cwd, environment, and import path order; run the offline import check in the actual helper context. Preserve failures that occur before the CLI initializes receipts.
- Enforce caps at the real UI-send boundary across imported aliases, repair/retry/failover paths, and critic calls. Journal before each send and after success/failure. Distinguish invocation counters, paired request/result records, and independent UI-turn submission receipts. If caps cannot be proven offline, stop before sending.
- For a no-send UI rehearsal, preserve request-body bytes and content-encoding, decode compressed bodies explicitly, and fail closed when decoding is incomplete. The receipt must prove the exact selector steps and zero fill, keyboard, Run, or provider-send actions. Keep send-guard counters separate from provider/account quota evidence.
- Treat schema-valid model output as a draft. Check hooks and character/study continuity against the bound source and channel profile before translation, narration, or planning.
- After durable edits stabilize, verify QMD coverage, incrementally update changed files, refresh affected embeddings and retrieve current content. Add a narrowly scoped collection when necessary durable documents lack coverage; never indiscriminately index media or secrets. If vectors remain partial, use lexical retrieval and report it.

## Gates and return

- Validate runner arguments against the actual CLI choices, then run focused caller-compatibility tests before the full suite. Keep harness silence timeout distinct from test timeout. Run applicable gates with exact commands (`pytest -q --tb=short` for Python) and report command, exit code, and counts.
- On failure, preserve output, diagnose, make a bounded correction, and rerun the relevant gate. Never make a third blind retry; stop on repeated failure.
- Return changed files, before/after evidence hashes and fingerprints, gate results, and separate verified facts, delegate claims, pending checks, limitations, deviations, and next step. Update the learnings ledger after review; fill all placeholders before delegation.

## Current evidence controls

- Verify current semantic model/composer controls before typing; coordinate clicks and stale UI assumptions are insufficient. Match browser-plugin profile to the pipeline-owned browser before an actual action.
- Preserve raw provider output, classify only the known UI-envelope-cleaned model body, and require the requested substantive artifact before marking complete. A completed UI response can be a refusal. First-failure stop rules close all dependent slots; never repurpose an unused refinement as a retry.
- Keep runtime-helper regression tests beside their runtime package; committed production tests must not import ignored operational files.
- Compare digests produced by the same serializer/contract. A semantic timeline fingerprint is not a raw-file SHA256; verify field meaning before claiming drift.

## Offline artifact return controls — 2026-10-13

- The parent must close helper stdout/stderr before hashing final payloads. A sealer must not include its still-open output log;seal after parent capture closes and preserve any prior failed manifest.
- Record word-level ASR anchor versus interpolated timing provenance. Script-token equality and monotonic timestamps are technical checks,not evidence that every word was spoken.
- Map task IDs to the current master acceptance;retain partial gates. Keep historical exact-artifact approval separate from current recipe validity.
- Label planning candidates and proposed OCR/schema/PR metrics as unexecuted until bound receipts exist;check source endpoint,countdown holds and every referenced artifact.


## Expanded evidence and derivative controls

- Before editing a newly expanded target, verify a current byte archive or reuse a coordinator raw preimage only after its hash matches; never reconstruct exact source bytes from compressed or normalized displays.
- Give each test, verifier, or live attempt a unique exclusive receipt/log path; preserve failed attempts and corrected retries separately.
- Complete full-script claim coverage before owner approval. After wording changes, verify derivative cohesion against exact approved bytes; old audio/timing/plan evidence does not transfer. Keep narration/provider authorization separate from copy approval.
## Return controls refined after21 October audit

- Do not weaken a1x, ownership, identity or submission guard to make a live task proceed. Optional capability fallback is established before a send; uncertain post-reservation failure remains failed/uncertain until reconciled.
- Before running an offline suite, compare new test membership with the last frozen manifest and inspect unmarked socket/CDP/GUI code, even under tests/unit. Separate live tests and require explicit opt-in; marker selection alone is insufficient.
- Compare fingerprints through the same validated production model/serializer, not raw dictionaries. Preserve wrong reviewer comparisons with additive corrections.
- Return exact human decision provenance separately from an Owner string or generated scorecard. Never reset cumulative counters after rejected generations; preserve failed attempts and reconcile each retry.
- Final return must reconcile every active status surface and fresh QMD lexical readback; passing a subset, git diff --stat or an old build cannot close full branch review/QA/production.
