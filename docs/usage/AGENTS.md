# Public usage guides

## Purpose
Own user-facing production instructions, channel bundle setup and reference-channel research. Development task records remain in tasks/ and dated session state remains in docs/sessions/.

## Ownership
- adaptive-mode.md: Adaptive staged mode, stage prerequisites, commands, expected outputs, review, recovery and troubleshooting.
- channel-bundles.md: bundled examples, creating and validating a personal channel profile, and selecting it for production.
- channel-research.md: REA reference evidence, study readiness, profile derivation and activation through supported interfaces.
- Root README.md: product introduction, mode comparison, feature overview and navigation to these guides.

## Local contracts
- Derive commands and file/schema examples from the current implementation. Explain command versus Python API availability; do not invent CLI stages.
- Keep examples runnable after their explicit prerequisites. Use bundled paths or create the example file first. Label placeholder inputs and distinguish offline validation from live generation.
- Explain editorial and provider boundaries where an action occurs. Historical task grants, PIDs, receipts and developer paths do not apply to a reader's installation.
- Describe channel bundles as project profile/configuration assets, not a separately implemented package or installer format. Versioned study-derived profiles have their own activation contracts.
- Keep user guides free of dated development cursors. Link to the setup guide for installation and keep detailed domain authority in its source contracts.

## Verification
- python tools/check_readme.py

## Child DOX index
- None.
