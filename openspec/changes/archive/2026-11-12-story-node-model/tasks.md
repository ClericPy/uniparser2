# Tasks

## 1. Documentation first

- [x] 1.1 Rewrite `docs/specs/003-parse-chain-spec.md` around `globals` + `nodes`: the story shape,
      node bodies, field-map locals, node calls, `type`, `run`, the synchronous contract, the error
      table, the lint checklist, the walkthrough and the deviation records.
- [x] 1.2 Update `docs/specs/002-dsl-spec-triples-and-operators.md`: the `node` and `type` stages,
      the `udf` argument forms, `py.sleep` / `py.filter`, the type set (drop `Request` /
      `RequestBatch`), and the error table (`UP2-E1018` retired, `UP2-E1010` / `UP2-E1017`
      restated).
- [x] 1.3 Update `docs/operator-reference.md` by hand for the new actions and stages.
- [x] 1.4 Regenerate `docs/report/up2-report.md` with `UP2_UPDATE_REPORT=1 uv run pytest tests/report`
      after the registry changes.

## 2. Tests first

- [x] 2.1 Replace `tests/chains/test_story.py` with cases for the node shape, node bodies, node
      calls, the call graph, `run`, globals overrides, the udf table and the JSON exit.
- [x] 2.2 Add `tests/ops/test_node.py` and `tests/ops/test_typeop.py`; extend `tests/ops/test_pyops.py`
      with `sleep` and `filter`.
- [x] 2.3 Update `tests/chains/test_trace.py`, `tests/chains/test_public_and_try.py`,
      `tests/chains/test_type_registry.py` for the node model and the trace's `node` field.
- [x] 2.4 Update the CLI, snapshot and store tests for `--node`, the first-node default, and the
      missing-udf diagnostic.

## 3. Kernel

- [x] 3.1 Rewrite `core/story.py`: `CompiledNode`, `CompiledStory`, `compile_story`, `run`, the node
      runner, the field-map writer and the node-call graph lint.
- [x] 3.2 Remove the whole-chain-reference carrier from `core/ast.py`, `core/compile.py`,
      `core/evaluator.py` and `core/trace.py`; `[]` becomes identity.
- [x] 3.3 Add the node runner to `core/registry.Call` and thread it through `eval_field`, the `each`
      sub-chain runner and the `node` operator.
- [x] 3.4 Add `eval_field_map` to `core/evaluator.py`; make field maps and `each` write every field
      to the current scope.
- [x] 3.5 Add `Scope.udfs`; keep the run-scoped table shared across child scopes.
- [x] 3.6 Update `core/limits.py` (`MAX_STORY_NODES`), `core/errors.py` (`UP2-E1018` retired,
      `UP2-E1010` / `UP2-E1017` wording) and `core/types.py` (drop `Request` / `RequestBatch`).
- [x] 3.7 Update `core/udfs.py` for the run-scoped table view and `core/__init__.py` /
      `uniparser2/__init__.py` exports (`run` in, `start` / `StoryRun` out).
- [x] 3.8 Bump `__version__` to `0.7.0`.

## 4. Operators

- [x] 4.1 Add `ops/node.py` and `ops/typeop.py`.
- [x] 4.2 Rewrite the `udf` argument binding (`DTO` / `*` / `**` / explicit) and the run-table
      lookup; reject awaitables with `UP2-E2009`; stop rejecting non-JSON host objects.
- [x] 4.3 Add `py.sleep` and `py.filter`; keep the allowlist's named-parameter model.
- [x] 4.4 Keep `fetch` object-only; build a request from a URL string with
      `["ctx","dict",{"url":"obj"}]` in the samples, the README and the runnable example.

## 5. Migration

- [x] 5.1 Rewrite `samples/books.toscrape.com/books/site.json` and its `host.py`; register `fetch`
      and `store_books`; the run starts at the `store` node.
- [x] 5.2 Rewrite `samples/quotes.toscrape.com/quotes/site.json` and its `host.py`.
- [x] 5.3 Update `cli/main.py` (lint counts, `trial --node`, missing-udf output) and
      `cli/samples.py` (the run-based snapshot runner).
- [x] 5.4 Update `store/base.py` and the store tests for the new story shape.

## 6. README

- [x] 6.1 Rewrite the hero in `README.md` and `README.zh-CN.md`: the one-line pitch, the GitHub
      description, a 20-line runnable demo and `<details>` sections.
- [x] 6.2 Add the tested GitHub pinned example to both READMEs once the model runs end to end.

## 7. Gates

- [x] 7.1 `uv run ruff format --check`
- [x] 7.2 `uv run ruff check`
- [x] 7.3 `uv run mypy`
- [x] 7.4 `uv run pytest --cov=uniparser2.core --cov-fail-under=95`
- [x] 7.5 `uv run up2 conformance --check`
- [x] 7.6 `openspec validate story-node-model --strict`
