# Proposal

## Why

Real feed formats carry a UTC offset — or a `Z` — inside the timestamp: RSS 2.0 `pubDate` is RFC 822
(`Thu, 24 Sep 2026 15:30:00 +0800`) and Atom 1.0 `updated` is ISO 8601 (`2026-09-24T15:30:00Z`).
`py.parse_time` called without parameters walks a fixed list of **zone-less** standard-library
formats, so both canonical feed dates end in `UP2-E2007`. A chain author reading a feed today must
already know to pass `{"lang": "en"}` or to hand-write `{"format": "%a, %d %b %Y %H:%M:%S %z"}`.
Measured on the current commit:

| Input | `["py", "parse_time", ""]` | `{"lang": "en"}` |
|---|---|---|
| `2026-09-24T15:30:00` | ok | ok |
| `2026-09-24T15:30:00Z` | `UP2-E2007` | ok |
| `2026-09-24T15:30:00+08:00` | `UP2-E2007` | ok |
| `Thu, 24 Sep 2026 15:30:00 +0800` | `UP2-E2007` | ok |

## What Changes

- The built-in standard-library format table gains zone-bearing entries so that RFC 822 and
  zone-bearing ISO 8601 timestamps parse with **no parameters**, both in the `T`-separated ISO shape
  and in the RFC 822 shape, with `Z` / `+0800` / `+08:00` offsets and with optional fractional
  seconds.
- Named zone **names** (`GMT`, `UTC`) are accepted in the RFC 822 shape.
- The offset is consumed, not applied: the result stays the canonical wall-clock string
  `%Y-%m-%d %H:%M:%S`, which is what the operation already returns for its existing formats and for
  the `{"lang": ...}` path. No timezone conversion is introduced.
- No new operator, action, parameter, error code or dependency. `{"lang": ...}` and
  `{"format": ...}` keep working exactly as before, and an explicit `format` still takes precedence.
- The format list recorded in the design notes and the format-table test are extended accordingly.

## Capabilities

### New Capabilities

- `time-parsing`: the accepted inputs of `py.parse_time` when no explicit `format` parameter is
  given, including the canonical feed-date shapes and the "offset is consumed, wall clock is kept"
  rule. (`openspec/specs/` currently holds no capabilities, so this is introduced here.)

### Modified Capabilities

- None. Spec-level behavior that already exists elsewhere is untouched.

## Impact

- `src/uniparser2/ops/pyops.py` — the `_TIME_FMTS` table and, if needed, the shape of the parse loop.
- `tests/ops/test_pyops.py` — the format-table case list and its parameterized test.
- `docs/specs/002-dsl-spec-triples-and-operators.md` §6.6 — the format list / accepted-input text.
- No API, packaging, dependency or CLI change; `up2 conformance --check` is unaffected because the
  `(operator, action)` pair and the error codes already exist.
