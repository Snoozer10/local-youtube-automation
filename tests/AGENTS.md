# Purpose
Offline verification, regression evidence and deterministic test fixtures.

## Ownership
- This tree owns unit and integration tests, local stubs and sanitized test-only evidence.

## Local Contracts
- tests/conftest.py autouse fixture isolated_shared_resource_paths redirects shared state to per-test tmp_path files adaptive.sqlite3 and owned_browsers.json; session hooks fingerprint persistent production resources and fail if tests change them. Keep these guards enabled.
- Diagnostic CLI tests create failures.jsonl under tmp_path and exercise failure_record.load_last_record(path, max_bytes=...) with dictionary records containing stage, utc, layer, kind, exception, message, frame, sends_spent, known_issue and evidence. Cover bounded read-only output, malformed-latest fail-closed behavior and credential redaction. Preserve raw JSONL evidence byte-for-byte; parser tests use isolated copies with before/after hashes.
- Browser-target regression tests simulate transport/schema failures and require zero attach on unknown probe state. PCM fixtures assert exact chunk/frame offsets and invalid extent/padding/format/alignment boundaries. Audacity readiness tests mock all native APIs/helper processes; assert zero pipe opens/commands for unsafe startup, identity drift and capture errors. Mock success proves offline contracts only, not live Windows/Audacity readiness.
- One-Help supervisor tests use fake clocks/processes/jobs and mocked kernel/DLL/msvcrt APIs only. Assert timeout hard-stop, stable phase deadlines, parent lease release, zero-send aborts, exact single Help frame and conservative before-send uncertainty; both pipe server PIDs must match.
- Unit tests must not invoke live Gemini, Flow, browser transport or paid/network services. Use fakes, preserved sanitized fixtures and public production seams.
- Actual browser/CDP/socket/process-inspection cases belong in integration tests marked `live_browser`. Default collection skips them before fixtures; `--run-live-browser` enables their execution and requires separate current bounded authorization. Offline fakes use synthetic facts and termination sentinels. The synthetic opt-in regression must never select actual live cases.
- Tests that acquire shared browser/process leases must redirect lease state to a test-local temporary database, assert release on success and failure, and leave the persistent production lease unchanged.
- UI-guard regressions must cover all matching overlays, including a hidden first match followed by a visible one, bounded probe failures, confirmed absence, and visible-overlay text-selector misses.
- Preserve historical regression evidence that remains linked from a durable replay contract. Do not replace a failing fixture merely to make a changed implementation pass.
- Audacity pipe mocks must accept only the exact valid platform frame (Windows CRLF+NUL, POSIX LF), preserve malformed suffixes/frames as rejection cases, and require the explicit completion status plus terminal blank boundary; do not use prefix-tolerant matching.
- fixtures/semantic_graphic_copy_v1.json records sanitized GRAPHIC_COPY_LOSS evidence; the compiler-to-ASS regression must preserve primary and secondary copy for kinetic_type and focus_sweep.
- fixtures/flow_reference_alias_v1.json replays FLOW_REFERENCE_ALIAS_MISSING: a resized CDN preview rejects until its exact editor alias is proved; another character still rejects. Keep raw browser/provider receipts in the ignored run.
- fixtures/flow_rotating_preview_v1.json replays FLOW_REFERENCE_TOKEN_ROTATION: different ASB tokens preserve identical preview pixels. Only an immutable canonical-bound preview permits exact-pixel matching; tampering, path escape and mismatched exposed identity reject.
- Test behavior and externally meaningful failure boundaries rather than incidental private call order.
- Word-cue regressions cover delayed fixation/time limits, each countdown word, shot-boundary continuity, immutable grid values, stale-plan rejection and partial prefixes that have not reached later spoken instructions. Preserve span-only historical replay without inventing word timing. Real FFmpeg pixel fixtures supply intended overlays explicitly; never depend on automatically injected unspoken cues.

- Regress the adaptive_production.py proofs CLI and public proof API against existing assets and the current render recipe. Assert a single encoder lease covers validation, current-input/ffprobe checks, native hardware probes and FFmpeg sampling; decoded PNG format and exact dimensions gate manifest creation. Verify unique diagnostic-only outputs and no production stage/job-key or publication-file changes; allow only encoder lease job/event changes in the runtime database. Proofs must not satisfy visual-audit, preview-approval, master or publication gates.

- Unit-test isolation is the default. Saved-artifact receipt audits are separate explicit CLI operations; tests use `tmp_path` copies and assert source receipts and canonical production state remain unchanged.

- Direct production publication touches the shared ledger. Before any stage, guard, or publication call, every Python child that can publish must set `ledger.resource_database` to its own test-local temporary database. Spawned children do not inherit parent monkeypatches. Keep the preconnection guard enabled so an installation-database attempt is rejected with caller context before SQLite opens it; do not clean up or restore the installation database as part of a test.

- Prompt resource regressions verify recursive template byte parity and isolated installed-layout load/render/turn/fragment behavior. Default-configuration tests compare canonical dialect ratios and exact lexicon order/rendered value, ignore missing/decoy prefix configuration, and preserve explicit path/channel/model precedence. Frozen verification checks actual wheel/sdist resources, metadata and offline target installation.

## Work Guidance
- Keep fixtures minimal, deterministic and free of secrets or machine-specific session identifiers.
- When production behavior intentionally changes, add or update the smallest regression that proves the new contract and retain separate cases for distinct failure boundaries.

## Verification
- Run focused changed tests first, then `python -m pytest tests/unit -q --tb=short` before closeout.

## Child DOX Index
- `fixtures/semantic_failures/AGENTS.md`: sanitized adaptive semantic-failure corpus and evidence ledger.

- One-Help image-inspection tests use local BMP fixtures and mocked native APIs; no live app launch. Outside-path fixtures must exist so strict missing-file rejection does not mask containment assertions. Supervisor tests mock the killable receipt sealer; fail-fast leaves later cases unverified.

- Preserve exact native diagnostic programs before execution. Log controller/Popen/payload identities before hazardous calls; pass the process object to WindowsJobContainment.assign and query the specific owned Job handle. Use a bounded acknowledgment gate, not a sleep, to order assignment before payload work. Retain failed evidence and native error codes; mocked success and dependency-path presence do not prove native containment or environment parity.

- Launcher diagnostics compare the owned native executable image to the pinned target,not solely sys.executable metadata. Record external command watchdog outcome separately from controller phase duration and staged cleanup;preserve partial proof without declaring a failed check passed. Current source revisions require current focused-suite evidence.


### Return audit regression boundaries
- Verify production Audacity pipe server PID mismatch fails before any command; mocks establish the contract only, not a native incident.
- Verify quota-bound adaptive Run dispatches once and treats false or ambiguous acknowledgment as uncertain without retrying the click.
- Keep an optional temperature-setting miss non-blocking while required model and voice checks remain fail-closed.
