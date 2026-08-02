# Coding-agent policy pack

The checked coding-agent pack is a deployable starting point for local coding assistants, MCP
clients, and other tool-using developer agents. It demonstrates a concrete boundary: authorize all
calls proposed by one turn before the embedding runtime schedules any of them.

## Included evidence

- `examples/policies/coding-agent-baseline.json`: fifteen deterministic rules;
- `examples/contracts/coding-agent-tool-context.json`: the application fact boundary;
- `examples/tests/coding-agent-baseline.tests.json`: sixteen allow/deny/review cases with 100% rule
  coverage; and
- `examples/deployment/coding-agent-baseline.deployment.json`: one verified policy, contract, and
  exact-content lock.

Run the lifecycle checks:

```bash
samsarix-ethics validate examples/policies/coding-agent-baseline.json \
  --context-contract examples/contracts/coding-agent-tool-context.json
samsarix-ethics test \
  --policy examples/policies/coding-agent-baseline.json \
  --context-contract examples/contracts/coding-agent-tool-context.json \
  examples/tests/coding-agent-baseline.tests.json
samsarix-ethics coverage \
  --policy examples/policies/coding-agent-baseline.json \
  --context-contract examples/contracts/coding-agent-tool-context.json \
  examples/tests/coding-agent-baseline.tests.json --threshold 100
samsarix-ethics deployment verify \
  examples/deployment/coding-agent-baseline.deployment.json
python examples/coding_agent_batch_demo.py
```

## Trusted registration taxonomy

| Capability | Intended meaning | Baseline behavior |
| --- | --- | --- |
| `workspace:read` | Read within the verified workspace root | Allow only when `workspace_contained` is true and no other capability is present |
| `workspace:write` | Create or modify workspace content | Review unless paired with approved `risk:elevated`; deny outside the workspace |
| `process:execute` | Start a local process or command | Review unless paired with approved `risk:elevated` |
| `network:access` | Communicate outside the local workspace | Review unless approved; warn when used |
| `external:write` | Create an effect in another system | Review unless approved |
| `destructive` | Delete or irreversibly overwrite state | Deny without exact-call approval |
| `data:sensitive` | Access secrets, credentials, personal, or confidential data | Never inherits the read-only allow; warns whenever present |
| `risk:elevated` | Application-owned marker requiring human approval | Review without approval, deny after rejection, allow only a known capability subset after approval |

Unknown capabilities default to review. Known elevated capabilities accidentally registered without
`risk:elevated` also fail to inherit an allow rule. This is defense in depth, not automatic tool
classification: the application must conservatively label every registration.

## MCP and framework boundary

MCP `readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint` are protocol hints, not
authorization facts. Their specification defines conservative defaults but explicitly forbids
security decisions based on annotations from untrusted servers. Keep a trusted local allowlist and
map its complete local alias set through
[`examples/catalogs/coding-agent-tools.json`](../examples/catalogs/coding-agent-tools.json) before
creating frozen bindings; do not let the model or an untrusted server choose capability labels. A
newly discovered tool makes exact catalog binding fail until the application reviews and catalogs
it. An under-classified elevated tool still fails to inherit an allow rule.

`context.workspace_contained` is also application-owned. Compute it from resolved paths, the
approved workspace root, symlink/reparse-point policy, and the semantics of the actual executor.
The policy only consumes the boolean; it does not parse paths or contain the filesystem itself.
The context contract permits the field to be absent solely so the policy's explicit missing-fact
denial remains regression-tested; omission never authorizes a call.

OpenAI Agents SDK function-tool guardrails, Claude Code permission controls, and LangGraph
human-in-the-loop review all expose interception points, but their scheduling and tool categories
differ. Keep the Samsarix adapter at the last common application-controlled boundary. Prepare every
proposed call, call `enforce_many`, and dispatch immediately only if it returns. Built-in or hosted
tools that bypass a framework's function-tool guardrail need their own protected execution seam.
When a batch blocks, use the exception's ordered metadata-only `decisions` and `blocking_index` to
render the review queue; do not call `evaluate_many` again and mint a second set of decision IDs.

## Limits

The batch decision is not a transaction. Callback scheduling, cancellation, retries, filesystem
containment, command sandboxing, network egress, approval authentication/expiry/one-time use, audit
durability, and compensation after partial side effects remain embedding-application controls.
`PreparedToolCall.arguments` returns the detached arguments that were evaluated; dispatch from that
copy and do not reconstruct them from model output.
