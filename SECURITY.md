# Security policy

## Supported versions

Until the first public release, the current default branch and the `0.1.x` release-candidate line
receive security fixes. No older repository snapshot is supported as an installable package.

## Reporting

Please use GitHub's private **Report a vulnerability** flow for this repository; private
vulnerability reporting is enabled. Do not include credentials, personal data, production policy
files, or sensitive action inputs in a public issue. If the private flow is inaccessible, email
[support@samsarix.com](mailto:support@samsarix.com) with a minimal description and request a safer
channel before sending secrets, production data, or exploit details.

No response-time SLA or bounty program is currently promised.

## Security boundary

Policy files are trusted developer/operator configuration. Evaluation inputs may be untrusted and
are bounded and type-checked. The embedding application remains responsible for:

- authenticating the actor and supplying trustworthy facts;
- assigning tool capability labels outside model control;
- binding tool names and capability labels once at trusted registration time where practical;
- storing pending-call fingerprints before review, authenticating reviewers, enforcing approval
  expiry, and atomically consuming approvals once;
- enforcing the returned decision immediately before the protected side effect, either with
  `ToolGate` or an equivalent boundary;
- treating every exception and nonzero CLI exit as non-authorization;
- preventing time-of-check/time-of-use races;
- protecting and reviewing policy files;
- recording the expected policy fingerprint at deployment when exact policy provenance matters;
- enforcing only the authoritative baseline decision during shadow rollout and separately
  monitoring candidate status, latency, changes, and errors;
- controlling audit destination credentials, network egress, idempotency, access, rotation,
  retention, integrity, and deletion.

`ToolGate` invokes only the explicit callback supplied by the embedding application and only after
an allow decision; it is not a sandbox. The package makes no network requests, executes no policy
code, loads no plugins, and stores no raw evaluation input in its built-in audit record.
Policy-test, comparison, and coverage reports exclude case inputs but expose case names. Shadow
reports exclude action inputs and have no case-name field. These report types still expose policy
and rule identifiers, fingerprints, and bounded evaluation errors; do not place secrets in those
operator-authored labels, and protect reports as operational metadata. Coverage proves only that a
supplied case matched a rule, not that every condition path or input is safe.
Lint reports omit condition values, descriptions, and rule messages, but expose rule identifiers
and zero-based condition locations. A clean lint report covers only documented deterministic
findings and is not evidence that an allow rule reflects application intent or least privilege.
Composition reports omit source paths, descriptions, rules, conditions, messages, and condition
values, but expose source and target IDs, versions, rule counts, and exact fingerprints. Treat
those fingerprints as operational metadata and equality oracles, not author signatures or
freshness evidence. Composition does not fetch, authenticate, sign, distribute, or activate policy.
Shadow reports also omit reason and warning text, but expose decision IDs/timestamps and candidate
errors plus per-policy evaluation durations. A successful baseline remains authoritative when the
candidate changes or raises a domain error; candidate health must therefore be monitored
independently of the authorization result.
Shadow evaluation is synchronous and may add latency or resource use. The package does not sample,
queue, persist telemetry, promote candidates, or roll back policies.
Caller-supplied audit sinks are trusted application code invoked synchronously before authorization;
their failures prevent tool execution, but their transport and downstream storage are outside this
package's boundary.

`ToolGate` rejects a `ToolCallApproval` when its fingerprint does not match the normalized call ID,
tool, arguments, capabilities, and actor. This is mutation detection, not authentication: approval
objects are ordinary application values, and parsing one with `from_dict` proves only that its JSON
shape is valid. Keep approval records in trusted server-side storage, never derive them from model
output, and enforce replay protection in the application.

`ToolGate.bind(...)` freezes a tool name and canonical capability tuple so invocation payloads
cannot downgrade those labels per call. The application still owns the registry used to select the
binding. Treat MCP and other remote tool annotations as untrusted hints unless their source and
meaning are independently trusted.

An optional `ContextContract` can reject policy path typos and missing or mistyped declared facts
before rule evaluation. A contract is trusted configuration, not authentication: it does not prove
that identity, capability, approval, tenant, or risk facts came from a trusted source, and it
deliberately permits unrelated input fields. Applications must derive and protect trusted facts
outside model-controlled payloads and use a full application validator when the entire request
must be closed. Current decisions and reports do not bind a contract fingerprint; preserve and
review the exact contract artifact through deployment configuration when its provenance matters.

The policy fingerprint is deterministic mutation/equality evidence, not a digital signature. It
does not authenticate a policy author, prove review, prevent rollback, or secure policy
distribution. Because a digest can also act as an equality oracle for a guessable private policy,
applications should apply suitable access controls to audit destinations that store it.

## Relevant vulnerability classes

Reports are especially useful when they demonstrate policy bypass, incorrect deny/review
precedence, parser or resource-limit bypass, sensitive input disclosure, unsafe file behavior, or a
way for malformed input to become an allow decision.
