# Repository instructions

These instructions are the shared project contract loaded by supported coding agents. User instructions take priority. The nearest applicable AGENTS.md adds local rules; platform adapters import this file and do not establish a competing authority.

## Session startup
- Read docs/sessions/HANDOFF.md when present. Check docs/error-solving/understood-errors.md before investigating a recorded failure.
- Read this root contract and every applicable parent/child AGENTS.md before editing. A task brief narrows authorized work but cannot weaken these contracts.
- Treat tracker status, handoff notes and delegated claims as mutable; refresh them against current files and receipts before relying on them.

## Shared work contract
- Before introducing an approval gate, identify the action and strongest safe option. Do not repeat a decision already authorized in this session; honor platform-enforced disclosure, destructive-action and irreversible-publication gates.
- Keep QMD coverage and freshness current before relying on retrieval. Re-index changed documents and refresh affected embeddings; use lexical retrieval and report pending vectors when embedding work is incomplete.
- Preserve user data, production evidence, rejected candidates, recovery journals and resumable state. Archive or delete only after classifying the target, checking references and demonstrating recovery.
- Keep provider, browser, GUI, publication and quota actions inside the current task's explicit scope and bounded grant. Prior usage, a fresh session or a test does not create authorization.
- Human rejection overrides model output and prior approval. Preserve rejected evidence and require fresh review of a revised candidate before publication.
- Preserve exact raw receipts and hashes. Keep secrets and private content out of committed fixtures and external research.
- Follow existing domain ownership and interfaces. Repair incrementally for safer feature changes; do not adopt new workspace tooling or replace a subsystem without evidence and an accepted task.
- Use GLOSSARY.md for shared terms, docs/adr/ for durable architecture decisions and docs/sessions/HANDOFF.md for current session state. Keep platform adapters free of duplicate domain guidance.

## Work routing
- Follow docs/agents/workflows.md for feature, debugging and release routes, tool routing, proportional research/delegation and configured checks.
- For any Python source, test or root facade change that enters src/youtube_automation/, first read src/youtube_automation/AGENTS.md and the nearest child contract. This also applies when editing a root facade.
- docs/agents/AGENTS.md owns engineering-guidance consumers and navigation to issue tracking, triage labels and domain vocabulary. The issue-tracker.md, triage-labels.md and domain.md documents own their named procedures and terms.
- Use only task-bound project skills from tasks/BRANCH_TASK_SKILLS.md; skill source and archive provenance live in skill-lock.json.

## DOX
- AGENTS.md files are binding contracts for their subtrees. Each parent states the purpose and ownership of direct children; child files index their own direct contracts.
- Before editing, read the root and every applicable parent/child contract. The closest contract owns local details and cannot weaken root DOX.
- Preserve byte archives with a bounded fixed-path binary read and exclusive-create helper. Verify source and archive hashes before copying and again after copying. Retain failed archive evidence.
- Never reconstruct exact preimages from compressed or text-normalized output. For mixed line endings, patch bounded byte spans, verify untouched bytes and verify reconstruction against the original bytes.
- After meaningful changes, update the closest contract when purpose, ownership, structure, behavior, workflow, constraints or child indexes change. Update affected parents and children, remove stale claims, refresh indexes and read every final file back from disk.
- Confirm each referenced output exists. A child Verification section lists only existing checks; if no check exists, leave that section empty instead of inventing one.
- Report which documents were intentionally left unchanged and why. Name each verification command and its observed result; never claim an unrun check.
- Keep HANDOFF concise with Done, Next, Failures & Fixes and enough resume context to prevent repeated work.

## Child DOX Index
- docs/agents/AGENTS.md: engineering guidance consumers, tracker references, triage labels and shared domain-document navigation.
- channels/AGENTS.md: saved channel identities and pilot voice/visual policy.
- tasks/AGENTS.md: implementation plans, acceptance contracts and verification evidence; tasks/BRANCH_COMPLETION_MASTER.md owns branch execution status and resume order.
- src/youtube_automation/AGENTS.md: Python package ownership and runtime contracts; its production child owns adaptive production specifics.
- tests/AGENTS.md: test isolation, regression evidence and fixture ownership.
- tools/AGENTS.md: maintained QA utilities, manual diagnostics, import safety and verification.
- .codex/AGENTS.md: branch-local Codex guidance and configuration validation.
- docs/error-solving/AGENTS.md: case records, known error patterns, and bounded diagnostic procedures.
- docs/sessions/ has no child AGENTS.md; root owns session and delegation-record workflows.

## Project navigation
- For product, architecture, workflow, vocabulary or resume questions, use [docs/README.md](docs/README.md), the documentation map owned by the root contract.
- docs/agents/workflows.md routes feature, debug and release work.
- docs/sessions/ owns handoffs, bounded delegation briefs, returns and learning receipts under the root session contract.
- docs/product/architecture-renewal-plan.md and architecture-renewal-spec.md record incremental renewal direction and accepted scope. The settled study policies live in their linked decisions; planning does not grant live REA execution.
- Managed Pane workspaces require runpane doctor --json before dispatch; see docs/tools/pane.md.
- The applicable production policy lives in src/youtube_automation/production/AGENTS.md.
