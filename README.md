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
samsarix-ethics test --policy examples/policies/safe-agent-actions.json \
  examples/tests/safe-agent-actions.tests.json
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
samsarix-ethics schema [policy|policy-test|policy-comparison|policy-composition|policy-coverage|policy-lint|tool-context|tool-approval|audit-record]
samsarix-ethics compose --id ID --version VERSION --policy SOURCE.json [--policy SOURCE.json ...] \
                        --output POLICY.json [--description TEXT] [--force] [--format text|json]
samsarix-ethics lint POLICY.json [--fail-on none|security-warning|warning|suggestion]
                              [--format text|json]
samsarix-ethics test --policy POLICY.json TESTS.json [--format text|json]
samsarix-ethics coverage --policy POLICY.json TESTS.json \
                         [--threshold PERCENT] [--format text|json]
samsarix-ethics compare --baseline BASELINE.json --candidate CANDIDATE.json \
                        TESTS.json [--format text|json]
samsarix-ethics check --policy POLICY.json [--input INPUT.json|-]
                      [--audit-log decisions.jsonl] [--format json|text]
samsarix-ethics --help
samsarix-ethics --version
```

Exit codes are stable for non-interactive use:

| Code | Meaning |
| ---: | --- |
| `0` | action allowed, or non-decision command succeeded |
| `1` | lint findings met the selected severity, policy tests failed/errored, coverage missed its threshold/errored, or comparison found changes/errors |
| `2` | invalid invocation, policy, input, evaluation, or requested audit write |
| `3` | action denied |
| `4` | human review required |

Only code `0` authorizes execution. Invalid data is an error, never an implicit allow.

Generate a starting policy without overwriting existing work:

```bash
samsarix-ethics init policy.json
```

`--force` is required to replace an existing file.

Print the versioned Draft 2020-12 schemas for editors, CI, or code generation:

```bash
samsarix-ethics schema policy > policy-v1.schema.json
samsarix-ethics schema policy-test > policy-test-v1.schema.json
samsarix-ethics schema policy-comparison > policy-comparison-v1.schema.json
samsarix-ethics schema policy-composition > policy-composition-v1.schema.json
samsarix-ethics schema policy-coverage > policy-coverage-v1.schema.json
samsarix-ethics schema policy-lint > policy-lint-v1.schema.json
samsarix-ethics schema tool-context > tool-context-v1.schema.json
samsarix-ethics schema tool-approval > tool-approval-v1.schema.json
samsarix-ethics schema audit-record > audit-record-v1.schema.json
```

Compose organization-owned guardrails with application-owned permissions into one ordinary policy:

```bash
samsarix-ethics compose \
  --id tool-call-baseline \
  --version 1.0.0 \
  --description "Fail-closed baseline for read, destructive, external, and sensitive tool capabilities." \
  --policy examples/policies/organization-tool-guardrails.json \
  --policy examples/policies/support-agent-tool-permissions.json \
  --output composed-policy.json
```

Sources must share a default effect and have globally unique rule IDs. The command writes the
deployable policy atomically and reports exact source/output fingerprints without copying paths,
descriptions, rules, conditions, messages, or values. The result works with every existing command;
the bundled fourteen-case support-agent suite reaches 100% of its twelve composed rules. See the
[layered policy composition guide](docs/POLICY_COMPOSITION.md).

Lint a valid policy for a deliberately small set of deterministic authoring risks:

```bash
samsarix-ethics lint examples/policies/safe-agent-actions.json --fail-on suggestion
```

Stable findings cover permissive defaults/unconditional allows, provably impossible or duplicate
conditions, and missing explanations without serializing condition values. See the
[policy authoring diagnostics guide](docs/POLICY_LINTING.md).

The bundled regression suite proves allow, deny, review, missing-approval, and warning behavior
without exposing case inputs in its report:

```bash
samsarix-ethics test --policy examples/policies/safe-agent-actions.json \
  examples/tests/safe-agent-actions.tests.json
```

Measure which rules the suite actually exercises and enforce a CI floor:

```bash
samsarix-ethics coverage \
  --policy examples/policies/tool-call-baseline.json \
  examples/tests/tool-call-baseline.tests.json \
  --threshold 100
