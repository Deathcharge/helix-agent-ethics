# Coherent tool-gate deployments

A tool-gate deployment is one bounded JSON v1 document containing an internally locked policy
deployment, a trusted tool catalog, and the catalog's exact canonical fingerprint. It prevents a
process from accidentally loading a policy generation from one rollout and capability labels from
another.

```console
samsarix-ethics gate-deployment create \
  --policy-deployment coding-agent.policy-deployment.json \
  --tool-catalog coding-agent-tools.json \
  --output coding-agent.gate-deployment.json
samsarix-ethics gate-deployment verify coding-agent.gate-deployment.json
samsarix-ethics schema tool-gate-deployment > tool-gate-deployment-v1.schema.json
```

The CLI report contains policy and catalog identity, fingerprints, tool count, verification state,
and output path. It does not reproduce policy rules or capability labels.

## Bind only after registry verification

```python
from samsarix_ethics import ToolGate, load_tool_gate_deployment

deployment = load_tool_gate_deployment("coding-agent.gate-deployment.json")
bindings = ToolGate.bind_deployment(
    deployment,
    registered_tools=registry.list_tools().keys(),
)

decision = bindings[model_tool_name].enforce(model_arguments)
```

`bind_deployment` constructs the gate from the deployment's verified policy, context contract, and
lock, then performs the catalog's exact name-set check before returning any bindings. A malformed
nested artifact, mismatched catalog fingerprint, missing tool, uncataloged tool, duplicate name, or
invalid capability fails closed.

For a complete in-process execution boundary, `ToolDispatcher.bind_deployment(...)` accepts a
mapping of final Python callback objects, performs the same exact match, snapshots those references,
and dispatches only after an allow decision. See [immutable tool dispatch](TOOL_DISPATCH.md).

Current agent runtimes already own pause/resume and durable human-review workflows. The
[OpenAI Agents SDK](https://openai.github.io/openai-agents-python/human_in_the_loop/) surfaces mixed
pending tool approvals as interruptions, while
[LangChain](https://docs.langchain.com/oss/python/langchain/human-in-the-loop) persists interrupts
through LangGraph checkpointers. Samsarix supplies deterministic authorization artifacts at the
dispatch boundary instead of replacing those workflow engines.

The artifact follows the same last-known-good principle as policy bundle systems. For example,
[OPA bundle verification](https://www.openpolicyagent.org/docs/management-bundles) activates a new
bundle only after its configured verification succeeds. Samsarix verifies internal exact equality;
the embedding deployment system remains responsible for authenticating who produced and approved
the file.

## Security and operational limits

- The catalog fingerprint detects mixed or changed local content; it is not a signature.
- Anyone able to replace the whole document can recompute its internal fingerprints.
- Exact name matching does not prove callable identity or capability-label correctness. A
  `ToolDispatcher` can stabilize selected object references, but cannot authenticate their code or
  freeze their closure, global, delegated-registry, or object state.
- The artifact does not fetch, distribute, approve, encrypt, sign, retain, or roll back itself.
- Durable desired state, transport authentication, promotion authorization, multi-host convergence,
  and restart recovery remain deployment-system responsibilities.
- MCP annotations remain untrusted hints and are never converted into capabilities automatically.

Protect the exact file bytes with repository review or an immutable artifact digest. If signatures
or attestations are required, verify repository/workflow identity and digest before opening the
path, then avoid a verify/reopen race by promoting the verified immutable object.
