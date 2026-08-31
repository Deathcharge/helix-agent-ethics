# Release operator guide

This guide separates a verified build from a package-registry publication. Merging, producing an
attested artifact, publishing a release, and claiming adopter evidence are distinct gates.

## Current automation

The Python 3.11 CI job builds the wheel and source distribution once, validates both files, installs
the wheel into a clean virtual environment, and uploads the exact files as
`python-distributions-<commit>` for 14 days. The same workflow exercises the source package across
Python 3.11-3.14. Dedicated hash-locked lanes exercise the exact OpenAI Agents SDK, LangChain,
Pydantic AI, MCP v1 server, MCP v2 client, and OpenTelemetry API/SDK contracts plus their no-network examples; release candidates
are valid only when the complete matrix and all optional-integration lanes are green.
The core, SDK and process lanes install the local project non-editably using the locked build
backend. The Python 3.11 lane also checks every core test/helper against the source archive,
extracts that archive outside the checkout, and runs its full core suite against the built wheel
with the same 90% coverage gate. The separate clean-wheel smoke test still checks a base install
without development dependencies. Integration tests and SDK locks remain checkout-only resources.

For pushes to `main`, a separate least-privilege job waits for the complete matrix, downloads those
already-verified files, and creates GitHub build-provenance attestations. The attestation links each
distribution digest to the repository, commit, and workflow run. Pull requests receive downloadable
artifacts but cannot mint attestations.

Nothing in this repository currently uploads to PyPI, creates a GitHub release, or moves a tag.

## Candidate verification

Run from the root of a checkout of the intended commit, with Python 3.11+ and GitHub CLI available.
The integration tests and hashed SDK locks live in the checkout; an extracted sdist alone is not
the complete release-verification workspace. Do not set `PYTHONPATH` to `src`, enable system site
packages, or reuse a development environment: those can hide a missing installation.

Use a distinct **new** virtual environment for each of steps 3-9 (core, OpenAI Agents, LangChain,
Pydantic AI, MCP v1, OpenTelemetry, MCP v2). For example, create `.venv/release-core` for step 3:

```bash
python -m venv .venv/release-core
```

Activate with `source .venv/release-core/bin/activate` on macOS/Linux or
`.venv\release-core\Scripts\Activate.ps1` in PowerShell. Before the next lane, deactivate and create
a differently named environment. The following blocks use the active environment's `python`.
PowerShell users should join backslash-continued commands onto one line; backslash is Bash syntax.
Stop after any unexpected nonzero command; do not continue to publish based on later successes.

