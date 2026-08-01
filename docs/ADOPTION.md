# Adoption and compatibility evidence

This record distinguishes a verified library consumer from a public release or production
deployment. It is intentionally specific enough for maintainers to reproduce and update.

## Samsarix Agent Framework

Samsarix Agent Framework is the first consumer-owned integration. Its optional
`PolicyToolRegistry` is a drop-in framework tool registry that:

- requires at least one application-owned capability label for every registered tool;
- obtains fresh trusted actor and approval facts immediately before every invocation;
- calls Agent Ethics' `ToolGate` at that boundary;
- never invokes the tool on `deny`, `review`, malformed facts, provider failure, or audit failure;
- preserves the authorizing `Decision` for direct callers and normalizes failures into the
  framework's `ToolError` contract; and
- keeps Agent Ethics absent from the framework's default dependency-free install.

| Evidence | Value |
| --- | --- |
| Consumer owner | Samsarix LLC |
| Consumer repository | `Deathcharge/samsarix-agent-framework` (private as of 2026-08-01) |
| Consumer pull request | `#4`, merged 2026-08-01 |
| Consumer merge commit | `02fe13ae102359958b8a02d125a41abaa814d472` |
| Consumer contract head | `1e44b70be52bf19ae625f2eaba4a845a8afc6c8e` |
| Agent Ethics source pin | `eb69207b14ddd79bdfe774ec5b166c8ca8ce940e` (`0.1.0`) |
| Contract fixture | 10 policy-registry tests inside the consumer's 106-test suite |
| Hosted compatibility | Python 3.11-3.14 integration tests; Python 3.10 core-only test |
| Package evidence | separate base-wheel and `[ethics]` installed-wheel smoke tests |
| Support level | experimental until both repositories publish versioned releases |

The pull request and CI are visible to repository-authorized maintainers. Because the consumer is
private, this is owner-verifiable adoption evidence rather than a publicly reproducible third-party
case study. No production traffic, external customer, availability claim, or product-market fit is
inferred.

The compatibility window is the exact Agent Ethics commit above. Moving to another commit or
release requires the consumer contract suite and installed-wheel smoke tests to pass again. The
rollback path is to revert the consumer merge or restore its core `ToolRegistry`; removing the
policy gate is a security behavior change and requires an equivalent application authorization
boundary.

## Next validated gap: application-owned audit sinks

Post-adoption research favors a small audit-delivery seam over owning approval workflows, OAuth, or
policy distribution:

- [OpenAI Agents SDK tool guardrails](https://openai.github.io/openai-agents-python/guardrails/)
  already wrap function tools immediately before execution and re-run time-sensitive checks after
  approval.
- [Pydantic AI deferred tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/) already
  model in-process and external approval/pause flows, and explicitly warn that approval is not
  application authorization.
- [MCP authorization guidance](https://modelcontextprotocol.io/docs/tutorials/security/authorization)
  assigns token validation and per-tool scopes to established identity/resource-server controls.
- [OPA decision logs](https://www.openpolicyagent.org/docs/management-decision-logs) support remote
  services and custom plugins because production consumers need to route decisions into their own
  operational systems.

Agent Ethics should therefore keep making local deterministic decisions and expose one bounded,
metadata-only record to a caller-supplied sink. The first increment should preserve the current
JSONL path API, define an immutable public audit-record contract, call at most one configured sink
per decision, treat sink failure as non-authorization in `ToolGate`, and add no network or runtime
dependency. HTTP delivery, queues, retries, credentials, retention, and tamper-evident storage stay
with the embedding application until a concrete adopter validates a narrower requirement.
