# Layered policy composition

`compose_policies` and `samsarix-ethics compose` combine independently maintained policy sources
into one ordinary, deployable Samsarix policy. The intended use case is a central build step that
layers organization guardrails with application permissions before linting, regression testing,
coverage measurement, review, and rollout.

## Runnable support-agent example

The repository splits its twelve-rule tool-call baseline into two ownership boundaries:

- `organization-tool-guardrails.json` owns context validation, destructive-action denial, and
  external-write review/rejection;
- `support-agent-tool-permissions.json` owns the support application's explicit grants and
  sensitive-data warning.

Compose them in declaration order:

```bash
samsarix-ethics compose \
  --id tool-call-baseline \
  --version 1.0.0 \
  --description "Fail-closed baseline for read, destructive, external, and sensitive tool capabilities." \
  --policy examples/policies/organization-tool-guardrails.json \
  --policy examples/policies/support-agent-tool-permissions.json \
  --output composed-policy.json \
  --format json
```

The command atomically writes `composed-policy.json` and prints a versioned, value-minimized
provenance report. The generated policy has the same twelve rules and exact policy fingerprint
as `examples/policies/tool-call-baseline.json`. Exercise the full deployment artifact:

```bash
samsarix-ethics lint composed-policy.json --fail-on suggestion
samsarix-ethics test --policy composed-policy.json examples/tests/tool-call-baseline.tests.json
samsarix-ethics coverage --policy composed-policy.json examples/tests/tool-call-baseline.tests.json --threshold 100
```

The fourteen cases cover malformed context, read, destructive, external-write, approval,
sensitive-data, and unknown-capability paths. They match every composed rule and observe allow,
deny, and review outcomes.

## Composition contract

Composition is deliberately strict and deterministic:

1. Sources are already validated immutable `Policy` values and are processed in the supplied
   order. The CLI accepts 1-32 repeated `--policy` paths.
2. Source policy IDs must be unique. Rule IDs must be globally unique across all sources; the
   composer never silently renames or shadows a rule.
3. Every source must declare the same `default_effect`. A default belongs to the complete policy,
   so applying independent defaults after each source would change rule semantics.
4. Rules are concatenated without modification. The composed policy retains the normal
   `deny > review > allow > default_effect` behavior and the existing 1,000-rule limit.
5. Target ID, version, description, rules, and aggregate limits pass through the authoritative
   policy validator. The serialized result must also fit the normal 1 MiB and shared structural
   limits, so `write_policy` cannot produce an artifact that `load_policy` would reject.
   The result is a normal `Policy`, not a second runtime format.
6. Source order, target metadata, source content, or rule content changes can change the composed
   policy fingerprint. Recompose and rerun the complete consumer suite after any such change.

`--output` refuses to replace an existing path unless `--force` is explicit. Its parent directory
must already exist. This prevents a build command from silently replacing a reviewed artifact.

## Python API

```python
from samsarix_ethics import compose_policies, load_policy, write_policy

composition = compose_policies(
    [
        load_policy("organization-tool-guardrails.json"),
        load_policy("support-agent-tool-permissions.json"),
    ],
    policy_id="support-agent",
    policy_version="2026-08-01",
)
write_policy("support-agent.json", composition.policy)
print(composition.policy_fingerprint)
print(composition.to_dict())
```

`PolicyComposition` and each `PolicyCompositionSource` are frozen. `to_dict()` returns only the
target identity, default, fingerprint and rule count plus each source's ID, version, fingerprint,
and rule count. It omits paths, descriptions, rules, conditions, messages, and condition values.
The report schema is available through `get_policy_composition_schema()` or:

```bash
samsarix-ethics schema policy-composition
```

## Security boundary

Composition is a trusted build-time operation, not runtime policy distribution. The library does
not discover directories, follow imports, fetch URLs, watch files, select tenant policies, verify
signatures, authenticate policy authors, or activate changes. Pin and protect source files in the
embedding application's supply chain, retain the composition report with build evidence, and
deploy only the tested output.

Fingerprints prove exact content equality under the documented serializer. They are not digital
signatures, freshness guarantees, or rollback protection, and can act as equality oracles for
guessable private policies. Protect reports accordingly. A valid composition also does not prove
that its sources implement business intent or least privilege.

This central aggregation model avoids runtime ordering races. It does not implement OPA bundles,
Cedar policy stores, remote management, version migration, or hot reload.
