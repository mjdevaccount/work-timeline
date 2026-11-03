---
status: accepted
date: 2026-11-03
---

# Shell writers use the package's CLI; the key never rides argv; exit codes name the failure

Decided in 0.2.0 (`python -m work_timeline`). Recorded in 1.0.0.

## Context and problem statement

Some writers are shell scripts: a deploy step, a cron wrapper. A script that builds the JSON
itself re-types the contract (its own escaping, its own field names, its own status words) and
loses everything ADR-0004 gains. A fire-and-forget `curl` also cannot tell "the receiver refused
this body" from "nothing answered".

## Decision drivers

- A shell writer must send exactly the body a Python writer would.
- The API key must not be visible to other users of the host.
- The caller must be able to tell refused from unreachable without parsing text.

## Considered options

1. Document a `curl` recipe.
2. A CLI in the package that builds through the contract models, reads the key from the
   environment, and reports the outcome as an exit code.

## Decision outcome

Chosen option 2. `python -m work_timeline record | open | close` builds each body through the
contract models. The key is read from the environment variable `--key-var` names; argv is readable
by every user of the host through `ps`, so the key is never accepted there. `--dry-run` prints the
exact body and sends nothing, so a caller's own tests can assert on it.

Exit codes: `0` accepted, `2` bad input (including a body the contract refuses, caught before it
is sent), `3` refused by the receiver, `4` no response, `5` not configured. The work being observed
must not fail because of them; a caller logs the line and carries on.

`--header` adds request headers (a `Host` header for a reverse proxy, say). The key, `Content-Type`
and `Accept` headers are set after the caller's, so a header can be added but the key cannot be
replaced.

The CLI does not translate a caller's status words. Anything other than `ok`, `failed` or
`cancelled` is recorded as `failed` (ADR-0003); the translation stays in the caller, where the
local word is defined.

### Consequences

- Good: one body format for every writer, Python or not.
- Bad: a shell writer needs a Python interpreter with the package installed.
