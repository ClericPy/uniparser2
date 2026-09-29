# Tasks

## 1. Implementation

- [x] 1.1 Add the zone-bearing entries to `_TIME_FMTS` in `src/uniparser2/ops/pyops.py`: `%Y-%m-%dT%H:%M:%S%z`, `%Y-%m-%dT%H:%M:%S.%f%z`, `%a, %d %b %Y %H:%M:%S %z`, `%a, %d %b %Y %H:%M:%S %Z`, `%Y-%m-%d %H:%M:%S %z`
- [x] 1.2 Confirm the surrounding parse loop needs no change (trim → first match → render as `%Y-%m-%d %H:%M:%S`); kept the existing entry order and the CJK comment untouched
- [x] 1.3 Confirm an explicit `format` still takes precedence and the language fallback is still reachable (the existing `format`/`lang` cases stay green)

## 2. Tests

- [x] 2.1 Extended the parameterized format-table test in `tests/ops/test_pyops.py` with `Sat, 26 Sep 2026 10:30:00 +0800`, `Sat, 26 Sep 2026 10:30:00 GMT`, `2026-09-26T10:30:00Z`, `2026-09-26T10:30:00+08:00`, `2026-09-26T10:30:00+0800`, `2026-09-26T10:30:00.000+08:00`, `2026-09-26 10:30:00 +0800`
- [x] 2.2 Added `test_parse_time_offset_is_consumed_not_applied`: `...Z` and `...+08:00` return the same `2026-09-26 10:30:00`
- [x] 2.3 Added `test_parse_time_zone_bearing_shapes_agree_with_the_zone_less_shape`: the zone-less, `Z` and `+00:00` spellings all return `2026-09-26 10:30:00`
- [x] 2.4 Extended the whitespace case to a zone-bearing value (`  2026-09-26T10:30:00Z  `)
- [x] 2.5 The unreadable-value case was already covered by `test_parse_time_unparsable_text_without_lang_is_e2007` (still green); the explicit-`format` cases are unchanged

## 3. Documentation

- [x] 3.1 Updated the `py.parse_time` section of `docs/specs/002-dsl-spec-triples-and-operators.md` (§6.6): the function row now names the two feed timestamp shapes, and the note states that a zone is consumed and never shifts the result, with the failure path unchanged
- [x] 3.2 Updated the RSS/Atom guidance in `demo.py`: both feed date chains now use `["py", "parse_time", ""]`, and the closing note no longer claims RFC 822 / zone-bearing ISO need `{"lang": "en"}`. No other committed note made that claim (`demo_report.py` parses a zone-less value)

## 4. Verification

- [x] 4.1 `uv run ruff format --check` and `uv run ruff check`
- [x] 4.2 `uv run mypy` (54 files, strict)
- [x] 4.3 `uv run pytest --cov=uniparser2.core --cov-fail-under=95` — 380 passed, 3 skipped, 98.37%
- [x] 4.4 `uv run up2 conformance --check` — 59/59 pairs, 25 codes, PASS
- [x] 4.5 `uv run python demo.py` and `uv run python demo_report.py` — both exit 0
- [x] 4.6 Post-edit checks (`change-linter`, L4 + `--security`): all green once the stale `VIRTUAL_ENV` is pointed at the project `.venv` (otherwise `ty`/`pyrefly`/`pyright` resolve a leftover uv cache environment and report a false `pytest` missing-import)
