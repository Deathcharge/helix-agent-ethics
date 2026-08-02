# Immutable tool dispatch

`ToolDispatcher` binds one verified tool catalog to one immutable snapshot of final Python
callback references. It gives model-selected calls a dependency-free runtime path in which trusted
name/capability metadata, authorization, audit delivery, and callback selection stay together.

```python
from samsarix_ethics import ToolDispatcher, load_tool_gate_deployment

deployment = load_tool_gate_deployment("coding-agent.gate-deployment.json")
callbacks = {
    "read_file": read_file,
    "write_file": write_file,
    # Every cataloged tool must be present exactly once.
}
dispatcher = ToolDispatcher.bind_deployment(
    deployment,
    registered_tools=callbacks,
)

result = dispatcher.execute(
    model_tool_name,
    model_arguments,
    actor={"id": authenticated_agent_id},
    context={"workspace_contained": application_verified_containment},
)
```

Callbacks receive the validated, detached argument object as keyword arguments. `execute_async`
requires a callback that returns an awaitable. Both methods return `ToolExecutionResult`, pairing
the callback value with the exact authorizing decision. Deny and review outcomes retain the normal
typed exceptions and never invoke a callback.

Agent Ethics bounds and validates the JSON argument object but does not own the framework's JSON
Schema or Python signature contract. Validate model arguments against the trusted tool schema
before dispatch, or let the final callback perform its normal signature/domain validation. Such a
callback error propagates after authorization; the audit record proves authorization, not success.

## Bind final callbacks, not mutable lookups

The dispatcher copies the supplied mapping and retains each callable object. Replacing an entry in
the original registry or dictionary later does not change dispatch. Pass the final tool function:

```python
callbacks = {
    name: registry.get_tool(name).function
    for name in registry.list_tools()
}
```

Do not bind a callback such as `lambda **args: registry.call(name, **args)` if that call performs a
fresh mutable name lookup. Such a wrapper is itself stable, but the implementation it selects is
not. The dispatcher cannot authenticate Python code, freeze closure/global/object state, detect
monkey-patching, prove capability labels correct, or stop a callback from delegating elsewhere.
Protect registration and deployment startup as trusted application operations.

## Multi-call turns

Prepare calls through the dispatcher so model input can supply only a known name and arguments:

```python
calls = [
    dispatcher.prepare("read_file", {"path": "README.md"}, context=trusted_context),
    dispatcher.prepare("run_command", {"command": "pytest"}, context=trusted_context),
]
results = dispatcher.execute_many(calls)
```

`execute_many` and `execute_many_async` normalize the bounded batch, require every prepared name
and capability tuple to match the dispatcher bindings, evaluate every item against one policy
generation, deliver all audit records, and require every outcome to be `allow` before the first
callback runs. Binding mismatch fails before evaluation or audit delivery. Allowed callbacks then
run sequentially in input order.

This is preflight, not a transaction. If callback two raises after callback one succeeds, the first
side effect remains. The embedding framework owns cancellation, retries, idempotency, timeouts,
concurrency, isolation, and compensation. Async batches are awaited sequentially; the package does
not silently move synchronous callbacks to threads.

Run `python examples/tool_dispatcher_demo.py` for a coherent-deployment example whose denied second
batch item proves that the allowed first item is not dispatched.
