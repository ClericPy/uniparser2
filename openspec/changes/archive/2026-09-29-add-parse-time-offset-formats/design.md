# Design

## Context

`py.parse_time` has three paths today (see `proposal.md` - Why for the measurements):

- an explicit `format` parameter → parse with exactly that format; a mismatch raises `UP2-E2007`;
- a `lang` parameter → the optional language parser, which already reads offsets;
- otherwise → the value is trimmed and tried against the fixed tuple `_TIME_FMTS` in
  `src/uniparser2/ops/pyops.py` (first match wins), and the result is rendered as
  `%Y-%m-%d %H:%M:%S`.

`_TIME_FMTS` currently holds only zone-less shapes (ISO without a zone, `/`, `.`, CJK date units,
`%Y%m%d`, `d/m/Y`, `m/d/Y`, and two month-name shapes). Constraints that shape the approach: the
default path must stay dependency-free (`dateparser` is optional and only reached through `lang`),
the value domain is a JSON tree so the result stays a string, and the DSL surface must not grow.

## Goals / Non-Goals

**Goals**

- The two canonical feed timestamp shapes parse with no parameters: RFC 822 (`Thu, 24 Sep 2026
  15:30:00 +0800`, also with `GMT`/`UTC`) and zone-bearing ISO 8601 (`...T15:30:00Z`,
  `+08:00`, `+0800`, with optional fractional seconds).
- The output shape, the precedence of `format`/`lang`, and the `UP2-E2007` failure path stay exactly
  as they are.

**Non-Goals**

- No UTC normalisation and no timezone-aware output (see Decision 2).
- No new parameter, operator, action, error code or dependency.
- Not every RFC 822 variant: two-digit years, obsolete military zones and comments in parentheses
  stay unsupported, and may be added if a real source needs them.

## Decisions

1. **Extend `_TIME_FMTS` instead of falling back to the language parser.** Alternative considered:
   "when nothing matches, try `dateparser`". Rejected — it would make the default result depend on an
   optional dependency and on heuristics, so the same chain could return different values on two
   hosts. The table stays the deterministic path.
2. **Consume the offset, keep the wall clock.** The operation's documented output is the canonical
   `%Y-%m-%d %H:%M:%S` string, and the existing `lang` path already behaves this way (measured:
   `...T15:30:00Z` and `...T15:30:00+08:00` both return `2026-09-24 15:30:00`). Alternative: normalise
   to UTC — rejected *for this change*, because it would silently change existing `lang` results and
   any stored value; correct cross-zone ordering deserves its own explicit parameter and its own
   change.
3. **Append the new entries, keep the existing order.** Order is not load-bearing: a zone-less value
   cannot match a `%z`/`%Z` entry and a zone-bearing value cannot match a zone-less entry, so
   appending keeps the diff minimal and the existing table (and its CJK comment) readable.
4. **`%z` covers the numeric offsets and `Z`; `%Z` covers the named zones.** CPython's `%z` accepts
   `Z`, `+0800` and `+08:00` (Python ≥ 3.7; the project floor is 3.12), while `%Z` is what reads
   `GMT`/`UTC` in the RFC 822 shape. Verified with `strptime` before writing this design.
5. **Fractional seconds via `%f`**, as a separate entry so the whole-second entry keeps working.

## Risks / Trade-offs

- **Locale sensitivity**: `%a`/`%b` parse month/weekday names in the *current* locale. This is not a
  new class of risk — `_TIME_FMTS` already carries `%d %b %Y` and `%b %d, %Y` — but the RFC 822 rows
  are the first ones to depend on it, so the tests must not assume a non-English locale.
- **`%Z` is best-effort**: it recognises the host's local zone names; an unrecognised name still ends
  in `UP2-E2007`, which is a safe failure.
- **A previously failing input now parses.** A caller that used `UP2-E2007` to detect "this is not a
  date" will now get a value for zone-bearing strings. Acceptable, and worth one line in the release
  notes.
- **Only the shapes listed above are covered**; anything else keeps failing rather than guessing.

## Open Questions

- Decision 2 (wall clock vs UTC) is a deliberate default, not a settled product decision. If
  cross-feed sorting must be correct, add an explicit parameter (for example `{"tz": "utc"}`) in a
  later change instead of changing this default. Confirmation is requested before applying.
