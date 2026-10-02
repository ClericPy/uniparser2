# Tasks

## 1. The rule, in the docs

- [x] 1.1 `03` §10: the `L12` row (the flow is acyclic), and the §10 note that replaces "not implemented
  yet" with the rule and the rejected reading
- [x] 1.2 `03` §12.5: the deviation record `D-03-5` — the graph, the rejected union reading, and the
  proof that the rule equals "no backward jump that loops"
- [x] 1.3 `03` §13 O9: settled, with the rule, `next`'s freedom and the pointer to §12.5
- [x] 1.4 `02` §7: the `UP2-E1017` row in the compile-time code table
- [x] 1.5 `01` §4.4: the cycle row stops saying a cycle cannot be expressed
- [x] 1.6 `CHANGELOG.md`: one `[Unreleased]` entry in the file's existing style

## 2. The check

- [x] 2.1 `core/errors.py`: `UP2-E1017` in `CODES`
- [x] 2.2 `core/story.py`: `_lint_flow` + `_LoopWalk` — the one-edge-per-step graph, the depth-first
  walk, and the diagnostic (`_cycle`) carrying the travel path and the pointer at the closing `next`
- [x] 2.3 `core/story.py`: `compile_story` runs the check after `next` / `exit` resolve, so `UP2-E1016`
  is still what a dangling target gets
- [x] 2.4 Update the four runtime-code cases whose self-referential `next` is now a compile-time loop:
  each gains a plain receiver step and still asserts its run-time code

## 3. Tests

- [x] 3.1 A three-step cycle is rejected with `UP2-E1017`, the travel path in the message and the
  pointer at the closing `next`
- [x] 3.2 A step that jumps to itself is rejected
- [x] 3.3 A backward `next` into a region that cannot reach it compiles **and runs** (the samples'
  fan-out shape)
- [x] 3.4 A backward `next` followed by a forward jump compiles and runs (the books-sample shape)
- [x] 3.5 A dangling `next` / `exit` still gives `UP2-E1016`

## 4. Gates

- [x] 4.1 `ruff format --check` / `ruff check` / `mypy` / `pytest --cov=uniparser2.core
  --cov-fail-under=95` / `up2 conformance --check`
- [x] 4.2 `up2 lint` on both committed sample bundles, output recorded
- [x] 4.3 The `change-linter` for every edited `.py`
- [x] 4.4 `openspec validate --strict`, then archive with the `openspec-archive-change` skill
