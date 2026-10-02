# Tasks

## 1. The trace data structure (kernel)

- [x] 1.1 `core/values.py`: extract `text_of(value)` (the full display text) so `preview` and the
      trace's `size` read one rendering
- [x] 1.2 `core/trace.py`: `ValueView` + `value_view` (`type` / `preview` cut to 200 characters /
      `size` of the full text), `TraceEvent` (the 13 fields of `06` §5.1, plus `effect` for a
      suspension) with `to_dict`, and `Trace` (`events`, `to_list`, `get_value(seq, side=…)`, `enter`
      / `stage` / `effect`, `stamp` / `elapsed_ms`)
- [x] 1.3 `core/trace.py`: the compiled-parameter projection (`ref` / `lit` / `chain` / `fields`)
- [x] 1.4 Re-export `Trace` / `TraceEvent` / `ValueView` from `core/__init__.py` and
      `uniparser2/__init__.py`

## 2. The evaluator hook

- [x] 2.1 `core/evaluator.py`: `eval_field(..., trace=None)` records one event per **evaluated**
      stage (op / action / compiled params / input / output / state / detail / ms) and passes the
      trace into a structural operator's sub-chain
- [x] 2.2 `core/refs.py`: `Scope.child(iteration=…)` takes the fan-out position, and `each` hands
      over the element's own position (`item`)
- [x] 2.3 `core/ast.py` + `core/compile.py`: `CompiledField.name` is the field-map key the chain was
      compiled as (the trace's `field`)

## 3. The story layer

- [x] 3.1 `core/story.py`: `start(bundle, value, trace=…)`, `StoryRun.trace`, and the step position
      (`enter`) each step's events belong to
- [x] 3.2 `core/story.py`: an effect event per suspension — `request` / `batch` hand over what the
      host must send, `call` carries the function name in `action` and its compiled `with` in
      `params`
- [x] 3.3 `core/story.py`: a batch's receiving step is traced with the answer's own position as its
      `item`

## 4. The command

- [x] 4.1 `cli/main.py`: `up2 trial --trace [--json]` — the events in evaluation order, in JSON
      (including a failed or suspended run) and as one text line per event

## 5. Tests

- [x] 5.1 `tests/chains/test_trace.py`: a story with one request, one batch and an `each` fan-out —
      the step / field / stage / item numbering, the three states, the truncation and `get_value(seq)`
- [x] 5.2 `tests/chains/test_trace.py`: a failing stage's event carries `code` / `reason`; a chain run
      without a trace collects nothing and behaves as before
- [x] 5.3 `tests/chains/test_trace.py`: the effect events (request, batch, call), the compiled
      `params`, and the batch answer's `item`
- [x] 5.4 `tests/cli/test_cli.py`: `up2 trial --trace --json` over a story (suspended) and over a
      field chain (done)

## 6. Docs, gates and archive

- [x] 6.1 `003` §4.4 (per-stage trace versus suspension) and `003` §13-O6 (settled)
- [x] 6.2 `006` §5.1 (the effect shape, `get_value`, the item rule, the O6 ruling) and §10 item 4
- [x] 6.3 `004` §7-S3, §7.1 (S3 rows) and §8: `--trace` exists now
- [x] 6.4 `CHANGELOG.md` `[Unreleased]`
- [x] 6.5 Every gate of `AGENTS.md` green (`ruff format --check`, `ruff check`, `mypy`,
      `pytest --cov=uniparser2.core --cov-fail-under=95`, `up2 conformance --check`), the
      `change-linter` run over every edited `.py`, `openspec validate --strict`
- [x] 6.6 One real trace over the committed live sample site (`samples/books.toscrape.com`)
- [x] 6.7 Archive the change with `openspec-archive-change`
