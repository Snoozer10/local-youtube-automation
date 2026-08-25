# 4 — DISCARDED APPROACHES AND FAILURES

## Rejected Code Fixes

| Considered | Why rejected | What shipped instead |
|---|---|---|
| Static `time.sleep()` waits after prompt send to "let Gemini finish" | Nondeterministic: fast Flash turns over-wait (2× slowdown across 16 turns); slow Pro turns still get truncated. Violates the repo's established text-stability doctrine | Existing `wait_for_gemini_response` stability polling + `get_last_response`; zero truncation observed in 16/16 turns |
| Raising `connect_over_cdp` timeout to 60 s instead of retrying | A single wedged boot would stall the supervisor for a minute with no signal; masks systemic boot failure as slowness | 3× retry @15 s with backoff — fails loud on the third miss |
| Making the rubric path a config key (`RUBRIC_PATH` in `.env`) | Over-parameterization for a file whose location is structural, not environmental; one more knob to drift | Hard convention `docs/audit_rubric.md` + legacy-root fallback |
| Parsing model replies with a single strict `<p id>` contract and failing the run otherwise | Two of two remediation turns ignored the wrapper — strict-only parsing had a 100% observed failure rate | Tagged parser → ordered-block fallback → loud dump-to-evidence on double-miss |
| Whole-script regeneration pass after audit FAIL | 16 healthy paragraphs re-rolled = high blast radius for judge noise; round-1 already proved edits can regress untouched strengths (terms colloquialized while fixing cadence) | Targeted paragraph splice by index, deterministic term restoration outside the model entirely |

## Failed Prompt Formats

1. **"Return ONLY revised paragraphs wrapped in `<p id="N">` tags"** (round 1): model returned plain blank-line-separated prose. Worked only when the chat already had the tagged example *and* a prior format miss to correct against (round-1 second attempt complied).
2. **Mixed directive granularity**: round-1 prompt mixed micro-edits (`...` insertion) with macro-rewrites (restructure openings). The model over-applied the Amiya voice onto locked technical vocabulary — the exact regression the rubric then flagged. Fixed by splitting concerns: mechanical fixes deterministic in code, creative work isolated per paragraph with NON-NEGOTIABLE locks up top.
3. **Trusting the auditor**: treating each new FAIL set as ground truth caused goalpost-chasing (audit #2 flagged tashkeel that a regex proved correct, and miscounted the script). Audits must be evidence-adjudicated, not obeyed.

## Lessons Learned & Pipeline Hardening Guidelines

1. **Checkpoint-first architecture paid for itself**: seven process kills mid-run produced zero lost turns. Keep every long phase resumable at sub-task granularity.
2. **Two readiness probes without coupling = race**. Any future CDP consumer should reuse the retry wrapper pattern (DM-1) rather than trusting `ensure_chrome_debug_session`'s HTTP probe as a websocket guarantee.
3. **Graceful degradation must be loud**: DM-2 hid a broken quality gate behind `return True`. Silent-skip branches should print a supervisor-scannable sentinel (e.g. `[AUDIT][SKIPPED]`) so log sweeps catch them.
4. **LLM judges need anchoring**: require the auditor to quote the offending sentence + paragraph id for each finding; findings without citations are auto-downgraded. Otherwise variance drives infinite remediation loops.
5. **Deterministic beats generative for mechanical edits**: harakat-tolerant term restoration fixed in code what a model pass had broken. Audit rubric violations should be triaged into "code-fixable" vs "model-fixable" before prompting.
6. **Sandboxed supervision shape**: unbuffered `-u` + file redirect + short killable windows + checkpoint resume is a viable substitute for true background processes when the harness forbids them.
7. **Remediation budget discipline**: cap content-iteration rounds (here: 2) and stop when judge feedback stops citing specifics — further turns trade verified quality for unverifiable churn.

## Evidence Artifacts

```
.docs/refine_script/evidence/
├── refine_run.log            # full live execution log, all 7 windows + crash trace
├── _remediation_raw.txt      # round-1 model reply (plain-text drift specimen)
└── _remediation_raw2.txt     # round-2 model reply (ordered-blocks case)
```
