# Application context contracts

A context contract declares the application facts that a Samsarix policy is allowed to reference.
It catches misspelled paths and incompatible operators before deployment, then checks required
facts and JSON types on every contracted evaluation. Contracts are optional so existing callers
remain compatible; production applications can require one at their policy boundary.

This is a deliberately restricted application contract, not JSON Schema, Cedar schema, or a
general data-validation language. The package keeps its zero-dependency runtime and validates only
declared dotted paths. Unrelated input fields remain accepted, allowing opaque tool arguments and
application metadata to travel through a normalized context without being exhaustively modeled.

## Format

```json
{
  "context_contract_version": 1,
  "id": "tool-call-context",
  "version": "1.0.0",
  "description": "Facts exposed to tool-call policy.",
  "fields": {
    "action": {"type": "object"},
    "action.operation": {"type": "string"},
    "action.capabilities": {"type": "array", "items": "string"},
    "context": {"type": "object"},
    "context.approved": {"type": "boolean", "required": false}
  }
}
```

Supported types are `array`, `boolean`, `integer`, `null`, `number`, `object`, and `string`.
`required` defaults to `true`. An array may declare one `items` type; omitting it permits any JSON
item type. Every dotted path's parent must also be declared as an `object`; a required child cannot
sit below an optional parent. A contract may contain
at most 1,000 fields, each path is at most 256 characters, and a loaded file is limited to 256 KiB.

`number` accepts finite integers and floating-point numbers but never booleans. `integer` accepts
integers but never booleans. This mirrors the policy engine's deliberate separation of JSON
booleans from Python's integer subtype behavior.

## Deployment validation

```bash
samsarix-ethics validate examples/policies/tool-call-baseline.json \
  --context-contract examples/contracts/tool-call-context.json
```

Validation requires every condition `field` and `$ref` path to be declared. It also checks:

- string operators use string facts and values;
- ordering operators compare two strings or two compatible numeric types;
- `contains`, `not_contains`, and `subset_of` use an array fact;
- `in`, `not_in`, and `subset_of` use an array policy value or array `$ref`;
- declared array-item types agree with membership values; and
- equality/reference operands have compatible types.

`integer` and `number` are mutually compatible. Optional `$ref` facts are permitted because a
preceding condition can guard their existence; if an evaluated rule reaches a missing `$ref`, the
normal engine behavior remains a fail-closed `EvaluationError`.

## Runtime enforcement

```python
from samsarix_ethics import PolicyEngine, load_context_contract, load_policy

policy = load_policy("examples/policies/tool-call-baseline.json")
contract = load_context_contract("examples/contracts/tool-call-context.json")
engine = PolicyEngine(policy, context_contract=contract)
decision = engine.evaluate(context)
```

Use the same contract directly at an in-process enforcement boundary:

```python
from samsarix_ethics import ToolGate

gate = ToolGate(policy, context_contract=contract)
```

Construction rejects a policy-contract mismatch. Each evaluation first applies the existing
bounded JSON validation, then rejects a missing required fact, wrong declared type, or wrong array
item type with `InputValidationError`. Treat every such error as non-authorization.

## Regression and rollout lifecycle

Use the same contract for policy regression, coverage, baseline/candidate comparison, and live
shadow observation:

```bash
samsarix-ethics test --policy policy.json --context-contract contract.json policy.tests.json
samsarix-ethics coverage --policy policy.json --context-contract contract.json policy.tests.json
samsarix-ethics compare --baseline baseline.json --candidate candidate.json \
  --context-contract contract.json policy.tests.json
samsarix-ethics shadow --baseline baseline.json --candidate candidate.json \
  --context-contract contract.json --input action.json
```

The corresponding Python APIs accept `context_contract=...`: `run_policy_tests`,
`measure_policy_coverage`, `compare_policies`, and `PolicyShadowEvaluator`. Policy/contract
incompatibility is a configuration error raised before cases or live input are evaluated. Contract
input failures become ordinary input-free test/coverage/comparison errors; a baseline contract
failure in shadow evaluation propagates as non-authorization.

Comparison and shadow evaluation require one shared contract for baseline and candidate. For an
additive schema migration, deploy optional new facts in the contract first, populate them, and only
then evaluate a policy that references them. This keeps baseline and candidate evidence within one
declared application boundary. Removing or changing fact types requires a separately reviewed
migration; this API does not compare two different application schemas.

Version 1 decision, test, coverage, comparison, shadow, and audit records do not embed a contract
fingerprint in lifecycle reports. Use a deployment lock to bind the reviewed contract artifact and
policy together at validation and evaluation boundaries. Policy fingerprints continue to identify
only policy content.

## Security boundary and limitations

A contract describes expected structure; it does not prove that a fact is authentic, current, or
authorized. The embedding application still owns fact derivation and must keep model-controlled
payloads from supplying capability labels, identity, approval, tenant, or other trusted facts.

Contracts do not reject undeclared request fields, constrain strings or numeric ranges, enumerate
allowed values, model heterogeneous arrays, or validate relationships between facts. Express
authorization constraints in reviewed policies and regression suites. Use an application schema
or a full validation library before Samsarix when the entire request must be closed and modeled.

The bundled Draft 2020-12 schema describes the contract document itself and is available with:

```bash
samsarix-ethics schema context-contract
```
