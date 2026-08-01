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
- enforcing the returned decision immediately before the protected side effect, either with
  `ToolGate` or an equivalent boundary;
- treating every exception and nonzero CLI exit as non-authorization;
- preventing time-of-check/time-of-use races;
- protecting and reviewing policy files;
- controlling audit destination credentials, network egress, idempotency, access, rotation,
  retention, integrity, and deletion.

`ToolGate` invokes only the explicit callback supplied by the embedding application and only after
an allow decision; it is not a sandbox. The package makes no network requests, executes no policy
code, loads no plugins, and stores no raw evaluation input in its built-in audit record.
Caller-supplied audit sinks are trusted application code invoked synchronously before authorization;
their failures prevent tool execution, but their transport and downstream storage are outside this
package's boundary.

## Relevant vulnerability classes

Reports are especially useful when they demonstrate policy bypass, incorrect deny/review
precedence, parser or resource-limit bypass, sensitive input disclosure, unsafe file behavior, or a
way for malformed input to become an allow decision.
