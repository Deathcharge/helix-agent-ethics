# Security policy

## Supported versions

Until the first public release, the current default branch and the `0.1.x` release-candidate line
receive security fixes. No older repository snapshot is supported as an installable package.

## Reporting

Please use GitHub's private **Report a vulnerability** flow for this repository when it is enabled.
Do not include credentials, personal data, production policy files, or sensitive action inputs in a
public issue. If private reporting is unavailable, open a minimal public issue asking the owner to
enable a private channel without disclosing exploit details.

No response-time SLA or bounty program is currently promised.

## Security boundary

Policy files are trusted developer/operator configuration. Evaluation inputs may be untrusted and
are bounded and type-checked. The embedding application remains responsible for:

- authenticating the actor and supplying trustworthy facts;
- enforcing the returned decision immediately before the protected side effect;
- treating every exception and nonzero CLI exit as non-authorization;
- preventing time-of-check/time-of-use races;
- protecting and reviewing policy files;
- controlling audit-file access, rotation, retention, integrity, and deletion.

The package makes no network requests, executes no policy code, loads no plugins, and stores no raw
evaluation input in its built-in audit record.

## Relevant vulnerability classes

Reports are especially useful when they demonstrate policy bypass, incorrect deny/review
precedence, parser or resource-limit bypass, sensitive input disclosure, unsafe file behavior, or a
way for malformed input to become an allow decision.
