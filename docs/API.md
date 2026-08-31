# API reference

All supported public names are exported from `samsarix_ethics`.

## Loading and evaluating

### `load_policy(path) -> Policy`

Reads a UTF-8 JSON policy with size and structural limits, rejects duplicate keys and invalid
values, and returns an immutable `Policy`. Raises `PolicyValidationError` for caller-correctable
policy failures.

### `load_context(path, *, stdin=None) -> dict[str, Any]`

Loads a bounded JSON object from a file, or from a binary stream when `path` is `None` or `"-"`.
Raises `InputValidationError`.

### `validate_context(value, *, label="evaluation input") -> Mapping[str, Any]`

Validates an in-memory object against the same depth, item-count, string-length, JSON-type, and
finite-number contract used for parsed input. Embedding applications can use it at their own input
boundary. `PolicyEngine.evaluate` calls it automatically.

### `load_context_contract(path) -> ContextContract`

Loads a bounded UTF-8 JSON application contract and returns an immutable `ContextContract`.
Contract files are limited to `MAX_CONTEXT_CONTRACT_BYTES` (256 KiB) and contain at most
`MAX_CONTEXT_CONTRACT_FIELDS` (1,000) declared dotted paths. Malformed contracts raise
`ContextContractValidationError`.

### `validate_policy_context_contract(policy, contract) -> None`

Rejects undeclared policy `field`/`$ref` paths and operator uses that are incompatible with declared
JSON types. `integer` and `number` are compatible; booleans remain distinct. The function returns
`None` after success and raises `ContextContractValidationError` on incompatibility.

### `validate_context_against_contract(context, contract) -> Mapping[str, Any]`

Applies normal bounded JSON validation, then enforces required declared paths, declared types, and
optional array-item types. Undeclared request fields are retained and accepted. Contract failures
raise `InputValidationError` and must be treated as non-authorization.

`ContextContract.from_dict(...)` and `.to_dict()` provide strict in-memory parsing and canonical
serialization. `ContextFieldType` contains `array`, `boolean`, `integer`, `null`, `number`,
`object`, and `string`. See [CONTEXT_CONTRACTS.md](CONTEXT_CONTRACTS.md).

### `PolicyEngine(policy, *, context_contract=None, deployment_lock=None).evaluate(context) -> Decision`

Evaluates every rule deterministically. Raises `InputValidationError` when the context is not a
bounded JSON object and `EvaluationError` if an operator cannot safely evaluate the supplied types
or a `$ref` is missing. Construction computes `policy_fingerprint` once for reuse by every
decision.

When a contract is supplied, construction validates policy compatibility and every evaluation
enforces the contract before rule matching. The immutable contract and its canonical fingerprint
are exposed as `engine.context_contract` and `engine.context_contract_fingerprint`. When a
`DeploymentLock` is supplied, construction verifies exact policy and contract identity/content
before evaluation and exposes it as `engine.deployment_lock`.

### `PolicyEngine(policy).evaluate_many(contexts) -> tuple[Decision, ...]`

Evaluates up to `MAX_BATCH_ITEMS` (1,000) contexts in input order. The first malformed context
raises `InputValidationError` with its zero-based batch index; policy evaluation errors still fail
closed. An empty batch returns an empty tuple.

`Decision` fields:

| Field | Meaning |
| --- | --- |
| `decision_id` | UUID generated for this evaluation |
| `evaluated_at` | UTC ISO 8601 timestamp |
| `policy_id`, `policy_version` | operator-authored policy identity labels |
| `policy_fingerprint` | exact canonical policy content used, as `v1:sha256:<hex>` |
| `outcome` | `Outcome.ALLOW`, `DENY`, or `REVIEW` |
| `allowed` | true only for `ALLOW` |
| `matched_rules` | matching rule IDs in priority/ID order |
| `warnings` | messages from matched warning rules |
| `reasons` | messages that determined the outcome |
| `evaluated_rules` | total rule count |

`Decision.to_dict()` returns a JSON-serializable dictionary and still excludes the raw input.

### `PolicyEngine(...).explain(context) -> PolicyExplanation`

Uses the same bounded validation, context contract, deployment lock, short-circuit condition
evaluation, error behavior, precedence, and default as `evaluate`. The deterministic report binds
the policy fingerprint and optional context-contract fingerprint and records rule/condition status
without input, condition values, `$ref` targets, descriptions, messages, UUIDs, or timestamps.

`PolicyExplanation.rules` contains declaration-ordered frozen `RuleExplanation` values. Each has
frozen `ConditionExplanation` entries with `MATCHED`, `NOT_MATCHED`, or `NOT_EVALUATED` status.
Matched rule IDs retain normal priority/ID order; `decisive_rule_ids` identifies matches whose
allow/deny/review effect supplied the outcome. `default_applied` is true when no decisive rule
matched. See [POLICY_EXPLANATIONS.md](POLICY_EXPLANATIONS.md).

### `fingerprint_policy(policy) -> str`

Returns the authoritative `v1:sha256:<hex>` fingerprint of a validated `Policy`. The canonical
payload includes every serialized policy field and a fingerprint-version domain separator. JSON
object keys are sorted; array order is retained, so rule and condition order remain part of exact
provenance. Serialization streams through the hash without building a second encoded byte buffer.
`PolicyEngine`, `ToolGate`, and `BoundToolGate` expose the same precomputed value as
`policy_fingerprint`; callers should use this helper instead of implementing their own serializer.

### `fingerprint_context_contract(contract) -> str`

Returns the authoritative `v1:sha256:<hex>` fingerprint for a validated `ContextContract`.
Canonical JSON uses sorted object keys, retains field semantics after strict model normalization,
and includes a context-contract-specific fingerprint-version domain separator. The textual format
matches policy fingerprints, but the distinct canonical domain prevents cross-artifact reuse.

## Exact deployment locks

### `create_deployment_lock(policy, context_contract=None) -> DeploymentLock`

Creates a frozen version 1 artifact containing policy ID, version, and canonical fingerprint plus
the same metadata for an optional context contract. `DeploymentLock.to_dict()` returns the strict
JSON shape; `DeploymentLock.from_dict(value)` validates that shape without claiming the referenced
artifacts match.