Every lane installs the hash-locked tools/SDK **and then this package**, with dependency resolution
and build isolation disabled. Regular installs exercise the installed package; editable installs
remain appropriate for development but are not the release acceptance path. See
[pip's regular/editable installation guidance](https://pip.pypa.io/en/stable/topics/local-project-installs/).

1. Confirm `main` is clean, synchronized, and green at the intended commit.
2. Confirm `pyproject.toml`, `samsarix_ethics.__version__`, and the changelog name the same version.
3. Install the hash-locked development environment and run the base release suite:

   ```bash
   python -m pip install --require-hashes -r requirements-dev.lock
   python -m pip install --no-build-isolation --no-deps .
   python -m pip check
   python -m ruff format --check .
   python -m ruff check .
   python -m mypy
   python -m pytest
   python -m pytest --no-cov integration_tests/test_deployment_process.py
   python examples/policy_restart_demo.py
   python -m build --no-isolation
   python -m twine check dist/*
   ```

4. In a fresh virtual environment, validate only the OpenAI Agents optional contract:

   ```bash
   python -m pip install --require-hashes \
     -r requirements-dev.lock \
     -r requirements-openai-agents.lock
   python -m pip install --no-build-isolation --no-deps .
   python -m pip check
   python -m pytest --no-cov integration_tests/test_openai_agents_sdk.py
   python examples/openai_agents_guardrail_demo.py
   ```

5. In a second fresh virtual environment, validate only the LangChain optional contract:

   ```bash
   python -m pip install --require-hashes \
     -r requirements-dev.lock \
     -r requirements-langchain.lock
   python -m pip install --no-build-isolation --no-deps .
   python -m pip check
   python -m pytest --no-cov integration_tests/test_langchain_sdk.py
   python examples/langchain_policy_middleware_demo.py
   ```

6. In a third fresh virtual environment, validate only the Pydantic AI optional contract:

   ```bash
   python -m pip install --require-hashes \
     -r requirements-dev.lock \
     -r requirements-pydantic-ai.lock
   python -m pip install --no-build-isolation --no-deps .
   python -m pip check
   python -m pytest --no-cov integration_tests/test_pydantic_ai_sdk.py
   python examples/pydantic_ai_policy_toolset_demo.py
   ```

7. In a fourth fresh virtual environment, validate only the MCP optional contract:

   ```bash
   python -m pip install --require-hashes \
     -r requirements-dev.lock \
     -r requirements-mcp.lock
   python -m pip install --no-build-isolation --no-deps .
   python -m pip check
   python -m pytest --no-cov integration_tests/test_mcp_sdk.py
   python examples/mcp_server_policy_demo.py
   ```

8. In a fifth fresh virtual environment, validate only the OpenTelemetry optional contract:

   ```bash
   python -m pip install --require-hashes \
     -r requirements-dev.lock \
     -r requirements-opentelemetry.lock
   python -m pip install --no-build-isolation --no-deps .
   python -m pip check
   python -m pytest --no-cov integration_tests/test_opentelemetry_sdk.py
   python examples/opentelemetry_decision_event_demo.py
   ```

9. In a sixth fresh virtual environment, validate only the MCP v2 client contract. Never combine
   the v1 server and v2 client locks or extras:

   ```bash
   python -m pip install --require-hashes \
     -r requirements-dev.lock \
     -r requirements-mcp-client.lock
   python -m pip install --no-build-isolation --no-deps .
   python -m pip check
   python -m pytest --no-cov integration_tests/test_mcp_client_sdk.py integration_tests/test_mcp_client_http.py integration_tests/test_mcp_http_transport.py integration_tests/test_mcp_client_oauth.py integration_tests/test_mcp_client_refresh.py
   python examples/mcp_client_policy_demo.py
   ```

10. Select the successful **main push** CI run whose `headSha` equals the intended full commit SHA.
    Confirm all test/SDK/recovery jobs and `Attest distributions` succeeded. Replace `RUN_ID`,
    `COMMIT` and `VERSION` below with that run, full SHA and package version. PR builds do not have
    attestations. Download into a new commit-specific directory, separate from local `dist/` builds;
    if it already exists, inspect it or choose a fresh directory instead of overwriting files.
    Verify both distributions before installing or executing either:

    ```bash
    gh run view RUN_ID --json event,headSha,headBranch,status,conclusion,jobs
    gh run download RUN_ID \
      --name python-distributions-COMMIT \
      --dir .venv/release-artifacts/COMMIT
    gh attestation verify .venv/release-artifacts/COMMIT/samsarix_agent_ethics-VERSION-py3-none-any.whl \
      --repo Deathcharge/samsarix-agent-ethics \
      --source-digest COMMIT \
      --source-ref refs/heads/main \
      --signer-workflow Deathcharge/samsarix-agent-ethics/.github/workflows/ci.yml
    gh attestation verify .venv/release-artifacts/COMMIT/samsarix_agent_ethics-VERSION.tar.gz \
      --repo Deathcharge/samsarix-agent-ethics \
      --source-digest COMMIT \
      --source-ref refs/heads/main \
      --signer-workflow Deathcharge/samsarix-agent-ethics/.github/workflows/ci.yml
    ```

    Repository-only verification is not enough to select a particular candidate. The commit, ref
    and signer constraints bind the artifact to the expected source/build identity; they do not
    replace code review or prove runtime safety. See the
    [GitHub CLI verification contract](https://cli.github.com/manual/gh_attestation_verify).

11. Install the verified downloaded wheel with `--no-deps` in a new virtual environment and run
    `samsarix-ethics --version`, schema export, policy validation, and one allow/deny walkthrough.
    Also replace the locally built package in each of the six SDK environments with that exact
    wheel using `python -m pip install --no-deps --force-reinstall WHEEL_PATH`, run
    `python -m pip check`, and repeat that lane's test and example commands. Keep MCP v1 and v2
    separate. Confirm `python -c "import samsarix_ethics; print(samsarix_ethics.__file__)"` points
    inside the lane's `site-packages`, not the checkout. Record results for the downloaded artifact,
    not just a locally rebuilt wheel with the same version label.
    From the same checkout or extracted sdist, run `python -m benchmarks.policy_gate run` using that
    environment's interpreter and retain the JSON with the exact wheel digest. The benchmark source
    is in the sdist, not the installed runtime API; timings are informational until deployment SLOs
    and controlled comparison conditions are selected. See [the methodology](docs/PERFORMANCE.md).
12. Record the commit, CI run, distribution SHA-256 digests, attestation verification, and rollback
    ref in the release notes.
    Refresh any claimed consumer compatibility against that exact artifact, separately from the
    public SDK tests. Record the consumer commit, actual installed wheel hash, tested interpreter,
    skipped contracts, and whether its declared dependency was changed. A consumer's old direct-URL
    extra or the shared `0.1.0` version label can otherwise conceal testing the wrong source. The
    [paired consumer qualification](docs/ADOPTION.md#current-default-qualification-2026-08-31)
    demonstrates this distinction without making private repositories necessary for public CI.

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
