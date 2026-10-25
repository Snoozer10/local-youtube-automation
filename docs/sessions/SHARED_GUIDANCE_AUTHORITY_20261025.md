# Shared Guidance Authority

Status: IMPLEMENTED; final branch validation pending. Ticket: [Establish shared guidance authority and route feature, debug, and release work](https://github.com/Snoozer10/local-youtube-automation/issues/36). Do not close the ticket from this record alone.

## Result and ownership
Root AGENTS.md is the shared contract and route map. GEMINI.md preserves project/version metadata and imports it; CLAUDE.md imports it. Platform adapters no longer own domain rules. Source runtime controls live in src/youtube_automation/AGENTS.md, which indexes the existing production child. docs/agents/workflows.md owns feature, debug and release procedures, proportional research/delegation, and verification. Existing tracker, triage and domain consumers retain their owners.

The coherent switch also reconciles authority in tasks/AGENTS.md and docs/agents/domain.md, the full source typing gate in production guidance, CONTRIBUTING and the PR template, browser ownership in README, and the supported filtergraph spelling in CONTEXT. The old multi-channel reference has a superseded notice and its original body remains byte-exact. A nonexistent skill-archive child was removed from the root index; no skills were moved or discovery claims made.

## Routing demonstration
| Work | Observed route | Responsible boundary and checks |
| --- | --- | --- |
| Feature: profile setting through root facade | Root -> workflows Feature -> source contract -> production contract; tests contract for tests | Existing public production.briefs.ensure_brief and tests/unit/test_production_briefs.py. Future reference-study/activation behavior remains ticket43/44 work. |
| Debug: owned Audacity timeout | Root -> workflows Debugging -> source ownership/IPC contract -> understood-errors | audio/audacity_client.py and core/process_supervisor.py; existing Audacity protocol/readiness/supervisor fixtures. Preserve recovery data, exact PID/Job identity and Windows CRLF+NUL framing; no live retry grant. |
| Release: Windows distributable | Root -> workflows Release -> tools contract and .github/workflows/release.yml | Full mypy --strict src/, relevant tests/lint, wheel/sdist build and separate Windows ZIP content requirements. Build is not publication authorization. |

A supported fresh Codex CLI 0.160.0 session quoted the root paragraph before tools. Its detailed read exercise exhausted its read budget and timed out at360seconds; that incomplete result is retained. A second routing-only session, capped at180seconds, exited0 and correctly selected all three entry routes from startup instructions without being supplied their answers. Detailed on-disk routes and27 targets were independently read back by the coordinator. Claude/Gemini runtime loading and skill discovery were not exercised; documented imports are not represented as those proofs.

## Verification and limits
| Check | Observed result |
| --- | --- |
| venv Python -m mypy --strict src/ | PASS at checked baseline; no scope exclusions added |
| venv Python -m ruff check . | PASS |
| venv Python -m build --no-isolation --sdist --wheel | PASS; no Windows ZIP publication performed |
| venv Python -m pytest tests/ -q --tb=short -x | FAIL:335passed,9skipped,1failed; stopped at test_compile_video_cli.py::TestMainExecutionAndDelegation::test_main_compiles_successfully_with_fake_runner (expected a recorded -vf command) |
| git -c core.whitespace=cr-at-eol,-blank-at-eof diff --cached --check | PASS; preserves existing mixed/CRLF bytes and the historical reference body EOF |
| Routing/index readback |27required targets exist;14changed guidance files pinned |

Antigravity owns compilation spec23/tickets24-30. Compiler/facade files changed during this session and the compilation CLI test changed after the247-input verification freeze. These checks therefore do not establish a passing final shared application tree. No compilation source/test fixes were made by this task, and the full suite was not blindly rerun. Preserve the failure until the compilation owner reconciles it, then verify the frozen branch before closing36.

## Independent review
Separate Standards and Spec reviewers found archive-integrity, FFmpeg routing, delegation-pinning, PID wording and Windows supervision omissions in the first draft. Corrections restored those controls. Readback found two further omissions: Antigravity learning records and worker/sealer initialization ordering. They were restored with bounded byte insertions; coordinator final readback confirmed them. This is bounded review, not a zero-defect claim.

## Evidence and disposition
Local ignored evidence: .runtime/guidance_authority_20261025T061500Z/. It is unavailable in a fresh clone. BASELINE.json, migration-receipt.md, REVIEW_INITIAL.json, FINAL_READBACK.json, SOURCE_FREEZE.json and gate JSON/logs preserve exact preimages, hashes, reconstruction receipts, failed commands and current readback. The first verifier had an eager missing-prompt read before invoking mypy; run_gate_v2 fixed initialization and preserved the failed helper. A gh incompatible-flags read was corrected; a capture-policy rejection was resolved with raw subprocess-byte capture rather than changing tool settings.

Root/child DOX indexes were reconciled. Existing source behavior, provider caps, editorial gates, recovery data and compilation ownership remain outside these documentation edits. The pre-existing CONTEXT compilation definition and unrelated line endings are deliberately left unstaged; its index contains only this ticket’s filtergraph correction. Historical root-relative links remain in the preserved body with correct navigation added above it. Prior product plan/spec/interview, glossary and Pane documentation are included as prerequisite documentation so the new routes exist in the commit; their dated findings remain historical. Unrelated dirty source, state, skill locks, error records, deletions and session records are excluded.

QMD remains intentionally unchanged under prior user direction; its625document index had264pending embeddings and current disk bytes were used. The existing post-commit hook would start QMD/graph updates, so this documentation commit uses a per-invocation empty hooks directory; no hook or global Git setting is edited. No active pre-commit hook was present.

## Research receipt
2026-10-25 UTC: current local Codex CLI0.160.0 help and applicable contracts were inspected first. Official [Claude memory/import documentation](https://code.claude.com/docs/en/memory), [Gemini memory import processor](https://geminicli.com/docs/reference/memport/) and [Codex AGENTS discovery documentation](https://developers.openai.com/codex/guides/agents-md) support explicit shared-file loading. The selected Windows-friendly import approach avoids changing global settings. Local checks establish only the runtime and routes actually exercised above.

## Resume
Commit the scoped documentation on master; leave36open while final branch verification is pending. Do not start its dependent tickets automatically. Compilation23/24-30 remains Antigravity-owned. The Channel DNA decision map is resolved; application implementation and meaningful live Windows REA qualification remain future work. Professor D1 remains deferred; no new production provider/live grant exists.
