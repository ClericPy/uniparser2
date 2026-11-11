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

## Kernel invariants

| Invariant | Concrete form |
|---|---|
| The kernel depends on the standard library only | every import under `src/uniparser2/core/` comes from the stdlib or the same package; third-party code goes into `ops/` and is declared as an optional dependency per operator/action |
| The kernel stays pure | `core/` touches neither the network nor the filesystem; IO such as file scanning lives in `cli/` |
| Fully synchronous | there is no `async`/`await` anywhere; concurrency is left to the caller |
| A single exit | values leaving a chain all pass through `core/export.pack`; `Opaque` handles and illegal types are rejected there |
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
