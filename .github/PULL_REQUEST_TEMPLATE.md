## Description

Brief summary of changes.

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Refactoring (no functional changes)
- [ ] Test addition or update
- [ ] Configuration change

## Related Issues

Closes #(issue number)

## Testing

- [ ] Unit tests added/updated
- [ ] Integration tests pass locally
- [ ] Manual pipeline run verified (specify steps tested)

```bash
# Commands run to verify
python -m pytest tests/ -v
python <tested_script>.py
```

## Checklist

- [ ] Code follows style guidelines (`black . && ruff check .`)
- [ ] Type checking passes (`venv/Scripts/python.exe -m mypy --strict src/`)
- [ ] Self-review completed
- [ ] No secrets committed (`git diff --check`)
- [ ] Documentation updated if behavior changed
- [ ] Related issues linked

## Documentation impact

- Reader-facing behavior changed, or specific reason there is no impact:
- README/setup/reference files updated, or why existing instructions remain accurate:
- Commands, links and claims verified; name checks actually run and any limitations:

See [README maintenance](https://github.com/Snoozer10/local-youtube-automation/blob/master/docs/agents/readme-maintenance.md). Documentation-impact assessment is required even when no documentation edit is needed.

## Additional Context

Any other information, configuration, or screenshots that help reviewers understand the change.