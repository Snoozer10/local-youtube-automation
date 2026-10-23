# AGYG: offline code-only Graphify candidate

Prepared 2026-10-12T07:07:27.746Z. Status QUEUED/NOT_STARTED. User chose AGY01–AGY04 first, then a separate fresh Antigravity session for Graphify. This is evidence preparation; no canonical graph promotion or integration is authorized. Gemini3.8Flash/high as selected.

ROOT = "C:/Users/Snoozer/Downloads/Antigravity/Youtube Automation 2/buckup/Version 4 before deepseek implementation plan/image_generation". Read ROOT/.agents/skills/graphify/SKILL.md and references/update.md. Explicit user constraints and this task scope override installation, provider, cleanup and integration suggestions in the skill.

## Task Capsule: AGYG

- Task ID: AGYG.
- Worker: bounded offline structural graph executor; no semantic-agent fanout.
- Scope & Ownership: read-only canonical Python sources and existing graphify-out; all new artifacts under a unique ROOT/.runtime/graphify_refresh_<UTC>/ directory.
- Goal & Acceptance: valid CODE_ONLY candidate with current canonical source provenance, reproducible manifest and original bytes preserved.
- Guidance: preserve originals; no project/provider/API calls, network changes, browser/Audacity, Git/GitHub mutation, installations/upgrades, watchers, hooks or guidance edits. No documentation/semantic extraction or API-key inspection/use. No replace/promotion of graphify-out.

## Frozen scope

Python .py files only under src/youtube_automation/, tools/, tests/ and the root directory (root files only). Do not follow symlinks. Exclude .runtime, __pycache__, .mypy_cache, .pytest_cache, .venv, venv, cache, logs, generated_images, youtube_runs and graphify-out directory names at every depth; skip private/secret material if encountered and report its exclusion without exposing it. Non-Python files and full documentation graph remain OUT_OF_SCOPE/PENDING.

At preparation,207 Python files matched this scope. Corpus binding SHA256: 52458af41841ab88576c1e22293d3ea640d7214345604357b6e42a0b8f376cc6. Reproduce by sorting relative paths lexicographically, reading raw bytes and constructing records with keys in order path,bytes,sha256; hash UTF8 JSON of the ordered array with no spaces/newline. Each file digest is raw SHA256. Python equivalent serializer: json.dumps(records, ensure_ascii=False, separators=(',', ':')). If scope or corpus digest differs, STOP_INPUT_DRIFT; do not silently adopt new inputs.

Original graph.json:5877338bytes SHA25680c895e9044bcc6a30b2c7af77b0a9fd15bc41335be6189bf195f32968e747c1. Additional protected graph files:

| Path | Bytes | SHA256 |
|---|---:|---|
| graphify-out/.graphify_analysis.json | 42697 | 3343b92998a0a9c247a47e4e52762825f1832c96111c956d2b99c40a04fbb33e |
| graphify-out/.graphify_incremental.json | 42352 | 361f55c881a3a7402441f2a68433450207b55c11a3eb6599c34c0d93e6b3c776 |
| graphify-out/.graphify_labels.json | 19773 | 0a8478dd75c98c43eb6c5ff76ff7fe40215c4d6bba0d126b2518d5c67cdccda8 |
| graphify-out/.graphify_learning.json | 7317 | 3662cf44d486d92dd98decc9efd39632df451c09b922db0638bce2dd70ca49e9 |
| graphify-out/.graphify_python | 74 | 516e374c08cfc0b94a8e7d588473bb8c120cc80bb2c8e5ceda3fc49153b70be8 |
| graphify-out/.graphify_root | 1 | cdb4ee2aea69cc6a83331bbe96dc2caa9a299d21329efb0336fc02a82e1839a8 |
| graphify-out/.vocab.txt | 8190 | 06a04413b399de7a87ea47067c3e898422f6cde2212f7f273214704624385008 |
| graphify-out/cost.json | 354 | a2c908dd4dbd1ec511724789d460e29df670e4bb011d37684433fd9cfa010605 |
| graphify-out/graph.json | 5877338 | 80c895e9044bcc6a30b2c7af77b0a9fd15bc41335be6189bf195f32968e747c1 |
| graphify-out/GRAPH_REPORT.md | 122341 | 5b207f9943b24808c9ce7f171e6b535b72831b2b46e84b811774f719d3f9ce29 |
| graphify-out/manifest.json | 98553 | 07445e466567ee31a7231ac380777ef3cb6bdafe671e512ac3b98054a14a9605 |

## Execution

1. Discover the existing installed interpreter/Graphify without invoking installers. Record versions/capabilities and exact proposed extraction commands. Missing tools or inability to isolate cache/output writes means STOP_ENVIRONMENT; preserve a blocked return.
2. Record input manifest and all original graph/source hashes; create bounded binary source copies exclusively under the new output folder. Verify source-before/source-after/copy hashes. Keep the same relative source tree and a mapping back to canonical ROOT paths. Freeze helper bytes before running them.
3. Run deterministic structural extraction only on the staged copies, with all outputs/caches confined there. Use the skill's AST path; never run a bare full pipeline/update against original ROOT. Do not assume an output flag exists; verify available APIs first. A new code-only graph is a partial candidate, not a fully updated mixed code/docs graph.
4. Validate actual output schema/JSON, unique node IDs, valid edge endpoints, resolvable canonical source locations and manifest coverage. Deleted/renamed current source entries must not persist as fresh facts. Check at least3 representative relationships against the source; label AST limitations honestly. Preserve stderr and failures.
5. Recompute corpus binding and every original graph file hash. Require all unchanged. Return command/cwd/environment, exit/counts, helper/output hashes and coverage limitations. No success solely from graph size or a delegate-written validator.

Embedded invariants: QSV_LOOKAHEAD=0/nv12 are preserved; no rendering is authorized. CDP loopback-only when separately authorized, but zero CDP access here. Atomic same-directory artifact writes; bounded watchdogs; no DNS/network/proxy changes, provider sends or Git mutation. Tool imports must not import project modules or touch production leases/state.

Max45minutes including waits. Stop on input drift, any UI/provider prompt, out-of-scope writes, unsafe access, quota message or two failed attempts total per gate; no third retry. Do not interpret costs/context as quota. Save PROGRESS.json after every phase and before long jobs: status,phase,UTC,input_manifest_sha256,completed_items,pending_items,next_command,helper/output hashes,failure_count. Existing attempts are never overwritten.

Allowed writes: only the new dated output folder, its staged inputs/cache/helpers/logs/atomic temporary siblings, PROGRESS.json and RETURN.md. No source/test/canonical docs/QMD/graphify-out modifications.

## Return

Create OUTPUT/RETURN.md with status DELIVERED_FOR_REVIEW/BLOCKED/INTERRUPTED, exact paths/hash list, actual checks, unchanged-byte guards, failed receipts and next action. Label CODE_ONLY; docs/semantic freshness remains pending. The user supplies that path to fresh Codex. No global graph freshness or branch completion claim.
