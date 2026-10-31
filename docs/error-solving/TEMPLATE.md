# Case ID: [ERR-XXX-title-slug]
**Version 1.0.0** · [Responsible Layer] · Status: [resolved|mitigated|active|hypothesis] · [YYYY-MM-DD]

---

## AI READING INSTRUCTION

Read `[BUG]` and `[SPEC]` blocks for authoritative failure modes, verified fixes, and prevention guards.
Read `[?]` blocks for active hypotheses and diagnostic bounds — treat with lower confidence.
Read `[NOTE]` blocks only if previous failed attempts or historical context are needed.

---

## Overview

**[SPEC]**
- **Title**: [Clear title describing the failure condition]
- **Responsible Layer**: [os.filesystem | video.qsv | audio.pipe | speech.manifest | browser.gemini | pipeline.gate]
- **Status**: [resolved | mitigated | active | hypothesis]
- **Date Recorded**: [YYYY-MM-DD]
- **Affected Components**: [Module, CLI command, or pipeline stage]

---

## 1. Verified Facts

**[BUG] [Short description of failure mode]**
- **Symptom**: [Exact observed exception, error code, or terminal failure output]
- **Cause**: [Confirmed root cause at hardware, driver, protocol, or AST level]
- **Fix**: [Deterministic code change or configuration remedy applied]
- [Concrete conditions required to trigger the failure]
- [Verified environmental or operating system facts]

---

## 2. Hypotheses

**[?]**
- [Working diagnostic hypothesis explaining why the failure occurs]
- [Confidence level: high | medium | low]

---

## 3. Attempts and Outcomes

**[NOTE]**
- **Attempt 1**: [Description of what was tried]
  - *Outcome*: [Observed result, whether it succeeded or failed]
- **Attempt 2**: [Description of follow-up approach if applicable]
  - *Outcome*: [Observed result]

---

## 4. Remaining Gaps & False-Positive Boundaries

**[?]**
- **Boundaries**: [When this error pattern does NOT apply; explicit false-positive criteria]
- **Gaps**: [Unverified assumptions or unresolved environmental limitations]

---

## 5. Verified Prevention Check

**[SPEC]**
- **Rule / Guard**: [Specific coding rule, pre-check, or configuration invariant]
- **Verification**: [Test file or runnable assert verifying the prevention guard]

---

## 6. Evidence Links

**[SPEC]**
- **Raw Receipts / Logs**: [Relative link to .runtime or log evidence]
- **Source Code**: [Relative link to affected source module]
- **Regression Test**: [Relative link to unit or integration test]
- **Legacy Anchor**: [Relative link to ../understood-errors.md#<slug>]
- **Origin Incident**: [Relative link to ../../incidents/INCIDENT_<slug>.md if applicable]
