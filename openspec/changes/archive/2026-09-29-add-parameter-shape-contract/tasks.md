# Tasks

## 1. `py` parameter validation

- [x] 1.1 Add the scalar-parameter table of design D3 (function → parameter → required scalar type) and one check function to `src/uniparser2/ops/pyops.py`, called from the existing `precompile` beside `_check_url_part` / `_check_time_format`, raising `UP2-E1005` with the parameter's pointer and a fix line that shows the accepted writing; Verification: `uv run up2 lint` exits 1 with `UP2-E1005` at the parameter for `["py","urljoin",{"base":"https://example.com/news/"}]`, `["py","slice",{"spec":"0:4"}]`, `["py","split",{"sep":{}}]`, `["py","split",{"sep":",","maxsplit":{}}]`, `["py","getitem",{"index":{}}]`, `["py","get",{"key":{}}]`, `["py","replace",{"old":{},"new":""}]` and `["py","sort",{"key":{}}]`
- [x] 1.2 Keep the existing `py` validations working and the legal container value untouched; Verification: `uv run up2 trial` still reports `{"a": 1}` for `[["ctx","get","locals.nope"],["py","default",{"a":1}]]`, `["py","split",{"sep":",","maxsplit":1}]` still splits `a,b,c` into `["a","b,c"]`, and `["py","urlsplit","netloc"]` / `["py","parse_time",{"format":"%d.%m.%Y"}]` still compile and evaluate as before

## 2. Parameter-slot shape in the self-description

- [x] 2.1 Add `param_form` to `ActionReport` and to `report_dicts()` in `src/uniparser2/core/registry.py`, derived from the declared parameters minus the ones the action slot provides (the existing `Op.action_params` hook), with the machine values `none` / `value` / `named`; Verification: `uv run up2 ops --json` reports `"param_form": "value"` for `py.slice`, `"named"` for `re.group`, `"none"` for `py.strip` and `"value"` for the `css` / `css1` accessor `@<attribute>`
- [x] 2.2 Render the same three states in the human `up2 ops` view of `src/uniparser2/cli/main.py`; Verification: `uv run up2 ops` prints the shape for every action, and for the same action the human and `--json` views agree

## 3. Tests

- [x] 3.1 Add the negative cases of 1.1 and the regression guards of 1.2 to `tests/ops/test_pyops.py`, asserting the error code, the pointer and (for at least one case) the fix text; Verification: `uv run pytest tests/ops/test_pyops.py` is green and the new cases really run (no skip)
- [x] 3.2 Add the report-field cases to `tests/ops/test_registry.py` — one action per state, including the accessor whose parameter the action slot provides — and update the `up2 ops` assertions of `tests/cli/test_cli.py`; Verification: `uv run pytest tests/ops/test_registry.py tests/cli/test_cli.py` is green
- [x] 3.3 Confirm the conformance audit is untouched: no new `CODES` entry, still 59 pairs and 25 codes; Verification: `uv run up2 conformance --check` exits 0 and prints 59 declared pairs = 59 covered pairs

## 4. Documentation

- [x] 4.1 Update design note `02` §4 (the shape rule states that a named object is not a parameter binding for a single-parameter action, and that a container is a value there) and §6.4 (the `py` parameter table of D3, including the deliberately excluded `default.value` / `join.sep` / `parse_time.lang`); Verification: every example chain in the note still compiles through `up2 lint`, and the note's rule matches the measured behavior of 1.1 and 1.2
- [x] 4.2 Add the `param_form` field to the capability self-description list of design note `01` §7, completing that row so it also names the keys it previously described only in prose (`actions`, `params`, `available`, `accepts_missing`, `requires` / `missing`); Verification: every key of a `up2 ops --json` action object is named in the row, checked by comparing the key set against the row text
- [x] 4.3 Record the change in `CHANGELOG.md` under `[Unreleased]`: the `py` compile-time validation (Fixed or Changed) and the new self-description field (Added); Verification: the entry names the affected operator, the reused error code and the observable difference (lint-time instead of runtime)

## 5. Gates and wrap-up

- [x] 5.1 Run the definition of done of `AGENTS.md` plus the graded post-edit checks of the change-linter at L3 with the security axis: `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`, `uv run pytest --cov=uniparser2.core --cov-fail-under=95`, `uv run up2 conformance --check`; Verification: all five commands exit 0 and every change-linter axis passes, with any missing tool or unrunnable axis reported truthfully instead of being claimed as green
- [x] 5.2 Archive the change and merge its capability spec into `openspec/specs/dsl-operators/spec.md`; Verification: `openspec list` reports no active change, `openspec list --specs` lists `dsl-operators`, and `openspec validate --specs` passes
