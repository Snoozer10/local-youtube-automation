# Keep public onboarding accurate

The root README owns the project's introduction and first-use navigation. [Getting started](../getting-started.md) owns the human setup sequence; [AI-assisted setup](setup.md) owns the agent's procedure. This file owns when those surfaces must be reviewed and how to verify them.

## Assess impact in every change

Before closing a task, compare its public behavior with the README and affected setup/reference guides. In the PR's Documentation impact section, name the updated files or give a specific reason the change has no reader-facing effect. A checked box alone is not the assessment.

| Change | Review these surfaces |
|---|---|
| Capabilities, channel/niche scope or production status | README opening, capability table and workflow descriptions |
| Installation, dependencies, supported OS/Python or packaging | README requirements, human setup guide and agent setup procedure |
| Public commands, flags, inputs, outputs or resume behavior | README examples and the owning operational guide |
| Configuration defaults, authentication or required applications | Setup guide and owning configuration/reference document |
| Workflow review, resource ownership or live-service boundaries | README limits and the affected agent/operational guide |
| Private implementation with unchanged public behavior | Usually no README edit; explain why in the PR |
| A release | Package/release metadata, changelog and any version-specific public instructions |

Update affected documents in the same change. Use the changelog for individual release changes rather than appending an implementation diary to the README. Link to detailed references instead of duplicating complete configuration files.

## Verify claims and examples

For each new or changed claim, identify its source: package metadata, parser, configuration loader, maintained contract, test or exact artifact. Distinguish implemented behavior, verified environments, goals and remaining proof. Human editorial acceptance is separate from software checks.

Keep instructions runnable in their named shell. For installation commands that would download packages or modify a machine, review their source and report whether a fresh installation was actually exercised. Do not run production merely to validate documentation. Recheck command flags before documenting them.

Use CI status badges tied to real workflow files. Derive compatibility wording from package metadata, and separately identify the actual CI interpreter. Avoid hardcoded provider/model, test-count, coverage or release badges without a maintained source. The banner is a visual introduction, not evidence of performance or a completed video.

## Run the offline check

From the repository root:

```powershell
python tools/check_readme.py
python -m unittest discover -s tests/unit -p test_readme_contract.py -v
```

The checker covers the README, human setup, agent setup and this maintenance guide. It checks the supported inline-link/heading syntax, local targets, onboarding routing, clone placeholders and selected badge/metadata contracts. It does not access external URLs, establish service availability, execute example commands or prove that prose accurately describes production behavior. A human or independent agent must review those claims.

[The documentation workflow](../../.github/workflows/docs.yml) runs these dependency-free checks on pushes and pull requests targeting master. The main software CI remains separate. A passing documentation check is not a required branch-protection rule until a repository owner configures it as one.

## Review the reader experience

Read the first screen as someone who has never opened the repository. They should understand its purpose, requirements and next step. Read the setup instructions as someone who cannot debug a failed installation. They should know what success looks like, where to find outputs and how to report a failure.

Keep the README concise, use stable terms and explain jargon where needed. New niches should be described through channel configuration and explicit examples. Do not imply that every niche, operating system, hardware encoder or external model has been tested.

## Assets and workflow provenance

`docs/assets/readme-banner.png` is an AI-generated project illustration created for the README on 2026-11-02. Its pictured media cards are illustrative, not captured output or an accuracy claim. Keep meaningful alt text next to the image and retain a text project title for accessibility. Review a replacement at normal GitHub reading width.

The separate documentation workflow uses published action releases [checkout v6.0.2](https://github.com/actions/checkout/releases/tag/v6.0.2) and [setup-python v6.2.0](https://github.com/actions/setup-python/releases/tag/v6.2.0), checked on 2026-11-02. This does not upgrade or qualify the existing software/release workflows.
