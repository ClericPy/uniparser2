# Tasks

## 1. `parse_time` — automatic detection becomes the default

- [x] 1.1 Reorder the decision path in `src/uniparser2/ops/pyops.py`: explicit `format` → the built-in table → the language call with `languages=[lang]` when `lang` is given and `languages=None` otherwise → `UP2-E2007`; Verification: `uv run up2 trial` on `24. September 2026` / `yesterday` / `24 septembre 2026` with the chain `[["py","parse_time",""]]` returns the canonical string when `dateparser` is installed, and the same chain still parses `Sep 24, 2026` from the table without importing `dateparser`
- [x] 1.2 Keep the missing-engine path loud: without `dateparser` the natural-language path reports `UP2-E2008` naming the extra; Verification: monkeypatched `_import_dateparser` (or an environment without the extra) makes `["py","parse_time",""]` on `24 septembre 2026` report `UP2-E2008`, while a table shape still succeeds
- [x] 1.3 Rewrite the `UP2-E2007` fix line for the new order (no "add lang" advice) and keep `UP2-E2008`'s wording; Verification: `uv run pytest tests/ops/test_pyops.py -k parse_time` is green, including the three dateparser stand-in branches (missing dependency / returns `None` / raises)

## 2. `parse_time` — `date_order` and `now`

- [x] 2.1 Add `date_order` (`MDY` / `DMY` / `YMD`, `Kind.LITERAL`, optional, validated at compile time with `UP2-E1005`), order the table's ambiguous slash pair with it and pass it as `settings={"DATE_ORDER": …}`; Verification: `up2 trial` gives `2026-04-03` for both `03/04/2026` and `03/04/2026 15:30` by default and `2026-03-04` for both under `{"date_order": "MDY"}`, and `{"date_order": "YDM"}` fails compilation with `UP2-E1005`
- [x] 2.2 Add `now` (`Kind.REF_OR_LITERAL`, optional) and pass it as `settings={"RELATIVE_BASE": …}`; Verification: `{"now": "2026-01-01 12:00:00"}` and `{"now": "$globals.now"}` make `tomorrow` return `2026-01-02 12:00:00`, while a non-canonical `now` fails with `UP2-E1005`
- [x] 2.3 Reject `format` + `lang` together at compile time with `UP2-E1005` and a fix line naming the alternatives; Verification: `["py","parse_time",{"format":"%Y-%m-%d","lang":"en"}]` exits 1 from `up2 lint` at the parameter pointer

## 3. `strftime`

- [x] 3.1 Register the new `py` action `strftime` (one parameter: the output layout) in `src/uniparser2/ops/pyops.py`, rendering the canonical string through the allowlist of D6; Verification: `["py","strftime","%Y/%m/%d"]` on `2026-09-24 15:30:00` returns `2026/09/24`, and a receiver that is not the canonical shape reports `UP2-E2007` naming `py.parse_time`
- [x] 3.2 Validate the layout at compile time against the allowlist, with the reason per rejected family in the fix line; Verification: `up2 lint` exits 1 with `UP2-E1005` for `%c`, `%a`, `%z`, `%s` and `%Q`, and exits 0 for `%Y/%m/%d` and `%Y-W%W`
- [x] 3.3 Keep the rendering independent of the locale and the platform: no `dateparser`, no `strftime` directive outside the allowlist reaches the C library; Verification: `["py","strftime","%B"]` is rejected at compile time, and the accepted layouts produce the same text under `LC_TIME=C` and the system locale

## 4. Tests and conformance

- [x] 4.1 Add the new behavior cases to `tests/ops/test_pyops.py` (automatic path with three languages, relative expression with and without `now`, both `date_order` outcomes, the rejected combination, `strftime` success and each rejected directive family); Verification: `uv run pytest tests/ops/test_pyops.py` is green with no new skip
- [x] 4.2 Declare the new pair for the conformance audit and keep the count truthful (`covers("py","strftime")`, 59 → 60 pairs, no new error code); Verification: `uv run up2 conformance --check` exits 0 and reports 60 declared pairs = 60 covered pairs, 25 codes
- [x] 4.3 Update the report tooling (`tools/demo_report.py`: the tier entry and cases for `strftime`, plus a `parse_time` case for the automatic path) and render the committed catalogue again; Verification: `uv run python tools/demo_report.py` exits 0 with no "not Ok" warning, and `UP2_UPDATE_REPORT=1 uv run pytest tests/report` then `uv run pytest tests/report` is green

## 5. Documentation

- [x] 5.1 Update `docs/specs/002-dsl-spec-triples-and-operators.md` §6.4 (the function count and table, 31 → 32) and §6.7 (the decision order, `date_order`, `now`, the rejected combination, the `strftime` action and its allowlist); Verification: every example chain in the note compiles through `uv run up2 lint`, and the counts in the note match `uv run up2 ops --json`
- [x] 5.2 Update `docs/operator-reference.md` (the `py` table, a `strftime` row, a worked example that reshapes a canonical time) and both READMEs (the function count, the `time` extra description); Verification: the numbers and the extra list in both READMEs and the reference page match `uv run up2 ops --json` and `pyproject.toml`
- [x] 5.3 Bump `__version__` to `0.2.0` (`005` §7, new capability) and record the change in `CHANGELOG.md` under `[Unreleased]`: the automatic path and the two parameters (Added), `strftime` (Added), the `format` + `lang` rejection and the removed "add lang" advice (Changed / Fixed); Verification: `uv run up2 --version` prints `0.2.0`, the wheel builds with the same version, and the CHANGELOG names the observable difference

## 6. Gates and wrap-up

- [x] 6.1 Run the definition of done of `AGENTS.md` plus the graded post-edit checks of the change-linter at L2 with the security axis: `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`, `uv run pytest --cov=uniparser2.core --cov-fail-under=95`, `uv run up2 conformance --check`; Verification: all five commands exit 0 and every change-linter axis passes, with a missing tool or an unrunnable axis reported truthfully
- [x] 6.2 Archive the change and merge its capability specs into `openspec/specs/`; Verification: `openspec list` reports no active change, `openspec list --specs` lists `time-parsing` and `time-formatting`, and `openspec validate --specs` passes
