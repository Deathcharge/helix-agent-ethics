# Trusted tool catalogs

A tool catalog is the application-owned link between a runtime registry and Agent Ethics policy
capabilities. It prevents a model, remote tool server, or per-call adapter from selecting weaker
capability labels than the application reviewed.

The catalog is a standalone JSON v1 artifact. It has no dependency on Samsarix Core, Samsarix Agent
Framework, MCP, or a provider SDK:

```json
{
  "tool_catalog_version": 1,
  "id": "coding-agent-tools",
  "version": "1.0.0",
  "description": "Trusted local coding tool capabilities.",
  "tools": [
    {
      "name": "read_file",
      "capabilities": ["workspace:read"]
    },
    {
      "name": "run_command",
      "capabilities": ["process:execute", "risk:elevated"]
    }
  ]
}
```

Validate and identify a catalog without loading a policy:

```console
samsarix-ethics catalog examples/catalogs/coding-agent-tools.json
samsarix-ethics schema tool-catalog > tool-catalog-v1.schema.json
```

The text and JSON CLI reports contain only the catalog ID/version, exact fingerprint, format
version, and tool count. They do not reproduce capabilities.

## Bind the complete registry

Load the catalog, obtain the complete tool-name snapshot from the trusted local registry, then bind
both to one gate:

```python
from samsarix_ethics import ToolGate, load_policy, load_tool_catalog

gate = ToolGate(load_policy("policy/tool-policy.json"))
catalog = load_tool_catalog("policy/tool-catalog.json")
registered_names = registry.list_tools().keys()
bindings = gate.bind_catalog(catalog, registered_tools=registered_names)

requested = bindings[model_tool_name]
decision = requested.enforce(model_arguments)
```

`bind_catalog` fails before returning any binding if a cataloged tool is absent from the registry,
an uncataloged tool is present in the registry, a name is duplicated or invalid, or either side
exceeds 256 tools. The resulting `BoundToolCatalog` is immutable, gate-specific, and carries the
exact catalog fingerprint. Each contained `BoundToolGate` freezes the catalog's canonical name and
capability tuple.

If the registry exposes its final Python functions, `ToolDispatcher.bind_catalog(...)` can also
snapshot those references and own post-authorization selection. See
[immutable tool dispatch](TOOL_DISPATCH.md).

For Samsarix Core, derive names from `(spec.name for spec in registry.list())`. For Samsarix Agent
Framework, `registry.list_tools().keys()` is already a name view. Other frameworks should expose an
equivalent application-controlled snapshot. Passing a partial, model-generated, or remote-server
list defeats the exact-match check.

## MCP and remote tools

MCP behavioral annotations such as `readOnlyHint` and `destructiveHint` are descriptive hints, not
authorization facts. Keep the MCP server allowlist and local aliases in the host application, then
catalog those local alias names with application-reviewed capabilities. Do not translate untrusted
server annotations directly into catalog entries.

The same rule applies to hosted or built-in provider tools: the catalog is useful only where the
application controls the final dispatch seam. Tools that execute entirely inside a provider need a
separate protected interception or provider permission boundary.

## Canonicalization and provenance

Catalogs contain 1-256 tools and 1-64 capabilities per tool. Identifiers use the same bounded
syntax as `ToolGate`. Parsing rejects duplicate keys, duplicate tool names, duplicate capabilities,
non-finite values, deep/oversized JSON, unknown fields, and empty registrations. Tool entries and
capabilities are sorted canonically, so semantically equivalent input ordering has the same
`fingerprint_tool_catalog(...)` result.

The fingerprint proves exact canonical content equality under the documented v1 serializer. It
does not prove who authored or approved the catalog, whether its labels are correct, or whether the
artifact is fresh. Store and promote it through authenticated, immutable application configuration.
The current policy deployment v1 does not embed or sign a catalog; pin its fingerprint separately
when deployment-level drift prevention is required.

## Deliberate non-goals

- The catalog does not infer capabilities from function schemas, descriptions, names, or MCP hints.
- Exact registry matching does not prove that registered callables implement their claimed names.
- A catalog does not replace a fail-closed policy; policy still decides what each capability means.
- It does not authenticate registries, catalog authors, reviewers, callers, or remote servers.
- It does not schedule tools, validate tool arguments, sandbox execution, or make a batch
  transactional.
