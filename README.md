# Samsarix Agent Ethics

Samsarix Agent Ethics is a local, deterministic policy gate for autonomous agent actions. It
answers one operational question before an agent acts: **allow, deny, or require human
review?**

It is for Python developers who need a small policy-as-code boundary in front of tool calls,
workflows, or other consequential operations. Policies and inputs are JSON, decisions are
explainable, and the optional audit log excludes raw input by design. The package makes no
network calls and has no runtime dependencies. Other Samsarix repositories can embed it, but none
is required; the package and its release lifecycle stand on their own.

> Status: **0.1.0 release candidate.** The core CLI and library journey is implemented and
> tested. It is not a general moral-reasoning system, a compliance certification product, or a
> substitute for application authorization and human judgment.

## Fastest successful path

Prerequisites: Python 3.11 or newer and Git.

```bash
git clone https://github.com/Deathcharge/samsarix-agent-ethics.git
cd samsarix-agent-ethics
python -m venv .venv
```

Activate the environment:

```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install and evaluate the included read-only action:

```bash
python -m pip install -e .
samsarix-ethics validate examples/policies/safe-agent-actions.json
samsarix-ethics check \
  --policy examples/policies/safe-agent-actions.json \
  --input examples/actions/read-resource.json
```

The last command prints a JSON decision with `"outcome": "allow"` and exits `0`.

The destructive example is denied and exits `3`:

```bash
samsarix-ethics check \
  --policy examples/policies/safe-agent-actions.json \
  --input examples/actions/delete-resource.json
```

PowerShell accepts the same command on one line. The CLI also reads input from standard input:

```bash
echo '{"action":{"operation":"read","risk":"low"}}' | \
  samsarix-ethics check --policy examples/policies/safe-agent-actions.json
```

## CLI

```text
samsarix-ethics init POLICY.json [--force]
samsarix-ethics validate POLICY.json [--format text|json]
samsarix-ethics check --policy POLICY.json [--input INPUT.json|-]
                      [--audit-log decisions.jsonl] [--format json|text]
samsarix-ethics --help
samsarix-ethics --version
```

Exit codes are stable for non-interactive use:

| Code | Meaning |
| ---: | --- |
| `0` | action allowed, or non-decision command succeeded |
| `2` | invalid invocation, policy, input, evaluation, or requested audit write |
| `3` | action denied |
| `4` | human review required |

Only code `0` authorizes execution. Invalid data is an error, never an implicit allow.

Generate a starting policy without overwriting existing work:

```bash
samsarix-ethics init policy.json
```

`--force` is required to replace an existing file.

## Python API

```python
from samsarix_ethics import PolicyEngine, load_policy

policy = load_policy("examples/policies/safe-agent-actions.json")
decision = PolicyEngine(policy).evaluate(
    {
        "actor": {"id": "research-agent"},
        "action": {"operation": "read", "risk": "low"},
        "context": {"human_approved": False},
    }
)

if decision.allowed:
    print(decision.decision_id, decision.reasons)
```

The application remains responsible for enforcing the decision immediately before the protected
operation. See [API reference](docs/API.md) and [policy format](docs/POLICY_FORMAT.md).

## Decision semantics

- Every rule is evaluated; all conditions in a rule must match.
- A matching `deny` overrides every `review` or `allow`.
- A matching `review` overrides every `allow`.
- If no decisive rule matches, `default_effect` applies.
- `warn` and `audit` rules are non-decisive metadata.
- Policy and evaluation errors are surfaced instead of silently skipping a rule.

This narrow model follows established policy-engine patterns—explicit grants, deny overrides, and
pre-use validation—without attempting to reproduce the much broader OPA or Cedar languages.

## Security and privacy

- Policy files are trusted developer/operator configuration; evaluation input may be untrusted.
- JSON byte size, nesting depth, string length, container count, rule count, and condition count are
  bounded.
- Duplicate JSON keys and non-finite numbers are rejected.
- There is no expression evaluation, regex engine, template expansion, dynamic import, shell
  execution, network request, database, or secret requirement.
- Optional audit JSONL includes decision metadata and matched rule IDs, never the raw input.
- Audit retention, access controls, rotation, and tamper resistance belong to the embedding
  application. A successful append is flushed to disk but is not a cryptographic ledger.

See [SECURITY.md](SECURITY.md) for the threat boundary and reporting process and
[SUPPORT.md](SUPPORT.md) for safe support requests.
General support is available at [support@samsarix.com](mailto:support@samsarix.com); company and
partnership inquiries can use [contact@samsarix.com](mailto:contact@samsarix.com).

## Development

The runtime has no third-party dependencies. The checked-in development requirements pin the
local and CI toolchain:

```bash
python -m venv .venv
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-build-isolation --no-deps -e .
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m pytest
python -m build --no-isolation
python -m twine check dist/*
```

The lock includes the build backend. Development installs and release checks disable build
isolation so no unverified build dependency is fetched outside that lock.

CI runs formatting, linting, strict type checking, tests with a 90% coverage gate, and package
build checks. Compatibility tests cover Python 3.11 through 3.14.

## Packaging and release

Build artifacts locally with `python -m build --no-isolation` after installing the locked
toolchain. Publication is intentionally not automated and has
not been performed. The `samsarix-agent-ethics` distribution name was unclaimed on PyPI when this
release candidate was prepared, but availability is not a reservation. Test the wheel in a clean
environment as described in [docs/PRODUCTIZATION.md](docs/PRODUCTIZATION.md) before publishing.

## Architecture and limitations

The product is a library plus CLI; it has no server or cloud component. The package separates
validated immutable models, deterministic evaluation, bounded I/O, and presentation/exit codes.
See [architecture](docs/ARCHITECTURE.md).

Deliberate limitations:

- JSON policies only; no arbitrary code, regex, network data, or plugin execution.
- In-process evaluation only; no policy distribution control plane.
- JSONL audit append is local and metadata-only, with no cross-process ordering guarantee.
- The engine evaluates explicit caller-supplied facts; it does not infer intent or truth.
- Policies must be reviewed and tested for the embedding application's real threat model.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for the verified development workflow.

Copyright 2024-2026 Samsarix LLC. Licensed under the [Apache License 2.0](LICENSE). The
[NOTICE](NOTICE) file preserves product attribution, and [TRADEMARKS.md](TRADEMARKS.md) explains
that the software license does not grant rights to Samsarix names or branding.