### `verify_deployment_lock(lock, policy, context_contract=None) -> None`

Recomputes canonical metadata and rejects any ID, version, fingerprint, or contract-presence
mismatch with `DeploymentLockValidationError`. Comparisons use constant-time digest comparison.
`PolicyEngine` and `ToolGate` accept the same optional lock and verify it at construction.

### `load_deployment_lock(path) -> DeploymentLock`

Loads a strict UTF-8 JSON lock with the 64 KiB `MAX_DEPLOYMENT_LOCK_BYTES` limit and shared JSON
structural limits. File and model errors are reported as `DeploymentLockValidationError`. See
[DEPLOYMENT_LOCKS.md](DEPLOYMENT_LOCKS.md) for the rollout and trust model.

## Single-file policy deployments

### `create_policy_deployment(policy, context_contract=None) -> PolicyDeployment`

Creates an immutable version 1 deployment containing the complete policy, optional complete
contract, and a newly derived mandatory `DeploymentLock`. Incorrect Python argument types raise
`TypeError`. `PolicyDeployment.to_dict()` returns a fresh complete JSON document;
`PolicyDeployment.from_dict(value)` strictly parses all nested models and raises
`PolicyDeploymentValidationError` unless the embedded lock exactly matches them.

### `load_policy_deployment(path) -> PolicyDeployment`

Reads one UTF-8 JSON object under the 4 MiB `MAX_POLICY_DEPLOYMENT_BYTES` limit, shared structural
limits, and duplicate-key rejection, then parses and verifies it. A single read prevents mixed
policy/contract/lock snapshots during local rollout. File, nested-model, and lock failures are
reported as `PolicyDeploymentValidationError`.

### `write_policy_deployment(path, deployment, *, force=False) -> Path`

Serializes the complete deployment deterministically, flushes a temporary file, and atomically
installs it. It refuses an existing or concurrently won target unless `force=True`; forced output
uses atomic replacement. The parent directory must already exist.

`samsarix-ethics deployment create/verify` exposes the same workflow with value-minimized text or
JSON metadata, while `check` and `explain` can consume the deployment directly with
`--deployment`. Those evaluation commands reject separate contract or lock arguments in
deployment mode. The CLI reports only exact artifact metadata and lock status, not policy content.
The deployment proves internal equality, not authorship, freshness, transport security, or
approval. See
[POLICY_DEPLOYMENTS.md](POLICY_DEPLOYMENTS.md).

## Atomic live policy runtime

### `PolicyRuntime(policy, *, context_contract=None, deployment_lock=None)`

Constructs generation `1` from one complete enforcement configuration. Construction has the same
policy/contract compatibility and exact deployment-lock checks as `PolicyEngine`. `evaluate`,
`explain`, and the `policy`, fingerprint, contract, and lock properties mirror the engine API.
`evaluate_many` captures one generation for the whole bounded batch.

`PolicyRuntime.from_deployment(deployment)` constructs generation `1` from a verified
`PolicyDeployment`; `activate_deployment(deployment, expected_generation=None)` activates one
through the same compare-and-swap, last-known-good path.

Every call captures one immutable engine under a short lock and evaluates after releasing it. An
in-flight call therefore finishes on its original generation while later calls can use a newly
activated generation.

### `PolicyRuntime.activate(policy, *, context_contract=None, deployment_lock=None, expected_generation=None) -> PolicyRuntimeStatus`

Builds and validates the complete candidate before acquiring the live-state lock, then swaps the
policy, contract, lock, and fingerprints together. Candidate validation/lock errors leave the last
successful generation untouched. A supplied positive `expected_generation` is compared under the
same lock; a stale value raises `PolicyActivationError` without activation. Every successful
activation increments the process-local generation, including rollback to retained prior
artifacts.

### `PolicyRuntime.status -> PolicyRuntimeStatus`

Returns one coherent frozen snapshot with `POLICY_RUNTIME_STATUS_VERSION` (currently `1`),
generation, UTC activation time, exact policy identity/fingerprint, optional exact contract
identity/fingerprint, and `deployment_lock_verified`. `to_dict()` returns the bundled schema shape
without policy content, action input, decisions, or errors. See
[POLICY_RUNTIME.md](POLICY_RUNTIME.md) for concurrency, rollback, and control-plane boundaries.

### `write_policy(path, policy, *, force=False) -> Path`

Atomically writes a validated `Policy` as UTF-8 JSON and returns the resolved output path. It
refuses to overwrite an existing path unless `force=True` and requires the parent directory to
exist. Raises `PolicyValidationError` for caller-correctable filesystem failures.

## Layered policy composition

### `compose_policies(policies, *, policy_id, policy_version, description="") -> PolicyComposition`

Combines 1-`MAX_COMPOSED_POLICIES` (32) validated policies in supplied order. Source IDs and all
rule IDs must be unique, all sources must share one `default_effect`, and the result must remain
within the normal 1,000-rule, 1 MiB serialized, and structural policy limits. Violations raise
`PolicyCompositionError`; incorrect Python argument types raise `TypeError`.

`PolicyComposition.policy` is an ordinary immutable `Policy`, so it can immediately enter
`PolicyEngine`, `ToolGate`, lint, regression, coverage, and comparison workflows.
`PolicyComposition.sources` is an ordered tuple of frozen `PolicyCompositionSource` records.
`policy_fingerprint` exposes the target's canonical fingerprint. `to_dict()` returns a versioned
report with approved metadata including the target default effect, target/source IDs, versions,
fingerprints, and rule counts. It omits paths, descriptions, rules, conditions, messages, and
condition values.

The CLI equivalent is `samsarix-ethics compose --id ... --version ... --policy SOURCE ...
--output TARGET`. Output replacement requires `--force`. See
[POLICY_COMPOSITION.md](POLICY_COMPOSITION.md) for the complete contract and support-agent example.

## Shadow policy rollout

### `PolicyShadowEvaluator(baseline, candidate, *, context_contract=None).evaluate(context) -> PolicyShadowEvaluation`