```

The included tool-call suite matches all twelve rules and observes allow, deny, and review
outcomes. Coverage reports contain rule IDs and input-free errors, never case inputs. See the
[policy coverage guide](docs/POLICY_COVERAGE.md).

Compare an approved baseline with a candidate over that same suite before rollout:

```bash
samsarix-ethics compare \
  --baseline examples/policies/safe-agent-actions.json \
  --candidate examples/policies/safe-agent-actions-candidate.json \
  examples/tests/safe-agent-actions.tests.json
```

The included candidate changes one sensitive-read case from `allow` to `review`, so comparison
reports one authorization change and exits `1`. The versioned report never includes case inputs.
See the [policy impact comparison guide](docs/POLICY_COMPARISON.md).

## Python API

```python
from samsarix_ethics import (
    PolicyEngine,
    compare_policies,
    compose_policies,
    load_policy,
    load_policy_test_suite,
    lint_policy,
    measure_policy_coverage,
)

policy = load_policy("examples/policies/safe-agent-actions.json")
lint_report = lint_policy(policy)
engine = PolicyEngine(policy)
print(engine.policy_fingerprint)  # v1:sha256:...
decision = engine.evaluate(
    {
        "actor": {"id": "research-agent"},
        "action": {"operation": "read", "risk": "low"},
        "context": {"human_approved": False},
    }
)

if decision.allowed:
    print(decision.decision_id, decision.reasons)

batch = PolicyEngine(policy).evaluate_many(
    [{"action": {"operation": "read"}}, {"action": {"operation": "delete"}}]
)

candidate = load_policy("examples/policies/safe-agent-actions-candidate.json")
suite = load_policy_test_suite("examples/tests/safe-agent-actions.tests.json")
coverage = measure_policy_coverage(policy, suite, threshold=80)
impact = compare_policies(policy, candidate, suite)
print(coverage.coverage_percent, coverage.threshold_met)
print(lint_report.passed, len(lint_report.findings))
print(impact.authorization_changes, impact.metadata_only_changes)

composition = compose_policies(
    [
        load_policy("examples/policies/organization-tool-guardrails.json"),
        load_policy("examples/policies/support-agent-tool-permissions.json"),
    ],
    policy_id="tool-call-baseline",
    policy_version="1.0.0",
    description="Fail-closed baseline for support-agent tools.",
)
print(composition.policy_fingerprint, composition.to_dict()["sources"])
```

For an in-process tool boundary, `ToolGate` turns non-allow outcomes into typed exceptions and
invokes the callback only after an allow decision:

```python
from samsarix_ethics import ToolGate, load_policy

gate = ToolGate(load_policy("examples/policies/tool-call-baseline.json"))
read_ticket = gate.bind("read_ticket", capabilities=["resource:read"])
result = read_ticket.execute(
    {"ticket_id": "T-100"},
    lambda arguments: ticket_store.read(arguments["ticket_id"]),
    actor={"id": "support-agent"},
)
print(result.decision.decision_id, result.value)
```

For a paused human-review flow, bind the authenticated decision to the exact framework call ID,
tool name, arguments, capabilities, and actor that were displayed for review:

```python
from samsarix_ethics import ToolCallApproval

call_id = "email-call-100"
arguments = {"to": "customer@example.com", "subject": "Case update"}
actor = {"id": "support-agent"}
send_email = gate.bind("send_email", capabilities=["external:write"])

# Persist this server-side with the pending call before requesting review.
pending_fingerprint = send_email.fingerprint(call_id, arguments, actor=actor)

