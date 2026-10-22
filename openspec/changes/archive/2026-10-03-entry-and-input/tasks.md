# Tasks

## 1. The entry step

- [x] 1.1 `core/story.py`: add `entry` to the bundle keys, require it, resolve it against the declared
  names (`UP2-E1005` at `/entry` when missing or not a string, `UP2-E1016` when it names nothing), and
  carry it on `CompiledStory`
- [x] 1.2 `core/story.py`: start the run at the entry step instead of position 0, and keep the run's
  value as that step's input
- [x] 1.3 `cli/main.py`: `up2 lint` names the entry step in its output and in its `--json` payload

## 2. The unreachable-step lint

- [x] 2.1 `core/errors.py`: register `UP2-E1018` (a step unreachable from the entry)
- [x] 2.2 `core/story.py`: reuse the flow walk from the entry and reject every step it cannot reach with
  `UP2-E1018`, naming the step and pointing at it

## 3. A chain may be a whole-chain reference

- [x] 3.1 `core/ast.py`: carry a whole-chain reference on `CompiledField` (and a `$` marker stage that
  serializes back to the reference's own text)
- [x] 3.2 `core/compile.py`: a string beginning with `$` in chain position compiles as that reference,
  validated by the same reference checks (`UP2-E1006` / `UP2-E1014`); a chain may also open with one
- [x] 3.3 `core/evaluator.py`: evaluate a whole-chain reference by reading it in the scope, unchanged
- [x] 3.4 `core/trace.py`: a compiled parameter carrying such a chain renders as the reference it is (no
  synthetic stage), and the stage index keeps the source's own position

## 4. `py.id` is deleted

- [x] 4.1 `ops/pyops.py`: delete the `id` entry, `_py_id` and its docstring mention
- [x] 4.2 Tests: the `py.id` cases become whole-chain-reference cases (`tests/ops/test_pyops.py`,
  `tests/runtime/test_runtime_errors.py`)

## 5. The samples

- [x] 5.1 Both `samples/*/site.json`: declare `entry`, drop the identity stages, collapse a `["$in"]`
  chain to the reference
- [x] 5.2 Both `samples/*/host.py`: take the seed URL from the command line (defaulting to the site
  root) and stop passing `globals.base_url` as the seed, with the one-line reason
- [x] 5.3 Re-run both samples live through their committed host scripts and record the output

## 6. Tests

- [x] 6.1 `tests/chains/test_story.py`: `entry` required / unknown / naming a step that is not first, and
  the unreachable-step cases of `UP2-E1018`
- [x] 6.2 A whole-chain-reference suite: a field-map value, a step's `parse`, an `each` element's step
  input, a host object staying unconverted, an unknown root (`UP2-E1006`), a local of another step
  (`UP2-E1014`) and a self-reference
- [x] 6.3 Every existing story bundle in the tests, the CLI cases and `samples/local/demo` declares `entry`
- [x] 6.4 Conformance stays green: 72 declared pairs = 72 covered pairs, and `UP2-E1018` has a case

## 7. Docs

- [x] 7.1 `03` §2 (the bundle table and the JSON), §2.1 (`parse` shapes), §5 (the run loop's start),
  §10 (L1/L9 and the new L13), §11 (the walkthrough and the sample measurements), §12.6, §13 O5/O13
- [x] 7.2 `002` §3.1 (the `$in` root, the retired `$fields` and the whole-chain reference), §5, §6.4
  (the `py` table, 42 → 41) and §7.1 (`UP2-E1018`)
- [x] 7.3 `004` §7/§9, `006`'s mock, `007`'s rows, `docs/operator-reference.md`, both READMEs, and the
  regenerated `docs/report/up2-report.md`
- [x] 7.4 `CHANGELOG.md`: one `[Unreleased]` entry

## 8. Gates

- [x] 8.1 `ruff format --check` / `ruff check` / `mypy` / `pytest --cov=uniparser2.core
  --cov-fail-under=95` / `up2 conformance --check`
- [x] 8.2 The `change-linter` for every edited `.py`
- [x] 8.3 `openspec validate --strict` and archive with the `openspec-archive-change` skill