Validates and detaches one bounded JSON context, evaluates the baseline first, and evaluates the
candidate only after the baseline succeeds. Baseline input/evaluation errors propagate fail closed.
A candidate `SamsarixEthicsError` becomes `status = PolicyShadowStatus.ERROR` telemetry without
replacing the baseline decision; unexpected exceptions propagate.
When supplied, one shared context contract validates both policies at construction and both engine
evaluations. Baseline contract input errors propagate fail closed before candidate evaluation;
candidate policy evaluation errors retain the existing observational telemetry behavior.

`PolicyShadowEvaluation.authoritative_decision` is the complete baseline `Decision` that the
application may enforce. `candidate_decision` is a complete observational `Decision` after success
or `None` after a candidate-domain error. `status` is `UNCHANGED`, `CHANGED`, or `ERROR`; `changes`
contains `PolicyShadowChange` labels for outcome, matched rules, warning count, reason messages,
and warning messages. `authorization_changed` is true exactly when the outcome changed.

`candidate` is the frozen input-free `PolicyShadowSnapshot`. It always retains candidate policy
ID, version, and exact fingerprint. A successful snapshot also carries decision ID, evaluation
time, outcome, matched-rule IDs, warning count, and evaluated-rule count. An error snapshot carries
the bounded engine error while unavailable decision fields are null. Both snapshot forms include
the monotonic engine-only `evaluation_duration_ns`; candidate errors retain time spent before the
failure.

`to_dict()` returns the `POLICY_SHADOW_VERSION` (currently `1`) report with a successful baseline
snapshot and either a successful candidate snapshot or a candidate-error snapshot. It excludes the
complete input and all reason/warning text; those message values are compared only in memory. The
synchronous second evaluation may add latency and resource use. Sampling, telemetry delivery,
promotion, and rollback remain caller responsibilities. See
[POLICY_SHADOWING.md](POLICY_SHADOWING.md).

## Tool-call enforcement

### `fingerprint_tool_call(tool_call_id, tool_name, arguments, *, capabilities=(), actor=None)`

Returns a `v1:sha256:<hex>` fingerprint over the normalized framework call ID, tool-context
version, tool name, validated arguments, canonical capability list, and actor. Canonical input is
streamed through the hash and limited to `MAX_TOOL_CALL_FINGERPRINT_BYTES` (1 MiB). Invalid or
oversized calls raise `InputValidationError`. Runtime context is deliberately excluded so fresh
authentication, risk, and environment facts can be re-read before execution.

### `ToolCallApproval(tool_call_id, approved, tool_call_fingerprint)`

A frozen versioned record that binds an approve/deny result to one framework call ID and one tool
fingerprint. `from_dict(value)` strictly parses the bundled JSON shape and `to_dict()` returns a
detached value. Parsing validates structure only; applications must authenticate the reviewer and
load the fingerprint from protected server-side pending-call state.

### `build_tool_context(tool_name, arguments, *, capabilities=(), actor=None, context=None, tool_call_id=None, approval=None)`

Builds a detached, bounded JSON context using the versioned shape documented in
[TOOL_CALLS.md](TOOL_CALLS.md). Tool and capability identifiers are 1-128 characters; each call
may declare up to `MAX_TOOL_CAPABILITIES` (64) unique capabilities. The returned context uses
`tool_context_version = TOOL_CONTEXT_VERSION` (currently `1`), uses
`action.kind = "tool_call"`, and never retains the caller's mutable dictionaries. When an approval
is supplied, the current framework `tool_call_id` is required. The builder recomputes the
fingerprint with constant-time comparisons of both ID and digest before adding the structured
approval to `context`. A `tool_call_id` without approval is rejected rather than silently ignored.
The `context.approval` field is reserved and cannot be injected through ordinary context metadata.

### `ToolCatalog.from_dict(value)` / `load_tool_catalog(path)`

Parse a bounded tool-catalog v1 document containing an application-owned ID/version and 1-256
unique local tool names. Every tool declares 1-64 unique capability identifiers. Tool entries and
capabilities are normalized into canonical sorted tuples; unknown fields, duplicate names, empty
labels, and malformed or oversized JSON fail with `ToolCatalogValidationError`.

`ToolCatalog.tool_names` returns the canonical name tuple, `get(name)` returns one immutable
`ToolCatalogEntry`, and `to_dict()` returns fresh canonical JSON containers.
`fingerprint_tool_catalog(catalog)` produces a domain-separated
`v1:sha256:<lowercase-hex>` identity. Input ordering does not affect it; any semantic metadata
change does.

`validate_tool_catalog_registration(catalog, registered_tools)` validates a bounded iterable of
trusted local registry names and returns its sorted tuple only when the name set exactly matches the
catalog. Missing cataloged tools, uncataloged registered tools, duplicates, invalid names, and
oversized snapshots fail closed.

### `ToolGateDeployment` / `create_tool_gate_deployment(...)`

`ToolGateDeployment` packages one internally verified `PolicyDeployment`, one immutable
`ToolCatalog`, and the catalog's matching canonical fingerprint. `from_dict` rejects unknown or
missing fields, invalid nested artifacts, and fingerprint mismatch; `to_dict` returns fresh
containers. `load_tool_gate_deployment` reads at most `MAX_TOOL_GATE_DEPLOYMENT_BYTES` and
`write_tool_gate_deployment` provides atomic no-overwrite-by-default output.

`ToolGate.bind_deployment(deployment, *, registered_tools, audit_log=None, audit_sink=None)` creates
the gate from the embedded policy deployment and returns a `BoundToolCatalog` only after complete
registry matching succeeds. This is internal coherence and equality evidence, not authentication.

### `ToolDispatcher.bind_catalog(...)` / `ToolDispatcher.bind_deployment(...)`

Create an immutable framework-neutral execution registry from a complete mapping of trusted local
names to final Python callbacks. `bind_catalog` accepts an existing `ToolGate` and `ToolCatalog`;
`bind_deployment` constructs the gate from one coherent `ToolGateDeployment` and accepts the same
optional audit configuration. Both exact-match catalog and mapping names, reject non-callables,
copy the mapping, and retain the selected callable objects.

`prepare` uses the trusted binding for a model-selected name. Batch execution rechecks every
prepared name and capability tuple against those bindings before evaluation. `execute` and
`execute_async` authorize one call and invoke the frozen callback with detached keyword arguments.
`execute_many`
and `execute_many_async` authorize the complete bounded batch before invoking callbacks
sequentially in input order. They return `ToolExecutionResult` objects carrying each authorizing
decision and callback value.

