# Samsarix portfolio boundary

Samsarix Agent Ethics is independently installable and useful without another Samsarix package.
Its canonical responsibility is the safety decision immediately before an autonomous-agent action:
allow, deny, or require review, backed by exact policy provenance, approval-bound tool calls,
metadata-minimized audit records, and a tested deployment lifecycle.

Nearby repositories remain separate products:

| Repository | Canonical responsibility | Relationship to Agent Ethics |
| --- | --- | --- |
| `samsarix-agent-ethics` | Agent/tool risk policy, review outcomes, enforcement, audit metadata, policy testing and rollout | This repository |
| [`policy-engine`](https://github.com/Deathcharge/policy-engine) | Generic principal/action/resource authorization and attribute matching | Use for application authorization; an embedding application may require both decisions |
| [`samsarix-core`](https://github.com/Deathcharge/samsarix-core) | Typed local tool runtime and protocol bridges such as MCP | Natural enforcement host; attach Agent Ethics at its trusted executor boundary |
| [`samsarix-agent-orchestration`](https://github.com/Deathcharge/samsarix-agent-orchestration) | Workflow graphs, durable checkpoints, approvals, and compensating operations | Owns durable process state; Agent Ethics supplies local action decisions, not workflow durability |
| `samsarix-agent-framework` | Agent loop and tool registry | Existing optional consumer; retains its own dependency and compatibility contract |

Do not copy policy evaluation into those repositories or make private monorepo imports. Integrate
through the published Python API and versioned JSON schemas, pin a released version or exact commit,
and keep a consumer-owned fail-closed contract test.

For a generic business permission such as “may principal P refund invoice I,” use the generic policy
engine or the application's authorization service. For an agent-execution question such as “may
this exact tool call run now, does it need review, and which reviewed policy authorized it,” use
Agent Ethics. Business authorization should be supplied as a trusted application fact or enforced
as a separate required decision; an Agent Ethics allow never replaces it.
