# Pull request

## What changed

Describe the user problem and the focused solution.

## Security and compatibility

Explain any effect on decision precedence, error handling, audit privacy, policy compatibility,
dependencies, CLI exit codes, or the public Python API.

## Verification

- [ ] `python -m ruff format --check .`
- [ ] `python -m ruff check .`
- [ ] `python -m mypy`
- [ ] `python -m pytest`
- [ ] `python -m build`
- [ ] `python -m twine check dist/*`
- [ ] Documentation and `CHANGELOG.md` reflect user-visible behavior.
- [ ] No secrets, private policies, production inputs, personal data, or audit logs are included.