The synchronous path rejects an awaitable result; the async path requires one. Callback errors are
not hidden. Batch preflight is not transactional, so an error from a later callback does not undo
earlier side effects. The snapshot prevents replacement in the supplied mapping, but does not
authenticate callable code, freeze closure/global/object state, or protect a callback that performs
a new mutable registry lookup. See [TOOL_DISPATCH.md](TOOL_DISPATCH.md).

### `ToolGate(policy_or_runtime, *, context_contract=None, deployment_lock=None, audit_log=None, audit_sink=None)`

Provides a fail-closed boundary immediately before an in-process side effect:

When `context_contract` is supplied, gate construction validates the policy and every normalized
tool-call context is checked before evaluation. When `deployment_lock` is supplied, exact artifact
verification occurs during construction. `ToolGate` and `BoundToolGate` expose
`context_contract`, `context_contract_fingerprint`, and `deployment_lock`.

Passing a `PolicyRuntime` makes the gate and all existing bindings follow successful atomic
activations. Contract and lock arguments must then be configured on the runtime rather than passed
again. `runtime_status` returns coherent live-generation metadata for a runtime-backed gate and
`None` for a static gate.

`ToolGate.explain(...)` normalizes the same call fields and returns a `PolicyExplanation` without
authorizing, executing, or emitting an authorization audit record. `BoundToolGate.explain(...)`
uses its immutable registered tool name and capabilities.

- `bind(tool_name, *, capabilities=()) -> BoundToolGate` validates and freezes trusted
  registration metadata once;
- `bind_catalog(catalog, *, registered_tools) -> BoundToolCatalog` first requires the catalog to
  exactly match a trusted complete registry-name snapshot, then freezes every binding;
- `bind_deployment(deployment, *, registered_tools, ...) -> BoundToolCatalog` constructs the gate
  from one coherent policy-and-catalog unit and performs the same exact registry check;
- `prepare(...) -> PreparedToolCall` validates, detaches, and recursively freezes one call for
  immediate single-generation batch authorization;
- `evaluate(...) -> Decision` evaluates the normalized call and optionally appends audit metadata;
- `evaluate_many(calls) -> tuple[Decision, ...]` validates a bounded gate-specific prepared batch,
  pins one runtime generation, then emits audit records in input order;
- `enforce(...) -> Decision` returns only an allow decision, otherwise raising a typed block;
- `enforce_many(calls) -> tuple[Decision, ...]` returns only when every prepared call is allowed,
  otherwise raising the first input-ordered typed block after the full batch was evaluated/audited;
- `execute(..., executor, ...) -> ToolExecutionResult[T]` invokes a callback with the detached,
  evaluated argument dictionary only after allow; it rejects coroutine functions and async
  callable objects, which must use `execute_async`;
- `await execute_async(..., executor, ...) -> ToolExecutionResult[T]` does the same for an async
  callback.

Each method accepts the optional `tool_call_id=...` and `approval=ToolCallApproval(...)` keywords;
they must be supplied together. An ID or fingerprint mismatch raises `InputValidationError` before
a decision, audit record, or callback exists. The gate does not authenticate, expire, or consume
approvals; applications own those stateful responsibilities.

`ToolExecutionResult` contains the authorizing `decision` and callback `value`. A deny raises
`ToolCallDeniedError`; review raises `ToolCallReviewRequiredError`. Both derive from
`ToolCallBlockedError`, retain the metadata-only `decision`, and omit tool arguments from their
messages. Every blocked-call exception also exposes an ordered metadata-only `decisions` tuple and
the `blocking_index` whose item is available as `decision`. Single-call enforcement uses a
one-item tuple at index zero. Batch enforcement retains every result from its one evaluation, so a
framework can populate a complete review surface without re-evaluating, changing decision IDs, or
re-emitting audit records. If configured audit persistence fails, `AuditLogError` propagates before
execution.
`audit_log` and `audit_sink` are mutually exclusive. A custom sink must be a synchronous callable
that accepts one `AuditRecord` and returns `None`; any other return or raised exception prevents the
decision from authorizing a callback. The package invokes the sink exactly once and never retries.

### `BoundToolGate`

The frozen object returned by `ToolGate.bind(...)`. Its `tool_name` and canonical immutable
`capabilities` tuple cannot be supplied or changed per invocation. It exposes `gate` and `policy`
properties, the gate's `policy_fingerprint`, plus
`runtime_status`,
`fingerprint(tool_call_id, arguments, *, actor=None)`, `prepare`, `evaluate`, `enforce`, `explain`,
`execute`, and `execute_async`. The latter six accept the same actor, context, call-ID, and approval keywords as
`ToolGate`, but take only arguments (and an executor where applicable).

Use a trusted application registry to select a binding. This prevents model or protocol payloads
from downgrading capability labels, but it does not establish that remote tool metadata is honest.

### `create_openai_agents_tool_policy(binding, *, actor_provider=None, context_provider=None, approval_store=None)`

Creates an optional `OpenAIAgentsToolPolicy` for one `BoundToolGate`. Construction imports the
OpenAI Agents SDK only when called; otherwise the core package retains zero runtime dependencies.
`actor_provider` and `context_provider` are synchronous callbacks from the SDK application context
to current application-owned JSON facts.

`approval_store` satisfies `OpenAIAgentsApprovalStore`: synchronous `remember` atomically retains
and returns the first exact-call fingerprint, `get` returns it without creation, and `forget`
removes it after the SDK resolves the call. The bounded thread-safe in-memory default reports
exhaustion at `MAX_PENDING_OPENAI_APPROVALS` (4,096), reclaims resolved entries, and fails closed
after reconstruction. Durable SDK run state requires a protected application-owned implementation.

`adapter.protect(tool)` returns a copied strict, top-level SDK `FunctionTool`, preserves its existing
input guardrails and approval logic, and appends Samsarix enforcement. It raises
`OpenAIAgentsIntegrationError` for unsupported or incompatible tool shapes. The adapter version is
`OPENAI_AGENTS_ADAPTER_VERSION`. See [OPENAI_AGENTS.md](OPENAI_AGENTS.md) for the exact execution
boundary and approval workflow.

