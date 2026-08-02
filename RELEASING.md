# Release operator guide

This guide separates a verified build from a package-registry publication. Merging, producing an
attested artifact, publishing a release, and claiming adopter evidence are distinct gates.

## Current automation

The Python 3.11 CI job builds the wheel and source distribution once, validates both files, installs
the wheel into a clean virtual environment, and uploads the exact files as
`python-distributions-<commit>` for 14 days. The same workflow exercises the source package across
Python 3.11-3.14. Dedicated hash-locked lanes exercise the exact OpenAI Agents SDK, LangChain, and
OpenTelemetry API/SDK contracts plus their no-network examples; release candidates are valid only
when the complete matrix and all optional-integration lanes are green.

For pushes to `main`, a separate least-privilege job waits for the complete matrix, downloads those
already-verified files, and creates GitHub build-provenance attestations. The attestation links each
distribution digest to the repository, commit, and workflow run. Pull requests receive downloadable
artifacts but cannot mint attestations.

Nothing in this repository currently uploads to PyPI, creates a GitHub release, or moves a tag.

## Candidate verification

1. Confirm `main` is clean, synchronized, and green at the intended commit.
2. Confirm `pyproject.toml`, `samsarix_ethics.__version__`, and the changelog name the same version.
3. Install the hash-locked development environment and run the base release suite:

   ```bash
   python -m pip install --require-hashes -r requirements-dev.lock
   python -m ruff format --check .
   python -m ruff check .
   python -m mypy
   python -m pytest
   python -m build --no-isolation
   python -m twine check dist/*
   ```

4. In a fresh virtual environment, validate only the OpenAI Agents optional contract:

   ```bash
   python -m pip install --require-hashes \
     -r requirements-dev.lock \
     -r requirements-openai-agents.lock
   python -m pytest --no-cov integration_tests/test_openai_agents_sdk.py
   python examples/openai_agents_guardrail_demo.py
   ```

5. In a second fresh virtual environment, validate only the LangChain optional contract:

   ```bash
   python -m pip install --require-hashes \
     -r requirements-dev.lock \
     -r requirements-langchain.lock
   python -m pytest --no-cov integration_tests/test_langchain_sdk.py
   python examples/langchain_policy_middleware_demo.py
   ```

6. In a third fresh virtual environment, validate only the OpenTelemetry optional contract:

   ```bash
   python -m pip install --require-hashes \
     -r requirements-dev.lock \
     -r requirements-opentelemetry.lock
   python -m pytest --no-cov integration_tests/test_opentelemetry_sdk.py
   python examples/opentelemetry_decision_event_demo.py
   ```

7. Download the exact CI distributions for the commit, then verify their provenance:

   ```bash
   gh run download RUN_ID \
     --name python-distributions-COMMIT \
     --dir dist
   gh attestation verify dist/samsarix_agent_ethics-VERSION-py3-none-any.whl \
     --repo Deathcharge/samsarix-agent-ethics
   gh attestation verify dist/samsarix_agent_ethics-VERSION.tar.gz \
     --repo Deathcharge/samsarix-agent-ethics
   ```

8. Install the downloaded wheel with `--no-deps` in a new virtual environment and run
   `samsarix-ethics --version`, schema export, policy validation, and one allow/deny walkthrough.
9. Record the commit, CI run, distribution SHA-256 digests, attestation verification, and rollback
   ref in the release notes.

## Registry publication prerequisites

Before adding or running a PyPI publication job, a Samsarix LLC maintainer must:

- confirm control of the `samsarix-agent-ethics` project name on PyPI;
- configure a PyPI Trusted Publisher for this repository and the exact publication workflow;
- create a protected GitHub `pypi` environment with required reviewer approval;
- review package metadata, Apache-2.0/NOTICE contents, support contacts, and the public changelog;
- ensure the workflow publishes the distributions downloaded from the verified build job instead
  of rebuilding them;
- use OpenID Connect Trusted Publishing rather than storing a long-lived PyPI token.

Follow the [Python Packaging User Guide's GitHub Actions publication pattern](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
and retain commit-pinned actions. A publication workflow should not be merged until its PyPI
publisher identity and protected environment can be exercised intentionally.

## Recovery

Do not reuse or move a published version tag. If a release is incorrect, preserve its provenance,
yank the affected PyPI files when appropriate, publish a corrected patch version, and document the
impact and migration path. GitHub Actions artifacts expire; durable release records must retain the
published distribution digests and attestation verification instructions.
