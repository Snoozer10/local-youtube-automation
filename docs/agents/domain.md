# Domain Docs

## Layout

Single-context: one root `GLOSSARY.md` and repository-wide decisions in `docs/adr/`.

## Before exploring

- Read the applicable `AGENTS.md` chain; platform adapters load shared policy and do not establish a competing authority.
- Read root `GLOSSARY.md` when present. While it is absent, read the existing root `CONTEXT.md` for domain vocabulary.
- Read ADRs in `docs/adr/` that apply to the area being changed.
- If a domain document is absent, proceed silently. `/domain-modeling` creates or updates domain documentation when terms or decisions are resolved; setup does not create an empty glossary.

## Use domain vocabulary

Use canonical terms from the glossary, or existing `CONTEXT.md` during transition, in issue titles, proposals, hypotheses and tests. Avoid its explicitly rejected synonyms. Reconsider unfamiliar terms or note a real vocabulary gap for `/domain-modeling`.

## Flag ADR conflicts

If a proposal contradicts an existing ADR, identify the ADR and explain why the decision should be reopened.
