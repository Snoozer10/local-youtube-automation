# AGY07 — Professor G6 full-source offline review

Task ID: `AGY07-G6-SOURCE-REVIEW`  
Prepared: 2026-10-13 · Deadline: 2026-10-14  
Scope: D1 only; offline source listening, script coverage, and evidence report.

## Frozen subject

- Audio: `C:/Users/Snoozer/Downloads/YouTube Stuff/Channels/Explainintions categories/Content/18 Done/Do These 7 Brain Exercises NOW & Watch Your Focus Explode/full_episode_voice.wav`
- Expected SHA-256: `967f539225482772a7f4c7e9571023c293d33ad9871ba10114841e8fe858b203`; duration 509.418625 s.
- Script: same folder, `refined_script.txt`; expected SHA-256 `90134bd2ef690e50cec5c99ab323c06ab84ed25ee4b385a0f38bcf2307ec1488`; 1,019 Arabic words.
- Lineage locator: `.runtime/claude_full_completion_20261009/attempt_08_g6_source`; D1 is also defined in `tasks/BRANCH_COMPLETION_MASTER.md`. Codex will independently verify input identity before relying on this report.

## Work and acceptance

1. Confirm the two input hashes and duration read-only. Stop on any mismatch; do not substitute a pilot excerpt or another episode.
2. Listen locally from 0 through 509.418625 s at normal speed while following the frozen script. Keep a timestamped coverage log whose intervals cover the complete source once, without gaps or overlap.
3. Map each script beat to heard audio and record omissions, additions, ordering/timing issues, and any uncertain Arabic transcription. For every factual claim, record the claim, the local source evidence checked, and status `supported`, `unverified`, or `contradicted`. Cached ASR may help navigate only; it is not factual or editorial approval.
4. If complete playback or local claim verification is unavailable, mark the affected item OPEN and identify the uncovered time span or claim. Never infer full coverage from file metadata or partial playback.

Return a concise findings table, complete interval log, per-claim evidence/status, input hashes, and explicit limitations. Do not claim D1 complete unless all acceptance evidence exists. Do not alter the source, script, canonical master, task checkbox, or project files.

## Run limits and return

- Offline only: no browser, network, provider, download, renderer, Audacity, or project/test runner.
- Use only fresh scratch: `.runtime/antigravity_offline_queue_20261013/AGY07_attempt01/`. Keep all generated notes and receipts there.
- Freeze and record any helper SHA before use; capture stdout/stderr to files; close payloads before hashing outputs and writing a manifest. Seal the return with a companion hash that excludes itself.
- One bounded pass; stop on first unexpected input, playback failure, scope drift, or helper mismatch. Use a small bounded coordinator team with non-overlapping ownership and an independent verifier; no installs or tool configuration changes. Return a report inside scratch with an end marker and hashes after the last write.
- No branch/master checkbox closure or evidence promotion. Human review and Codex independent review remain separate.

Exact frozen script path: "C:/Users/Snoozer/Downloads/YouTube Stuff/Channels/Explainintions categories/Content/18 Done/Do These 7 Brain Exercises NOW & Watch Your Focus Explode/refined_script.txt". Use exact endpoint509.418625s;include pauses in contiguous beat intervals. If this harness cannot actually listen/review the whole audio,deliver script/ASR coverage as a labelled proxy and keep listening/factual acceptance OPEN. Offline facts without local independent support remain unverified;do not browse.

## Binding execution controls (Codex review)

ROOT = "C:/Users/Snoozer/Downloads/Antigravity/Youtube Automation 2/buckup/Version 4 before deepseek implementation plan/image_generation". Quote every path containing spaces. Read root AGENTS.md, GEMINI.md and owning contracts, but this user-approved scratch-only scope overrides generic project-document closeout writes: propose changes in RETURN.md; do not edit HANDOFF, AGENTS or master. Run helpers with PYTHONDONTWRITEBYTECODE=1 and Python -B;redirect temporary files,logs,caches and every artifact to this lane's scratch. If an API cannot respect that boundary,stop instead of bypassing its resource guard.

Lead Antigravity as coordinator; use bounded native implementer and independent verifier subagents with disjoint scratch ownership. Verify byte/hash identities first; record original and derived data separately. No launch of Audacity or browser,no provider sends/web fetches/model downloads,rendering,source changes,Git mutations,graph updates or installs. Native Antigravity reasoning is authorized; task-initiated external calls are not. Use only existing tools and local assets. Input drift or attempted scope violation stops the lane immediately.

Freeze helper source/version and SHA-256 BEFORE use; verify that hash immediately before each invocation. Capture exact argv,cwd,exit status and unmodified stdout/stderr into raw log files under scratch. Do not treat compressed tool text as executable code,raw file bytes or successful evidence.

Close every output and log before sealing. Hash closed payload files into OUTPUT_MANIFEST.json; then close RETURN.md and the manifest. Finally write SEAL.json containing hashes of those two closed files (exclude SEAL.json itself from its hash domain). Freeze all sealed files; no edits after seal. If a change is necessary,create a new additive correction and new seal retaining originals. Missing evidence is UNVERIFIABLE/PARTIAL,never a pass. Return the complete scratch path,counts,per-task findings,remaining blockers and seal;Codex independently reviews before any promotion or checkbox closure.

Create this lane attempt directory exclusively; if it exists,stop and report rather than overwrite or silently choose another attempt. All task statuses remain staged claims until Codex review.

Required scratch payloads: INPUTS.json, coverage.csv (start,end,beat,script-span,listen/proxy method,evidence,uncertainty), coverage_validation.json (first0,last509.418625,ordered contiguous intervals), facts_review.md and TASK_STATUS.json. Log every interval,including silence;provide script-word mapping and a concise full-story beat summary.
