# Proposal

## Why

`py.parse_time` is the operator's answer to "natural language → time", but it only reaches `dateparser`
when the chain names a language: `["py", "parse_time", ""]` walks a fixed table of machine shapes and
then fails, so a feed carrying `24. September 2026` or `yesterday` needs a parameter most chains do not
care about. Measured on the current commit:

| Input | `["py", "parse_time", ""]` | `{"lang": "de"}` |
|---|---|---|
| `24. September 2026` | `UP2-E2007` | ok |
| `yesterday` | `UP2-E2007` | ok |
| `Sep 24, 2026` | ok (table) | ok |

Two further gaps become visible once the parser is reached by default:

- **Ambiguity**: `03/04/2026` is a different date in `en` and in `de`, and no detector can resolve it.
  On the current commit the same writing even gives **two different dates depending on whether a time
  part follows**: `03/04/2026` → `2026-04-03` (the built-in table is day-first) while
  `03/04/2026 15:30` → `2026-03-04` (the engine defaults to month-first). No knob exists, and the split
  is stated nowhere.
- **The base clock**: relative expressions resolve against `datetime.now()` (measured:
  `["py", "parse_time", "en"]` on `yesterday` returns the current date minus one day), so the result of
  a chain depends on when it runs, with no way to pin it.

On the output side there is no way at all to render another layout: the canonical
`%Y-%m-%d %H:%M:%S` string can only be reshaped with `slice` / `replace` / `re`.

## What Changes

- `py.parse_time` reaches `dateparser` **without a parameter**. The order becomes: an explicit `format`
  → the built-in table → automatic language detection (when `dateparser` is installed) → `UP2-E2007`.
  `lang` becomes optional and only restricts detection to one language.
- Two optional parameters are added: `date_order` (`MDY` / `DMY` / `YMD`, validated at compile time) for
  the ambiguous numeric shapes — it orders the built-in table's slash pair **and** the engine, so a plain
  and a time-bearing writing can no longer disagree, with `DMY` as the documented default — and `now` (a
  `ref_or_literal` value such as `"$globals.now"`) which pins the base clock of relative expressions.
  Without `now` the wall clock is used, and that default is documented.
- `lang` and `format` together are rejected at compile time (`UP2-E1005`): `format` wins over the
  language fallback, so the combination can only hide a parameter that never has an effect.
- A new `py` action `strftime` renders the canonical string in another layout:
  `["py", "strftime", "%Y/%m/%d"]`, a single-parameter action, so it is written with a plain value.
  The layout is validated at compile time against an allowlist of locale-free, platform-stable numeric
  directives; name-bearing (`%a` / `%A` / `%b` / `%B` / `%p` / `%c` / `%x` / `%X`), zone-bearing
  (`%z` / `%Z`, empty on a zone-less value), platform-specific (`%e` / `%k` / `%l` / `%G` / `%V`) and
  epoch (`%s`, which would have to assume a zone) directives are rejected, with the reason in the fix
  line. No `to_datetime` action is introduced: the canonical string is a lossless representation of a
  datetime, so formatting re-parses it, while an object inside the chain would break the JSON value
  domain (Store, UDFs, `up2 trial` readability).
- Dependencies stay optional: without `uniparser2[time]` the natural-language path reports
  `UP2-E2008` and names the extra; `uniparser2[all]` installs everything and the local HTML report
  lists which engines are missing.

## Capabilities

### Modified Capabilities

- `time-parsing`: the decision order of `py.parse_time`, the two new parameters, the documented
  defaults (automatic detection, `MDY`, wall clock), and the compile-time rejection of `format` + `lang`.

### New Capabilities

- `time-formatting`: `py.strftime` — rendering the canonical time string in another layout, with its
  directive allowlist and the compile-time validation of a layout.

## Impact

- `src/uniparser2/ops/pyops.py` — `parse_time`'s decision order, validation and language call; the new
  `strftime` action with its directive allowlist.
- `tests/ops/test_pyops.py` — cases for the automatic path, `date_order`, `now`, the rejected
  combination and `strftime` (including rejected directives and a non-canonical receiver).
- `docs/specs/002-dsl-spec-triples-and-operators.md` §6.4 / §6.7 — the function count, the parameter
  table and the decision order; `docs/operator-reference.md`, both READMEs and `CHANGELOG.md`.
- `tools/demo_report.py` — the commonness tier entry and cases for the new action; the committed
  catalogue `docs/report/up2-report.md` is rendered again.
- `up2 conformance --check`: one new `(operator, action)` pair (59 → 60), no new error code (25).
- `src/uniparser2/__init__.py` — version `0.1.0` → `0.2.0` (`005` §7: a new capability bumps the minor).
- No packaging change: `time` stays an optional extra and `all` already includes it.
