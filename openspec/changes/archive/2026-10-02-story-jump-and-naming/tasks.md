# Tasks

## 1. The bundle format

- [x] 1.1 `03` §2/§2.1: the bundle is `globals` + `steps` + `exit`, the step keys are `name` /
  `type` / `parse`|`call` / `next` / `with`, and the `chains` table is gone
- [x] 1.2 `03` §4/§5: `next` (step default plus the per-task override, kernel-resolved, never handed
  to the host), per-answer execution of the receiving step, the join rule, and the `exit` collection
- [x] 1.3 `03` §10: the lint rows, including the `L9` row that mentions `chains`, and the two codes
  the story compiler uses (`UP2-E1009`, `UP2-E1016`)
- [x] 1.4 `03` §11: rewrite the walkthrough to the new keys, with a parse rule per step
- [x] 1.5 `03` §12/§13: record the jump (`R15` superseded) and close the open questions this change
  settles (`O5` gets `py.id`, the exit question, `$in`)
- [x] 1.6 `007`'s L2 roadmap row: the story's step sequence spelled with `name` / `type` / `next` /
  `exit`
- [x] 1.7 Rewrite both `samples/*/site.json` to the new keys, each response parsed by a named step

## 2. `$in` and `py.id`

- [x] 2.1 `core/refs.py`: `in` joins the reserved roots; `Scope` carries the step input (`child()`
  propagates it) and `read` resolves `$in.*` through the same path walk
- [x] 2.2 `ops/pyops.py`: the `id` action (no arguments, the input unchanged)
- [x] 2.3 Tests: `$in` reads a seed's own input, `$in.url` resolves a relative link against an
  answer's final URL, `py.id` is the identity on a string and on a host object, `in` is reserved
- [x] 2.4 Registry/docs/conformance: `py.id` in `docs/operator-reference.md`, `02` §6.4's table, a
  `tools/demo_report.py` case, and the `py` coverage declaration

## 3. The first story executor

- [x] 3.1 `core/story.py`: `compile_story` — the bundle shape, step names, `parse`/`call`, `next`
  and `exit` resolution, the field map, and the limits (`UP2-E1005` / `UP2-E1009` / `UP2-E1016` /
  `UP2-E1012`)
- [x] 3.2 `core/story.py`: the run — `start` / `next` / `send`, the effect tuples, suspension and
  resume of the same run, per-answer execution with the join rule, and the exit collection
- [x] 3.3 `call`: the `with` leaves resolve as `ref_or_literal` through the step's scope, and the
  receipt becomes the step's product
- [x] 3.4 `up2 lint` / `up2 trial` accept a story file (shape branch, the suspended state, the
  refused `--global` / `--product`)
- [x] 3.5 Tests: the compile failures (`E1005` / `E1009` / `E1016`), a single-request run, a batch
  fan-out and rejoin, a nested request, a `call`, `done` idempotence, the exit list, and the CLI story
  path
- [x] 3.6 Conformance declarations and the coverage gates stay green with the two new codes

## 4. Proof on real sites

- [x] 4.1 Run `samples/books.toscrape.com/books/site.json` through the executor against the live site
  (a stdlib `urllib` host loop), and record the output
- [x] 4.2 Run `samples/quotes.toscrape.com/quotes/site.json` the same way, and record the output
- [x] 4.3 `up2 lint` both sample bundles

## 5. Gates

- [x] 5.1 `ruff format --check` / `ruff check` / `mypy` / `pytest --cov=uniparser2.core
  --cov-fail-under=95` / `up2 conformance --check`
- [x] 5.2 The `change-linter` for every edited `.py`
- [x] 5.3 `openspec validate --strict` for this change, and archive it with the
  `openspec-archive-change` skill
