# Tasks

## 1. O11 — a missing step product is skipped

- [x] 1.1 `core/story.py`: `_parse_product` answers "no product" for a `Missing` chain outcome, and
  `_step_product` returns it without recording a product or appending to the exit output
- [x] 1.2 `core/story.py`: a skipped receiving step resumes at the step after it (single request), and a
  fan-out joins as before
- [x] 1.3 Tests: a skipped step contributes nothing to the exit, nothing is recorded for a later
  reference, and a skipped receiving step continues the run
- [x] 1.4 Docs: `03` §9 states the rule, `03` §13 O11 is marked settled

## 2. O12 — a dotted reference refuses a callable

- [x] 2.1 `core/refs.py`: `_walk_attribute` refuses a callable with `UP2-E2002`, the same message shape
  and the same fix hint as `py.getattr`
- [x] 2.2 Tests: the refusal's code, message and fix, and its agreement with `py.getattr`
- [x] 2.3 Docs: `03` §13 O12 marked settled, `002` §3.1 states the dispatch and the refusal

## 3. Gates

- [x] 3.1 `ruff format --check` / `ruff check` / `mypy` / `pytest --cov=uniparser2.core
  --cov-fail-under=95` / `up2 conformance --check`
- [x] 3.2 The `change-linter` for every edited `.py`
- [x] 3.3 `openspec validate --strict` and archive with the `openspec-archive-change` skill
