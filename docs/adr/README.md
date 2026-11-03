# Architecture decision records

Why the package is shaped the way it is, with the evidence that decided it. Each record follows
[MADR 4](https://adr.github.io/madr/). Docstrings state the contract and point here with
`Rationale: ADR-NNNN.`; what changed release by release is in [`CHANGELOG.md`](../../CHANGELOG.md).

The first six were recorded together in 0.3.0, after the fact: each decision shipped earlier, and
its reasoning lived in docstrings until then. The release that made each decision is named in its
record.

| ADR | Decision |
|---|---|
| [0001](0001-write-on-entry.md) | Open a unit when the work starts and close it when it ends; fall back to one completion write |
| [0002](0002-the-writer-never-raises.md) | The writer never raises, is bounded by a timeout, and does not retry |
| [0003](0003-cancelled-is-not-failed.md) | A stopped unit is `cancelled`, not `failed` |
| [0004](0004-one-contract-for-receiver-and-writers.md) | The receiver validates with, and every writer builds through, the same models |
| [0005](0005-closed-vocabulary-receiver-first.md) | Kinds, layers and statuses are closed sets; a new value ships to the receiver first |
| [0006](0006-a-cli-for-shell-writers.md) | Shell writers use the package's CLI; the key never rides argv; exit codes name the failure |