### `create_langchain_tool_policy(bindings, *, actor_provider=None, context_provider=None)`

Creates an optional `LangChainToolPolicy` for one exact `BoundToolCatalog`. Construction imports
LangChain only when called. `validate_tools(tools)` requires real `BaseTool` instances whose names
exactly match the catalog. `middleware` is the sync/async `AgentMiddleware` instance and must be
last in LangChain's middleware list so it sees the final request after outer transformations.

The providers are synchronous callbacks from `request.runtime.context` to current application-
owned JSON facts. `explain(request)` performs an unaudited policy explanation and
`approval_for(request, approved=...)` creates unsigned exact-call evidence for a caller-owned
review system; neither method authenticates a reviewer or authorizes execution.

Allow invokes the original handler once after an audited enforcement. Deny raises the ordinary
typed gate error. Review calls LangGraph `interrupt()` with
`LANGCHAIN_REVIEW_INTERRUPT_TYPE = "samsarix.tool_call.review"`; an approved resume must be a
strict `ToolCallApproval` dictionary matching the current call fingerprint before final
enforcement. Rejection returns a generic error `ToolMessage` without invoking the tool. The adapter
contract version is `LANGCHAIN_ADAPTER_VERSION = 1`. See [LANGCHAIN.md](LANGCHAIN.md).

### `create_pydantic_ai_tool_policy(bindings, toolset, *, actor_provider=None, context_provider=None, approval_store=None)`

Creates an optional `PydanticAIToolPolicy` for one exact `BoundToolCatalog` and one real Pydantic
AI `AbstractToolset`. Construction imports Pydantic AI only when called. `toolset` returns a public
`WrapperToolset` subclass suitable for `Agent(toolsets=[...])`; every run step must expose an exact
catalog-matching dictionary of real `ToolsetTool` objects, and execution must resolve to the
snapshotted object.

Providers are synchronous callbacks from `RunContext.deps` to fresh application-owned JSON facts.
`approval_store` implements `PydanticAIApprovalStore.remember(...)` and atomic `.consume(...)`.
The bounded thread-safe process-local default retains at most
`MAX_PENDING_PYDANTIC_AI_APPROVALS` (4,096) pending calls and fails closed after reconstruction;
durable workflows supply protected application-owned state.
Allow delegates once after audited enforcement. Deny raises the typed gate error. Review raises
native `ApprovalRequired` with `PYDANTIC_AI_REVIEW_METADATA_KEY` metadata.
`build_results(requests, decisions)` validates selected deferred calls and creates either
fingerprint-bound `PYDANTIC_AI_APPROVAL_METADATA_KEY` evidence or a generic `ToolDenied` result.
A native boolean approval without this evidence fails closed, and approved resume re-enforces the
current call and policy. The adapter contract version is `PYDANTIC_AI_ADAPTER_VERSION = 1`. See
[PYDANTIC_AI.md](PYDANTIC_AI.md).

### `create_mcp_server_tool_policy(bindings, tools, tool_handler, *, application_context_provider=None, actor_provider=None, context_provider=None, approval_provider=None)`

Creates an optional `MCPServerToolPolicy` for the stable MCP Python SDK low-level server. MCP is
imported only when this factory is called. `tools` must be a complete registry of valid real
`mcp.types.Tool` objects; catalog matching uses their names. Definitions are deep-copied at
construction, and `policy.tools` returns fresh copies for the server's `list_tools` handler.

Register `policy.call_tool` with `Server.call_tool()` using its default schema validation. Each
schema-valid invocation bounds and detaches arguments, obtains fresh request-scoped application,
actor, and context values, and authorizes immediately before calling the async `tool_handler` once.
Allow delegates, deny blocks, and review optionally awaits the application-owned provider.

The provider receives an immutable `MCPToolReviewRequest`, whose detached `arguments`, redacted
representation, sensitive `to_dict()`, and `approval(approved=...)` helper bind a fresh one-shot
call ID and exact fingerprint. Reviewer authentication, confidentiality, expiry, timeout, and
cancellation remain application-owned. The adapter contract version is
`MCP_SERVER_ADAPTER_VERSION = 1`; integration failures raise `MCPServerIntegrationError`. See
[MCP.md](MCP.md) for the exact supported and unsupported execution paths.

### `await create_mcp_client_tool_policy(bindings, client, *, server_id, ...)`

Creates an optional `MCPClientToolPolicy` for a connected MCP 2.1.1 `Client`. Install the
`mcp-client` extra separately from the v1 `mcp` server extra. The async factory pins the complete
paginated tool definitions and checks exact trusted-catalog membership. `tools` returns detached
copies; `registry_fingerprint` identifies canonical snapshot content, not server authenticity.

Optional synchronous `actor_provider()` and `context_provider()` supply fresh application facts.
Async `approval_provider(review)` receives `MCPClientReviewRequest`, with detached sensitive
`request`/`to_dict()` payloads and `approval(approved=...)` evidence. Review binds the server alias,
registry, actor, tool, arguments, metadata and continuation state to a fresh invocation ID. Fresh
discovery/facts and final current-policy enforcement follow review. Rejection cannot dispatch.

`await adapter.call_tool(name, arguments=None, read_timeout_seconds=None, progress_callback=None,
*, input_responses=None, request_state=None, meta=None)` sends at most one tools/call round through
the captured public session. `InputRequiredResult` is returned for explicit reauthorization; no
high-level input driver or retries run. `context.mcp` is reserved for the server/registry identity
and supplied metadata/continuation facts. Timeouts default to 30 seconds per discovery/dispatch
and 300 seconds per review; values must be finite in `(0, 3600]`.

`MCP_CLIENT_ADAPTER_VERSION = 1`; integration failures raise `MCPClientIntegrationError`, ordinary
policy blocks retain typed gate errors, and SDK exceptions/cancellation propagate. See
[MCP_CLIENT.md](MCP_CLIENT.md) for audit timing, limits, incompatible extras and transport ownership.

### `create_mcp_http_transport(transport, *, max_wire_bytes=4194304, max_response_bytes=4194304)`