# Construct this only from an authenticated reviewer decision and stored fingerprint.
approval = ToolCallApproval(call_id, True, pending_fingerprint)
result = send_email.execute(
    arguments,
    lambda prepared: mailer.send(**prepared),
    actor=actor,
    tool_call_id=call_id,
    approval=approval,
)
```

`ToolGate` recomputes the bounded versioned fingerprint and rejects any changed call before policy
evaluation, audit delivery, or execution. The application still owns reviewer authentication,
expiration, atomic one-time consumption, and protected pending-call storage. A parsed
`ToolCallApproval` is evidence supplied by the caller, not proof that its source is authentic.
`gate.bind(...)` also freezes the application-owned tool name and capability labels once at
registration, so untrusted invocation data cannot downgrade them per call.

`execute_async` provides the same fail-closed boundary for async callbacks. Denials raise
`ToolCallDeniedError`; review outcomes raise `ToolCallReviewRequiredError`; neither invokes the
tool. See the [tool-call integration guide](docs/TOOL_CALLS.md), [API reference](docs/API.md), and
[policy format](docs/POLICY_FORMAT.md).

Run the dependency-free demonstration with `python examples/tool_gate_demo.py`.

Applications can route the same versioned metadata-only record to their own durable store or
telemetry pipeline with a synchronous sink:

```python
from samsarix_ethics import AuditRecord, ToolGate

records: list[AuditRecord] = []
gate = ToolGate(policy, audit_sink=records.append)
```

The sink runs once after each decision is computed and before the decision can authorize a callback.
It must return `None`; an exception or other return becomes `AuditLogError` and fails closed. Use
either `audit_sink=` or the existing local `audit_log=` path, not both. Agent Ethics never retries
delivery or includes evaluation input in `AuditRecord`. Every decision and audit record includes
the exact canonical policy fingerprint, so reused human-readable policy versions cannot make two
different policy bodies look identical in operational evidence.

## Downstream adoption

Samsarix Agent Framework is the first verified downstream consumer. Its optional policy registry
pins Agent Ethics `0.1.0` at source commit `eb69207b14ddd79bdfe774ec5b166c8ca8ce940e`, binds trusted
capabilities outside model arguments, re-reads authentication/approval facts for every call, and
blocks execution on every non-allow outcome or gate failure. The consumer contract runs on Python
3.11-3.14 while the framework's dependency-free core retains Python 3.10 support.

The consumer repository is private as of 2026-08-01, so this is Samsarix-owned integration
evidence rather than a public third-party case study or production deployment. Exact commits,
compatibility, rollback, support level, and evidence limits are recorded in
[adoption and compatibility evidence](docs/ADOPTION.md).

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
- Direct Python calls enforce the same bounded JSON contract as file and standard-input parsing.
- Baseline/candidate impact reports classify authorization, metadata-only, and error cases without
  copying regression inputs; equality is limited to the supplied cases.
- Rule-coverage reports show which policy branches a bounded suite matched, but cannot prove that
  every condition boundary or possible input was tested.
- Policy lint reports only certain authoring patterns and omits condition values; a clean report is
  not proof that permissions match business intent.
- Policy composition rejects ambiguous defaults and identifiers and reports only source/target
  metadata; it does not authenticate, distribute, sign, or activate policy.
- There is no expression evaluation, regex engine, template expansion, dynamic import, shell
  execution, network request, database, or secret requirement.
- Optional audit JSONL includes decision metadata and matched rule IDs, never the raw input.
- Decisions, policy-test reports, and audit records carry a versioned SHA-256 fingerprint of the
  complete validated policy body; policy ID/version remain operator-authored labels.
- Caller-owned audit sinks receive the same versioned metadata-only record and no raw input.
- `ToolGate` audits before execution when configured; an audit failure prevents the callback.
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
toolchain. CI retains the verified wheel and source distribution for 14 days; artifacts built from
`main` also receive GitHub build-provenance attestations. Publication is intentionally not automated
and has not been performed. The `samsarix-agent-ethics` distribution name was unclaimed on PyPI when
this release candidate was prepared, but availability is not a reservation. Follow the
[release operator guide](RELEASING.md) to verify an exact artifact and configure Trusted Publishing
before any registry upload.

## Architecture and limitations

The product is a library plus CLI; it has no server or cloud component. The package separates
validated immutable models, deterministic evaluation, fail-closed in-process tool enforcement,
versioned schemas, bounded I/O, authoring diagnostics, regression testing, rule coverage, policy
impact comparison, layered composition, and presentation/exit codes.
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
