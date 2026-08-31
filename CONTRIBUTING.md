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
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-build-isolation --no-deps -e .
```

`requirements-dev.txt` is the human-maintained source list. Regenerate the cross-platform lock with
`uv pip compile --universal --python-version 3.11 --generate-hashes requirements-dev.txt -o requirements-dev.lock`
and review the resulting dependency changes before committing them. The lock includes the build
backend, so development installs and release checks disable build isolation to keep every installed
tool inside the hash-verified dependency boundary.

Optional integrations have separate exact contract inputs and locks. Regenerate them with the same
universal Python 3.11 flags and run their dedicated integration tests and examples in environments
that install exactly one of `requirements-openai-agents.lock`, `requirements-langchain.lock`,
`requirements-pydantic-ai.lock`, `requirements-mcp.lock`, `requirements-mcp-client.lock`, or
`requirements-opentelemetry.lock` together with the development
lock. Keep optional packages out of the base development environment so the dependency-free import
contract remains testable.

The MCP v1 server and v2 client extras cannot coexist. For the v2 client lock, also pass
`--constraint requirements-dev.lock` during compilation, preserving shared transitive pins, and
run `python -m pytest --no-cov integration_tests/test_mcp_client_sdk.py integration_tests/test_mcp_client_http.py` plus
`python examples/mcp_client_policy_demo.py` in its own hash-locked environment.
The HTTP tests bind ephemeral loopback ports and require no external server or credentials.

## Required checks

```bash
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m pytest
python -m build --no-isolation
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
