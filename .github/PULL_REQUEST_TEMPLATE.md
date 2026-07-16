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
- [ ] Type checking passes (`mypy .`)
- [ ] Self-review completed
- [ ] No secrets committed (`git diff --check`)
- [ ] Documentation updated if behavior changed
- [ ] Related issues linked

## Additional Context

Any other information, configuration, or screenshots that help reviewers understand the change.