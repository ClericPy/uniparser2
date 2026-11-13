# uniparser2 — repository instructions

The global engineering rules live in `~/.dsh/AGENTS.md` (read that first). This file records only what
is **specific to this repository**.

## Language

Code comments, docstrings, user-facing strings and repo docs are English; `README.zh-CN.md` is the only
Chinese artifact.

## Definition of done for every change

```bash
uv sync                          # after a dependency change
uv run ruff format --check
uv run ruff check
uv run mypy                      # strict
uv run pytest --cov=uniparser2.core --cov-fail-under=95
uv run up2 conformance --check   # must exit 0
```

`up2 conformance --check` is this repository's **backbone constraint**: every `(operator, action)`
declared in the registry must have a visible coverage declaration in the test sources, and every
implemented error code must be asserted by at least one case. Adding an operator and forgetting its
case — or writing a case for something the registry does not have — turns this step red. The
per-change checks (what to run, and when) are in `docs/specs/005` §6.

## Determinism: what you see is what you get

**The engine never backs up a rule that is wrong.** If a chain can produce something undesirable, the
fix is in the rule (the operator's Schema, the stage's contract), never a guard bolted on afterwards.
A defensive layer invents a rule the chain never declared, and the chain stops predicting its own
output. Concretely:

- **No export check.** `run` answers what the run produced. A host object, an `Opaque` handle or a
  `datetime` at the exit is the product; if the host cannot serialize it, the host's own serializer
  says so, with the trace already showing which operator produced it. There is no `pack`, and
  `UP2-E2003` is retired.
- **No implicit coercion.** An operator either accepts a value or fails it with a code; it never
  silently converts one shape into another because the next stage would prefer it.
- **No silent drops.** A value the consumer cannot handle is reported and named (key, `repr`), not
  filtered out. `Scope.json_view` fails instead of hiding a scope entry the sandbox cannot take.
- **No guessing the host's intent.** "The host probably wants JSON / probably wants text / probably
  has no serializer" is not a reason to act; report and let the caller decide.
- **Diagnostics still localize**: a failure carries a code, a one-sentence `fix`, a `pointer`, and the
  `allowed` values when a substitute exists (`01` §4). That is the opposite of a guard -- it is what
  lets a caller fix the rule instead of working around it.

A guard is only acceptable when it enforces a **module boundary the module itself owns** (the Monty
sandbox takes JSON, so `code` rejects a non-JSON argument) -- never a policy about what the caller
should do with the result.

## Cross-operator invariants (`tests/invariants/`)

`conformance` audits `(operator, action)` pairs. It says nothing about a claim that **spans**
operators or crosses a layer boundary — and that gap shipped a defect: `type` was documented as a
chain-tail JSON validator in `01`/`02`/`03`, each operator's own tests agreed with that sentence,
and every gate stayed green while the engine substituted the payload for the object it built.

`tests/invariants/` exists so a documented claim has an executing case:

- **A fact in `docs/specs/` that involves two or more operators, or a boundary between layers, needs
  a case here** — not only a case in one operator's file. "A host object flows mid-chain whichever
  operator produced it" and "the exit hands back what the run produced" are the canonical examples.
- `tests/invariants/test_invariant_coverage.py` reads the ids the notes declare (`I1`–`I8` in
  `01` §1.1, `N1`–`N8` in `00` §2) and fails when one is neither executed here (`INVARIANT_CASES`)
  nor recorded as enforced by another gate (`ENFORCED_ELSEWHERE`). Declaring a new invariant in
  `00`/`01` therefore requires naming the case that proves it.
- A source-level assertion is legitimate here when the invariant is about *where* something may
  happen (no IO on an `evaluate` path, no `async` anywhere) — behaviour tests cannot see placement.

## Kernel invariants

| Invariant | Concrete form |
|---|---|
| The kernel depends on the standard library only | every import under `src/uniparser2/core/` comes from the stdlib or the same package; third-party code goes into `ops/` and is declared as an optional dependency per operator/action |
| The kernel stays pure | `core/` touches neither the network nor the filesystem; IO such as file scanning lives in `cli/` |
| Fully synchronous | there is no `async`/`await` anywhere; concurrency is left to the caller |
| No export check | `run` answers what the run produced; nothing inspects, rejects or substitutes the product |
| The chain is data | `dumps(loads(x))` is a character-for-character fixed point, guaranteed by tests |
| Bad chains fail at compile time | unknown operators/actions, mismatched arguments and dangling references all error during `compile_field`, with a `UP2-E*` code and a JSON Pointer |

## Error codes

To add a code: first write it into `CODES` in `core/errors.py` (`diag()` rejects codes outside that
table, deliberately), then assert it in a test. To express "a deliberately nonexistent code" in a test,
build it (`"UP2-E" + "9999"`) — a literal would be read by the conformance audit as a coverage
declaration.

## Change process

1. **Open a change first**: `openspec list` to see existing changes; draft one with the
   `openspec-propose` skill (proposal / design / specs / tasks).
2. Change the code + add tests + update the design docs (changes to interfaces, error codes or DSL
   syntax must land in the design drafts).
   - **Verify a doc claim against the engine before writing it as an invariant.** Run the smallest
     case that exercises the claim (a host object at the exit, a stage boundary, an operator's
     position in a chain) rather than describing what the code appears to do. A design sentence that
     no case executes is the bug, not the spec.
   - A claim that spans operators or layers lands in `tests/invariants/` (see above).
3. Run the gates above; all green.
4. `openspec-archive-change` to archive, merging the delta into `openspec/specs/`.
5. **Record future syntax changes in the CHANGELOG**: a change that alters DSL syntax or observable
   behavior adds an entry to `CHANGELOG.md` under the version it ships in, with breaking changes
   marked. Do not backfill earlier versions (the `0.7.0` story model included): start recording with
   the next syntax change after the version that introduces this rule.

`openspec/config.yaml` sets artifacts to English, with structural headings and SHALL/MUST keywords kept
in English.

## Where the docs are

- The 8 design notes live in `docs/specs/` as `0NN-*.md` (index in `docs/README.md`) and are committed.
  They are referenced by their leading number `00`–`07`.
- Before writing a chain or changing operator semantics, read the `02` DSL spec (triples and operators);
  before changing chain structure, read the `03` parse chain spec.
- Use `uv run up2 ops --json` for the facts about operator capabilities, instead of writing action names
  from memory.