Creates an optional `MCPHTTPTransport` for an unshared, application-owned HTTPX2 2.12.0 async
transport. The wrapper owns its supplied transport and implements async HTTP dispatch/context
management/`aclose()`. Configure it before opening the MCP Client; existing sessions are not
modified. Budgets must be integers in `[1, 67108864]` and count per-response encoded/decoded body
bytes, including the complete lifetime of an SSE response. It adds no retry or log sink.

`max_wire_bytes` and `max_response_bytes` are read-only properties. `failure_reason` is initially
`None`; a local contract violation latches it and prohibits further underlying HTTP dispatch.
Reasons are `wire_bytes`, `decoded_bytes`, `invalid_content_length`, `unsupported_encoding`,
`invalid_content_encoding`, `response_not_streaming`, or `invalid_stream`. An ordinary network
failure or cancellation is not a budget failure. A closed wrapper rejects reuse with
`MCPHTTPResponseError("transport_closed")`.

`MCPHTTPResponseError.reason` contains a diagnostic label, not response/request data. Factory
dependency errors use `install_mcp_client_extra` or `unsupported_httpx2_version`; invalid budgets
raise `ValueError`, and an invalid wrapped transport raises `TypeError`. SDK task groups may
wrap/translate transport exceptions. Read `failure_reason` from the application-owned wrapper
when interpreting failure; do not trust a remote error message as local evidence.

