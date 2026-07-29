# Contributing

Thank you for improving Samsarix Agent Ethics. Contributions should preserve its narrow product
boundary: a deterministic, local policy gate rather than a hosted service or subjective ethics
oracle.

## Setup

```bash
git clone https://github.com/Deathcharge/samsarix-agent-ethics.git
cd samsarix-agent-ethics
python -m venv .venv
```

Activate the environment, then install the pinned toolchain:

```bash
python -m pip install -r requirements-dev.txt
```

## Required checks

```bash
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m pytest
python -m build
python -m twine check dist/*
```

Use `python -m ruff format .` to apply formatting. Tests must exercise real package behavior; mocks
are appropriate only at actual external boundaries. Keep the coverage gate at or above 90% and add
command-level tests for CLI behavior or exit-code changes.

## Policy-engine changes

Security properties are part of the public contract:

- invalid data must never become an allow decision;
- deny must continue to override review and allow;
- evaluation must remain deterministic and bounded;
- the built-in audit record must not acquire raw action input;
- new operators need wrong-type, missing-field, and adversarial-input tests;
- destructive CLI behavior must remain explicit.

Update `docs/POLICY_FORMAT.md`, `docs/API.md`, and `CHANGELOG.md` for user-visible behavior.

## Pull requests

Keep changes focused. In the pull request, explain the user problem, policy/security impact,
compatibility impact, and exact commands run. Do not commit virtual environments, audit logs,
coverage output, build artifacts, credentials, or production policy/input data.

Use GitHub's private vulnerability-reporting flow for security issues; follow `SECURITY.md` rather
than publishing exploit details in an issue.

## License

Contributions are submitted under Apache License 2.0 unless explicitly marked otherwise before
submission. Preserve the repository's `LICENSE`, `NOTICE`, and trademark notices. Questions about
contribution licensing can be sent to [contact@samsarix.com](mailto:contact@samsarix.com).
