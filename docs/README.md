# Documentation index

## Design notes (`docs/specs/`)

The design notes are committed, in English, and numbered. They are the **single source of truth** for
what the system should be; design note `05` §5 describes how code and notes are kept in sync.

| Note | File | Content |
|---|---|---|
| `00` | [`000-overview.md`](specs/000-overview.md) | positioning, the end-state acceptance criteria, where the four root goals land, glossary, scope and exclusions |
| `01` | [`001-architecture-and-value-model.md`](specs/001-architecture-and-value-model.md) | layering and invariants, package structure, the value tree, three states and policies, exit boxing, security and resource limits |
| `02` | [`002-dsl-spec-triples-and-operators.md`](specs/002-dsl-spec-triples-and-operators.md) | the chain step `[operator, action, argument]`, the enumeration strength of the slots, reference syntax, the full set of 11 operators (including the optional `code` sandbox), the error code table |
| `03` | [`003-parse-chain-spec.md`](specs/003-parse-chain-spec.md) | the **story** model: a step sequence (`parse` / `call` plus `type` / `next` / `exit`), products and type names, the effects and the suspend/resume run loop, `each` and the field map, on-demand materialization with the run-scoped cache, scope, the compile-time lint checklist, and the ah.gov.cn walkthrough |
| `04` | [`004-persistence-and-sop.md`](specs/004-persistence-and-sop.md) | the persistence data model for chains, fingerprints and auditing, the Store abstraction, the `S0–S7` freezing process, the chain's trust boundary |
| `05` | [`005-engineering-workflow.md`](specs/005-engineering-workflow.md) | uv / test layering / conformance audit / documentation-driven development / OpenSpec integration / CI and release |
| `06` | [`006-trial-ui-design.md`](specs/006-trial-ui-design.md) | the pywebview in-place trial UI: three-column layout, single-step trace, the save-as-snapshot loop (design only; not implemented) |
| `07` | [`007-source-decisions-and-roadmap.md`](specs/007-source-decisions-and-roadmap.md) | rulings on the five source materials one by one, conclusions on the 18 blockers, the L1–L4 roadmap and acceptance criteria, the open-questions list |

Code, tests and OpenSpec changes cite these notes by their leading number (`design note 02 §6.12`
means §6.12 of `002-dsl-spec-triples-and-operators.md`).

## Reference pages

- **[`operator-reference.md`](operator-reference.md)**: what each operator and action means, how the
  parameter slot is written, and worked examples with their real outputs. It is **hand-maintained**;
  the authority for the action list stays the registry (`uv run up2 ops --json`).
- **[`report/up2-report.md`](report/up2-report.md)**: the machine-written catalogue — one case per
  declared `(operator, action)` pair, the multi-stage compositions and the compile-time invalid forms,
  each produced by a real run. A test keeps it honest:
  `uv run pytest tests/report` fails when it is stale, and
  `UP2_UPDATE_REPORT=1 uv run pytest tests/report` rewrites it (`005` §6).

## Conventions

- **Interfaces, error codes and DSL syntax changes must land in the notes** before or with the code
  change; stale documentation is worse than none (`005` §5).
- The design notes were translated from Chinese drafts, so a few passages still describe the state at
  drafting time; the notes are the authority for *design intent*, the tests for *behaviour*.

## Not in this directory

- **ADRs** (`docs/adr/NNNN-*.md`): design note `05` §5.4 step 2 promotes the rulings in note `07`
  into one ADR per irreversible trade-off. Not executed yet.
- **Source material**: the inputs the design was adjudicated against (an earlier template-engine
  prototype and a prior parser design) are internal and **not shipped in this repository**; note `07`
  records the rulings made against them.
