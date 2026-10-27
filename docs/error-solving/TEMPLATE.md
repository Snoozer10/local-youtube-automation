# Case ID: [ERR-XXX-title-slug]

## Overview
- **Title**: [Clear title describing the failure condition]
- **Responsible Layer**: [e.g. video.qsv | audio.pipe | browser.gemini | speech.manifest | pipeline.gate | os.filesystem]
- **Status**: [resolved | mitigated | active | hypothesis]
- **Date Recorded**: [YYYY-MM-DD]
- **Affected Components**: [Module, CLI command, or pipeline stage]

## 1. Verified Facts
- [Exact observed exception, error code, or terminal failure output]
- [Concrete conditions required to trigger the failure]
- [Verified environmental or operating system facts]

## 2. Hypotheses
- [Working diagnostic hypothesis explaining why the failure occurs]
- [Confidence level: high | medium | low]

## 3. Attempts and Outcomes
- **Attempt 1**: [Description of what was tried]
  - *Outcome*: [Observed result, whether it succeeded or failed]
- **Attempt 2**: [Description of follow-up approach if applicable]
  - *Outcome*: [Observed result]

## 4. Remaining Gaps & False-Positive Boundaries
- **Boundaries**: [When this error pattern does NOT apply; explicit false-positive criteria]
- **Gaps**: [Unverified assumptions or unresolved environmental limitations]

## 5. Verified Prevention Check
- **Rule / Guard**: [Specific coding rule, pre-check, or configuration setting]
- **Verification**: [Test file or runnable assert verifying the prevention guard]

## 6. Evidence Links
- **Raw Receipts / Logs**: [Relative link to .runtime or log evidence]
- **Source Code**: [Relative link to affected source module]
- **Regression Test**: [Relative link to unit or integration test]