The contract version is `MCP_HTTP_RESPONSE_BUDGET_VERSION = 1` and the default constant is
`DEFAULT_MCP_HTTP_RESPONSE_BYTES = 4194304`. Limits apply before MCP JSON/SSE parsing, not before
all HTTP parser/decoder allocations. Identity, gzip and deflate are supported, with no stacked
codings. See [MCP_CLIENT.md](MCP_CLIENT.md#response-budgets-and-recovery) for ownership, memory,
cleanup, failure recovery, header changes, and proxy/mount bypass limits.

### `BoundToolCatalog`

The immutable mapping returned by `ToolGate.bind_catalog(...)`. It exposes `gate`, `catalog`,
`catalog_fingerprint`, canonical `tool_names`, mapping iteration, and name lookup returning a
`BoundToolGate`. Its representation includes only catalog ID/version and tool count. Construction
is gate-owned, and the internal mapping cannot be mutated.

Exact matching prevents a registry tool from silently bypassing the reviewed catalog and prevents
stale catalog entries from creating bindings for absent tools. The caller must supply the complete
name snapshot from a trusted local registry; the package does not inspect framework objects or
trust model/provider/MCP discovery data. The fingerprint proves content equality, not authorship,
freshness, or capability correctness.

### `PreparedToolCall`

The frozen gate-specific object returned by `ToolGate.prepare(...)` or
`BoundToolGate.prepare(...)`. `tool_name` and `capabilities` expose immutable normalized metadata;
`arguments` returns a fresh detached dictionary on every access. Its constructor is intentionally
unavailable. A prepared call retains normalized actor/context/approval facts internally for
immediate `evaluate_many` or `enforce_many` use; it is not a durable authorization token and must
not be reused after those facts can become stale. A batch rejects repeated object identities and
repeated approval `tool_call_id` values; applications still enforce replay protection across
batches. `MAX_TOOL_BATCH_ITEMS` is 1,000.

## Authenticated deployment envelopes

### `fingerprint_tool_gate_deployment(deployment) -> str`

Returns the domain-separated `v1:sha256` fingerprint of the complete coherent policy, contract,
lock, and tool catalog deployment. It is exact-content identity, not authentication by itself.

### `authenticate_tool_gate_deployment(deployment, key, *, key_id, audience, sequence, issued_at, expires_at)`

Returns an untrusted-when-received `ToolGateDeploymentEnvelope` containing the full deployment and
an HMAC-SHA-256 over `unsigned_dict()`, which contains every non-MAC envelope field. Keys are copied
from 32-4096 byte bytes-like values.
Timestamps use strict whole-second UTC RFC 3339 form; expiry must follow issuance and the lifetime
cannot exceed 30 days. Creation proves only that the supplied key produced the envelope.
`generate_deployment_auth_key()` returns a fresh 32-byte key suitable for this API; secret storage,
permissions, and rotation remain caller responsibilities.

### `ToolGateDeploymentEnvelope.from_dict(value)` and `ToolGateDeploymentEnvelope.to_dict()`

Strictly parse or detach the version 1 envelope. Parsing validates structure, timestamps, nested
deployment consistency, and exact fingerprint equality but deliberately does not trust the MAC,
audience, sequence, or current time. `unsigned_dict()` returns the exact fields covered by the MAC.

### `verify_tool_gate_deployment_envelope(envelope, keys, *, expected_audience, minimum_sequence=1, now=None, clock_skew_seconds=0)`

Selects `envelope.key_id` from a bounded caller-owned keyring, verifies the MAC in constant time,
then enforces the exact audience, caller-protected minimum sequence, issuance, and expiry. `now`
must be timezone-aware when supplied; clock skew is explicitly bounded to 0-3600 seconds. It
returns `VerifiedToolGateDeployment`, including value-minimized verification metadata and the
authenticated deployment. Failures raise `DeploymentAuthenticationError`.

### `load_tool_gate_deployment_envelope(path)` and `write_tool_gate_deployment_envelope(path, envelope, *, force=False)`

Parse or atomically write the strict bounded 5 MiB envelope document. Loading is not
authentication. Output refuses implicit or concurrently won overwrite unless `force=True`.

### `ToolGate.bind_authenticated_deployment(...)` and `ToolDispatcher.bind_authenticated_deployment(...)`

Authenticate a current envelope immediately before constructing the gate or freezing callback
references. Both require a keyring, expected audience, complete registry, and optional minimum
sequence/time/skew inputs. The same catalog exact-match and fail-closed enforcement behavior then
applies. The returned binding or dispatcher retains the immutable `VerifiedToolGateDeployment` on
its read-only `authenticated_deployment` property so operators can inspect the authorizing key ID,
sequence, verification time, and deployment fingerprint. These methods avoid treating a cached
historical verification as current authorization.

See [authenticated deployments](AUTHENTICATED_DEPLOYMENTS.md) for rotation and threat boundaries.

## Models

- `Policy.from_dict(value)` and `Policy.to_dict()`
- `PolicyRule.from_dict(value, index=...)` and `PolicyRule.to_dict()`
- `PolicyCondition.from_dict(value, location=...)` and `PolicyCondition.to_dict()`
- `Effect`: `allow`, `deny`, `review`, `warn`, `audit`
- `Outcome`: `allow`, `deny`, `review`
- `ToolCallApproval.from_dict(value)` and `ToolCallApproval.to_dict()`

Models are frozen dataclasses. Policy condition arrays and objects are recursively frozen, and
`to_dict()` returns fresh JSON containers, so retaining or serializing a source document cannot
mutate a live policy. Construct policies through `from_dict` or `load_policy` so validation always
runs.

## Schemas and policy regression tests

### `get_policy_schema()`, `get_context_contract_schema()`, and other schema accessors

Return fresh dictionaries containing the bundled Draft 2020-12 schemas for policies, application
context contracts, deployment locks, policy deployments, regression suites, comparison,
composition, coverage, explanation, lint, runtime-status, and shadow reports, the normalized
tool-call context, bound approval records, trusted tool catalogs, metadata-only audit records, and
coherent tool-gate deployments. The other accessors are
`get_policy_test_schema`, `get_policy_comparison_schema`, `get_policy_composition_schema`,
`get_policy_coverage_schema`, `get_policy_explanation_schema`, `get_policy_lint_schema`,
`get_policy_runtime_status_schema`, `get_policy_shadow_schema`, `get_deployment_lock_schema`,
`get_policy_deployment_schema`, `get_tool_context_schema`, `get_tool_approval_schema`,
`get_tool_catalog_schema`, `get_tool_gate_deployment_schema`,
`get_tool_gate_deployment_envelope_schema`, `get_audit_record_schema`,
`get_audit_chain_entry_schema`, and `get_audit_chain_verification_schema`. These calls perform no
network access and callers may mutate a returned
value without changing future calls.

### `load_policy_test_suite(path) -> PolicyTestSuite`

Loads a UTF-8 JSON suite with a 4 MiB byte limit and the shared JSON structural limits. Suites
contain 1-1,000 uniquely named cases. Raises `PolicyTestValidationError` for malformed suites.

### `run_policy_tests(policy, suite, *, context_contract=None) -> PolicyTestReport`

Evaluates every case and records `PolicyTestStatus.PASS`, `FAIL`, or `ERROR`. A report includes
operator-authored policy identity, its exact policy fingerprint, counts, expected and actual
outcomes, matched rule IDs, assertion messages, and evaluation errors. It deliberately excludes
every raw case input. `successful` is true only when all cases pass.

`PolicyTestCase`, `PolicyTestSuite`, `PolicyTestResult`, and `PolicyTestReport` are frozen public
models with JSON-serializable `to_dict()` methods.
An optional context contract is validated when the engine is constructed and applied to every
case. Per-case contract input failures are input-free `ERROR` results.

## Policy authoring diagnostics

### `lint_policy(policy, *, fail_on=PolicyLintSeverity.SECURITY_WARNING) -> PolicyLintReport`

Returns stable, value-minimized findings for a validated policy. `fail_on` accepts a
`PolicyLintSeverity` or `None`; `passed` is false when a finding at or above the selected severity
exists. `None` reports without blocking. The report includes `POLICY_LINT_VERSION` (currently `1`),
policy identity/fingerprint, severity counts, blocking count, and frozen `PolicyLintFinding`
objects with a `PolicyLintCode`, rule ID, and zero-based condition indices.

The analyzer reports default/unconditional allow, provably contradictory same-field conditions,
semantically duplicate conditions, and missing authored messages. It does not serialize condition
values or rule messages, infer an application schema, or guess about dynamic `$ref` equality. Use
an explicit `ContextContract` for supported path/type validation; the linter itself remains
contract-independent.

The CLI equivalent is `samsarix-ethics lint POLICY --fail-on SEVERITY`. It exits `0` when the
selected gate passes, `1` for blocking findings, and `2` for invalid input or invocation. See
[POLICY_LINTING.md](POLICY_LINTING.md) for stable code definitions and limitations.

## Policy rule coverage

### `measure_policy_coverage(policy, suite, *, threshold=0, context_contract=None) -> PolicyCoverageReport`

Evaluates each bounded suite input against one policy and records which rule IDs matched. The
integer threshold must be from `0` to `100`. `threshold_met` is true only when exact covered/total
counts meet that threshold and every case evaluated successfully. `complete` requires every rule
to be covered and no errors. The suite's `expected_*` assertions are not checked; use
`run_policy_tests` for correctness. With zero policy rules, rule coverage is vacuously 100%.

The frozen report includes `POLICY_COVERAGE_VERSION` (currently `1`), suite and policy identity,
the exact policy fingerprint, declaration-ordered covered/uncovered IDs, rule counts, a two-decimal
display percentage, allow/deny/review case counts, and input-free `PolicyCoverageError` objects.
Overridden authorization rules and warning rules count as covered when they match. Default outcomes
count as evaluated cases but do not cover a rule.

The CLI equivalent is `samsarix-ethics coverage --policy ... SUITE --threshold N`. It exits `0`
when the threshold is met, `1` when it is missed or evaluation errors occur, and `2` for invalid
input or invocation. Coverage is branch evidence over supplied cases, not proof that all condition
boundaries or possible inputs were exercised. See [POLICY_COVERAGE.md](POLICY_COVERAGE.md).
An optional shared context contract applies the same production fact checks to every coverage case;
contract input errors fail the threshold and remain input-free.

## Policy impact comparison

### `compare_policies(baseline, candidate, suite, *, context_contract=None) -> PolicyComparisonReport`

Evaluates every bounded `PolicyTestSuite` case independently against two policies and returns a
deterministic, input-free report. The suite's expected fields are not used for comparison; the
function directly compares each policy's actual outcome, ordered matched-rule IDs, warning count,
reason messages, and warning messages. Message contents are compared internally but not retained in
the report. Either-side evaluation failures become per-case `error` results rather than being
mistaken for unchanged behavior.
When supplied, one shared contract must accept both policies at construction and is enforced for
both evaluations of every case. Contract input failures are per-case errors.

The report uses `comparison_version = POLICY_COMPARISON_VERSION` (currently `1`) and includes both
policies' ID, version, and exact fingerprint. Aggregate properties are:

| Property | Meaning |
| --- | --- |
| `unchanged` | cases with equal outcome, matched rules, warning count, reasons, and warnings |
| `changed` | cases where one or more observable fields differ |
| `authorization_changes` | changed cases whose outcome differs |
| `metadata_only_changes` | equal-outcome cases with different rule, warning, or message metadata |
| `errors` | cases where either policy failed closed |
| `identical` | true only when `changed == 0` and `errors == 0` |

Each `PolicyComparisonResult` has a `PolicyComparisonStatus`, an ordered tuple of
`PolicyComparisonChange` values, and input-free baseline/candidate `PolicyComparisonSnapshot`
objects. `to_dict()` returns detached JSON values. It excludes fixture inputs, decision UUIDs,
timestamps, reason text, and warning text.

The CLI equivalent is `samsarix-ethics compare --baseline ... --candidate ... SUITE`. It exits `0`
only for identical observed behavior, `1` for changes or errors, and `2` for invalid invocation or
input. See [POLICY_COMPARISON.md](POLICY_COMPARISON.md) for rollout guidance and coverage limits.

## Audit records and sinks

### `AuditRecord.from_decision(decision) -> AuditRecord`

Creates a frozen `audit_record_version = AUDIT_RECORD_VERSION` record (currently version `1`) with
decision/policy identity, the exact policy fingerprint, evaluation time, outcome, matched rule IDs,
and warning count. Raw input, reasons, and warning text are absent. `to_dict()` returns a detached
JSON-compatible dictionary.

`AuditRecord.from_dict(value)` strictly parses the persisted version 1 shape, rejects missing and
unknown fields, and returns the same frozen model.

### `AuditSink`

A structural typing protocol for a synchronous callable with the signature
`sink(record: AuditRecord) -> None`. Normal `None` return means delivery succeeded. `ToolGate`
converts an ordinary sink exception to `AuditLogError` using only its type name; it does not retry.
An application that retries an uncertain external commit must deduplicate by `decision_id` if its
destination requires exactly-once storage.

### `JsonlAuditSink(path)`

The built-in local sink appends one compact record and calls `fsync`. Its destination parent must
already exist. It is also what `ToolGate(..., audit_log=path)` uses.

### `CompositeAuditSink(*sinks)`

Validates and retains 1-`MAX_COMPOSITE_AUDIT_SINKS` (currently 32) distinct synchronous audit
sinks, then delivers each record in supplied order. It stops at the first child failure or invalid
return and does not call later sinks. Earlier deliveries cannot be rolled back and no retry occurs.
The immutable `sinks` property exposes the exact delivery order.

### `OpenTelemetryDecisionEventSink()`

Lazily imports the optional exact `opentelemetry-api==1.44.0` integration and adds one
`OPENTELEMETRY_DECISION_EVENT_NAME` event to the current recording span for each audit record. The
event contract is `OPENTELEMETRY_DECISION_EVENT_VERSION = 1` and contains only the existing
metadata-only record fields under versioned `samsarix.*` attributes. It creates no span and a
non-recording span is a successful no-op. API-shape or event-delivery failures flow through the
ordinary fail-closed audit boundary. See [OPENTELEMETRY.md](OPENTELEMETRY.md).

### `append_audit_record(path, decision) -> None`

Appends one compact JSONL record and calls `fsync`. The destination's parent must already exist.
This compatibility helper converts the decision to `AuditRecord` and invokes `JsonlAuditSink`.
Raises `AuditLogError` on failure.

### `HmacAuditChainSink(path, key, *, stream_id, expected_head=None)`

Implements `AuditSink` for one local single-writer JSONL stream. `key` is copied from a 32-4096 byte
bytes-like value. A new stream begins at sequence 1; a non-empty existing stream is completely
verified before resuming. `expected_head` optionally binds that restart to an externally retained
checkpoint. The sink serializes calls from its own threads, flushes each append, and refuses an
observed out-of-instance file change. It exposes `path`, `stream_id`, `entry_count`, and the
nullable `head_mac`; its representation excludes the key.

### `verify_audit_chain(path, key, *, expected_head=None, expected_stream_id=None)`

Authenticates every bounded `AuditChainEntry` and returns a frozen `AuditChainVerification` with
the stream ID, entry count, sequence range, and head MAC. Duplicate fields, unknown fields, blank or
incomplete lines, sequence/link discontinuity, stream changes, malformed records, and incorrect
MACs fail with `AuditChainError`. An expected head detects valid-prefix rollback; without that
external anchor, the verifier cannot distinguish a legitimate shorter stream from rollback.
The verifier accepts only a regular file and rejects state changes observed during its read. Quiesce
the writer or provide an immutable snapshot when the report must represent a complete stream.

`generate_audit_chain_key()` returns a fresh 32-byte key. The application owns secret storage,
rotation, external checkpoint retention, cross-process writer exclusion, and post-execution outcome
records. See [AUDIT_CHAINS.md](AUDIT_CHAINS.md) for the format and complete threat boundary.

## Error hierarchy

`PolicyValidationError`, `PolicyDeploymentValidationError`, `PolicyActivationError`,
`PolicyCompositionError`, `PolicyTestValidationError`, `InputValidationError`, `EvaluationError`,
`AuditLogError`, `AuditChainError`, `OpenAIAgentsIntegrationError`, `LangChainIntegrationError`,
`PydanticAIIntegrationError`, `MCPServerIntegrationError`, `MCPClientIntegrationError`,
`MCPHTTPResponseError`, and the
tool-call enforcement errors derive from
`SamsarixEthicsError`. `AuditChainError` also derives from `AuditLogError`, preserving fail-closed
gate handling. The base
class and specialized errors are exported from `samsarix_ethics` and defined in
`samsarix_ethics.errors` or their optional integration module.

## Compatibility

The supported package API begins at `0.1.0`. The former repository code did not expose an
installable, internally consistent API; its missing imports and placeholder compliance types are
not compatibility targets. Breaking changes before `1.0.0` will be called out in `CHANGELOG.md`.
