# AGY08 — Snoozer Anime historical recipe audit

Task ID: `AGY08-SNOOZER-CURRENT-RECIPE-AUDIT`  
Prepared: 2026-10-13 · Deadline: 2026-10-14  
Scope: C5 evidence map and current gap matrix only. Do not render or refresh.

## Review subject and pins

C5 is the Snoozer Anime pilot in `tasks/BRANCH_COMPLETION_MASTER.md` (current recipe, historical plan/assets/preview, and exact approval binding remain to be validated). The 2026-10-09 session record identifies the candidate run as `youtube_runs/adaptive-pilot-snoozer-hokkaido`, with historical master/preview SHA-256 `1d83099386a4b8e91c060ec768f742e4298c2297a9fe7ba7ebb8c4853e042b65`. Its source is Hokkaido Gals, not Professor G6 and not the separate intake folder `youtube_runs/adaptive-pilot-snoozer-anime`.

Codex’s read-only preliminary pins (recheck before use; Codex will independently verify):
- Source-lineage manifest `youtube_runs/adaptive-pilot-snoozer-hokkaido/pilot_source.json`: SHA-256 `ca66b92b3d420455e82f047809790078ebd54efa4f840cf078a1d6c1e5da29b0`. It binds channel `snoozer-anime`, owner media SHA `5e936f578d2da5a37fd424b2b423399b7cdcc81fca076a2f897304e7e2084608`, and source PDF SHA `ea76bc3b19a8110bcdca360a5673d2c727573b0ec3ab7a608174c231512e33ce`.
- Output binding `active_master.json`: SHA-256 `87d8fc7888180ef3015798d95c79caff594ebb57f9ba064752279bb1f19ce407`; preview binding `adaptive_preview.json`: `d1246dc717bcf708f0cad78732ad1cc855ab33b58fc28a07b30a94153c624362`; historical approval `editorial_approval.json`: `d1a43472ea5f368465a1923d10a2d1a82493f2b3cfed22c7128899d98c580976`. Each is in the candidate run directory above.

## Audit and acceptance

Read `GEMINI.md`, `channels/AGENTS.md`, the current Snoozer profile, the C5/C6 master entries, and relevant session records first. Confirm the pins and episode identity. Build a matrix with each current recipe gate, its current source contract/version and hash, the exact historical evidence/path/hash, and status `satisfied`, `gap`, or `unknown`. Distinguish evidence that the old artifact existed from evidence that it satisfies today’s recipe. The 2026-10-09 session’s renderer/plan versions are historical; read current contracts and record their versions rather than copying stale numbers. Identify the exact current input/recipe manifest used for comparison and its SHA-256. If the pins do not resolve unambiguously to C5, stop and report the mismatch.

Report only the current gap matrix and the evidence map. Do not generate images, replan, rerender, approve, activate, or infer acceptance. C6 remains conditional on a blocking gap and requires separate authorization.

## Run limits and return

- Offline/read-only: no browser, network, provider, download, Flow, renderer, Audacity, project runner, or tests.
- Fresh scratch only: `.runtime/antigravity_offline_queue_20261013/AGY08_attempt01/`. Store notes and receipts there.
- Freeze and record helper SHA before use; save stdout/stderr; close payloads before hashing outputs and writing a manifest. Seal with a companion hash that excludes itself.
- One bounded pass; stop on first input drift, scope drift, or unexpected side effect. Use a bounded coordinator team with non-overlapping work and independent verification; make no installs or configuration changes.
- Return the report and end marker inside scratch with hashes after the final write. Do not modify shared master/checklists, promote evidence, or claim C5/C6 closure.

Codex verified the four JSON file hashes and actual historical preview bytes at queue preflight;see INPUT_VERIFICATION.json,SNOOZER_INPUT_PINS.json and SNOOZER_PREVIEW_PIN.json in .runtime/antigravity_offline_queue_20261013/. Preview path: "youtube_runs/adaptive-pilot-snoozer-hokkaido/adaptive_renders/d2fb906223532746e8ae50326b7d67d342c31b1f730e5abfcf6221cd6f2c8b45/preview-1d83099386a4b8e91c060ec768f742e4298c2297a9fe7ba7ebb8c4853e042b65.mp4". Recorded owner media/PDF hashes inside pilot_source.json remain lineage declarations until their actual files are rechecked. Historical renderer version3 and manifest approval fields do not prove current-engine acceptance;compare current source contracts and keep unsupported/re-render-required gaps OPEN without rendering.

## Binding execution controls (Codex review)

ROOT = "C:/Users/Snoozer/Downloads/Antigravity/Youtube Automation 2/buckup/Version 4 before deepseek implementation plan/image_generation". Quote every path containing spaces. Read root AGENTS.md, GEMINI.md and owning contracts, but this user-approved scratch-only scope overrides generic project-document closeout writes: propose changes in RETURN.md; do not edit HANDOFF, AGENTS or master. Run helpers with PYTHONDONTWRITEBYTECODE=1 and Python -B;redirect temporary files,logs,caches and every artifact to this lane's scratch. If an API cannot respect that boundary,stop instead of bypassing its resource guard.

Lead Antigravity as coordinator; use bounded native implementer and independent verifier subagents with disjoint scratch ownership. Verify byte/hash identities first; record original and derived data separately. No launch of Audacity or browser,no provider sends/web fetches/model downloads,rendering,source changes,Git mutations,graph updates or installs. Native Antigravity reasoning is authorized; task-initiated external calls are not. Use only existing tools and local assets. Input drift or attempted scope violation stops the lane immediately.

Freeze helper source/version and SHA-256 BEFORE use; verify that hash immediately before each invocation. Capture exact argv,cwd,exit status and unmodified stdout/stderr into raw log files under scratch. Do not treat compressed tool text as executable code,raw file bytes or successful evidence.

Close every output and log before sealing. Hash closed payload files into OUTPUT_MANIFEST.json; then close RETURN.md and the manifest. Finally write SEAL.json containing hashes of those two closed files (exclude SEAL.json itself from its hash domain). Freeze all sealed files; no edits after seal. If a change is necessary,create a new additive correction and new seal retaining originals. Missing evidence is UNVERIFIABLE/PARTIAL,never a pass. Return the complete scratch path,counts,per-task findings,remaining blockers and seal;Codex independently reviews before any promotion or checkbox closure.

Create this lane attempt directory exclusively; if it exists,stop and report rather than overwrite or silently choose another attempt. All task statuses remain staged claims until Codex review.

Required scratch payloads: INPUTS.json, historical_inventory.json, current_contract_pins.json, gap_matrix.csv (requirement,current code/doc evidence,historical evidence,status,needed action), audit.md and TASK_STATUS.json. Compare plan/schema,recipe,asset/preview hashes,narration/timing,render-version,cues/text,continuity,motion and exact approval bindings. Read-only decode/ffprobe and bounded scratch frame extraction are permitted;no rendering/composition or promotion.
