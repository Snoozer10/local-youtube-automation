# Engineering workflows

These routes apply the shared root contract. The nearest task and domain contracts define the acceptance criteria.

## Shared routing and tools
- Read docs/sessions/HANDOFF.md, the applicable AGENTS.md chain and any relevant understood-error record before work.
- Use only skills bound by tasks/BRANCH_TASK_SKILLS.md. skill-lock.json owns canonical sources, hashes and archive mappings. Do not add a per-task skill toggle or change global settings to simulate scoped discovery; project-TOML parsing alone does not prove exclusion and existing skill catalogs may not hot-reload.
- Route shell commands through ctx_shell. Use lean-ctx reads/search for source context; start multi-hop code questions with ctx_compose. Use Serena for symbols and surgical edits, and Codebase-Memory only for an already-indexed project.
- Use QMD for Markdown only after checking coverage and freshness. Re-index changed files and refresh affected embeddings before semantic retrieval. If embeddings are pending, use lexical retrieval and report that state. After one QMD device-loss/reranking failure, switch to lexical BM25 through ctx_shell; do not repeat the failed route.
- Use Headroom for one bounded exact retrieval. If exact retrieval fails once, read the needed local bytes directly; do not retry the same failed recovery path.
- Research when uncertainty, changing external facts, unfamiliar failures or significant decisions affect the approach. Prefer current primary sources and stop when they support an actionable choice. Record topic, date, links, relevant version and local verification. Keep private code, secrets and sensitive logs out of queries.
- Delegate when independent work adds value; handle straightforward local work directly. Every task capsule names Task ID, Worker, Scope & Ownership, Goal & Acceptance, and Guidance. Set exact ownership, bounded caps, stop conditions and a return receipt. Workers do not update shared status or commit/push. Record model/effort only when the harness exposes it; never infer quota from usage estimates.
- Before publishing a delegation brief, compare every immutable input pin with actual file bytes and reread the final brief. Preserve incorrect draft preimages. Scratch-only Antigravity work closes inside its authorized scratch; it does not edit shared HANDOFF, DOX or master records. Freeze helpers before use, preserve raw logs, and seal outputs only after every file is closed. The coordinator integrates and reviews returned work; the user starts/stops Antigravity.
- When the user delegates production completion to Claude Code, the task-specific brief and return record in the `docs/sessions/` folder permitted production and document work. The active brief controls its named exceptions to older blanket restrictions; it does not grant provider actions. Git/GitHub mutations, formal PR review and merge remain with Codex when explicitly requested.
- **Approved Architecture-Renewal Campaign Exception (2026-10-27)**: For the architecture-renewal campaign under parent #31, Antigravity's Project Orchestrator is the designated campaign integration owner per the approved campaign charter and permission matrix. The scratch-only Antigravity clause and Codex-reserved Git/PR/merge clause above are superseded for this campaign. The Project Orchestrator is authorized to coordinate workers, manage the campaign workspace, integrate diffs, execute campaign commits, push owned campaign branches, open/update PRs, merge scoped campaign PRs upon passing CI and independent audit, and update GitHub issue progress. Codex availability is not a routine milestone gate. Unrelated delegations outside this campaign continue to follow the default worker-only and Codex-reserved rules. All underlying safety guards (production DB isolation, credentials, browser profiles, provider caps, and editorial controls) remain strictly binding.
- Browser, provider, GUI and publication actions require a current explicit scope and bounded grant. Track provider caps separately from model/tool usage. A reset, fixture or delegated claim does not grant additional use. Near a cap, reserve closeout and prepare the agreed fresh-session handoff and controlled delegation instructions unless the user chooses another delegate.

- Before requesting a live browser, provider or GUI grant, complete offline candidate checks and a final review; offline readiness does not grant live execution.
- After every Antigravity return, distinguish verified evidence from unverified claims. Record evidence-bound delegate/reviewer mistakes and successful controls in `docs/sessions/ANTIGRAVITY_DELEGATION_LEARNINGS.md`; carry the prevention and a check into the next brief using `docs/sessions/ANTIGRAVITY_DELEGATION_TEMPLATE.md`.
- For Claude usage, report only a supported fresh usage display. Do not assume a Codex quota API is available or estimate token costs.

## Feature work
1. Read the relevant task, source contract and nearest child contract before editing. For source, tests or a root facade that enters src/youtube_automation/, load src/youtube_automation/AGENTS.md.
2. Identify the public behavior seam, owning module, affected callers and preserved state. Keep changes within the accepted scope.
3. Delegate only independent work that can reduce risk or elapsed time; otherwise work directly. Include explicit ownership, acceptance checks and evidence requirements.
4. Run the focused test/check while iterating. Run required repository gates once against the frozen tree; documentation-only edits do not need broad suites unless a required check is affected.

## Debugging
1. Establish the exact symptom, environment, versions and last known-good state. Check docs/error-solving/understood-errors.md before investigating a recorded failure.
2. Reproduce at the narrowest responsible boundary. Preserve raw receipts, hashes, checkpoints and recoverable state; separate observed facts from hypotheses.
3. Search current primary documentation or maintainer sources when external/version-sensitive facts, unfamiliar behavior or significant choices require it. Preserve a short research receipt and verify locally.
4. Change the responsible layer, then rerun the focused reproducer and relevant regression case. Bound retries and stop after the same command fails twice without a new hypothesis.
5. For production failures, add a minimal sanitized replay case and replay accepted cases before another costly live run. A failed investigation does not grant live browser, provider, GUI or external action.
6. If an owned GUI failure remains unexplained, capture and inspect the current owned window before another attempt. Bind evidence to PID/time where available, preserve dialogs and recovery data, and treat visual diagnosis as a hypothesis until retested.

## Release work
1. Read the current release task and .github/workflows/release.yml.
2. Keep pyproject.toml, GEMINI version metadata and CHANGELOG.md aligned. Verify the Windows portable ZIP contains src/youtube_automation/, all root prompts/ files and saved channels/*.json; wheel resources follow their own package-data requirements. Exclude operational state, credentials, generated media and caches from the portable ZIP.
3. Use the repository's configured build and release checks. A local build is not publication authorization.

## Verification references
- Full source typing gate: venv/Scripts/python.exe -m mypy --strict src/. pyproject.toml configures Python 3.10 and strict mode; preserve discovery and checking scope.
- Final tests: venv/Scripts/python.exe -m pytest tests/ -q --tb=short -x. Run focused affected tests first.
- Package build check: venv/Scripts/python.exe -m build --no-isolation --sdist --wheel.
- Exercise checks are documented in run.bat and owned by tools/AGENTS.md.
