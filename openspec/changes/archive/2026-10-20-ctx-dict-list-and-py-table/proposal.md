# Proposal

## Why

`ctx.map` is one action with two result shapes: an array of paths yields a list and an object of paths
yields a dict. The name says neither, so a reader cannot tell what a stage produces without checking the
parameter's shape. Separately, the `py` allowlist has no action that turns a mapping into something a
field chain can iterate, so "iterate an object" is impossible on the default install — `each` requires a
list and `py.list` refuses a mapping. Finally, the conversion failures of `str` / `int` / `float` /
`bool` / `list` / `from_json` share a fix text that recommends another operator as a fallback, which is
wrong twice: an error is an error, and the recommended fallback cannot catch a failure anyway.

## What Changes

- **`ctx.map` is split** into `ctx.dict` (an object of name → path) and `ctx.list` (an array of paths), so
  the action name states the result shape and the two line up with `**` / `*` argument payloads.
  **BREAKING**
- **`py.items` is added**: a mapping becomes `[[key, value], …]`, which `each` can iterate (with
  `py.getitem 0` / `py.getitem 1`). `py` holds 42 functions afterwards.
- **The conversion actions' fix text stops recommending a fallback operator**; it states the expected
  input and points at the upstream stage instead.
- **The local report tool's stale wording is corrected**: its `ctx.set` note still names `fields`, a root
  removed earlier.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `dsl-operators`: the scope operator's actions name their result shape; the `py` allowlist gains
  `items`; the conversion actions describe their input rather than a fallback.

## Impact

- Operators: `ops/ctx.py` (the split), `ops/pyops.py` (`items`, the conversion fix text).
- Docs: note `02` §6.4 / §6.8, `docs/operator-reference.md`, the regenerated report, `CHANGELOG.md`.
- Tooling: `tools/demo_report.py` (the `ctx.set` note, cases for the two new actions and `py.items`).
- Tests and conformance: every `ctx.map` case moves to `ctx.dict` / `ctx.list`; `py.items` gets its own.
