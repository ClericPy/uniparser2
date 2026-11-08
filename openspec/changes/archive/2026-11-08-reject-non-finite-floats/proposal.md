# Proposal

## Why

The value domain is JSON, and JSON has no `Infinity` / `NaN`. `is_json_value` accepts **any** float
— including the non-finite ones — so they pass the single exit and reach the serializers. Measured on
this commit:

- `pack(float("inf"))` → `Ok(inf)`, so a chain product can be non-finite;
- `up2 trial --json` prints `{"state": "ok", "value": Infinity}` — **not valid JSON**; a strict
  parser (JS `JSON.parse`, Go `encoding/json`, serde) rejects the whole document;
- `up2.dumps([["const", float("inf")]])` prints `[["const",Infinity]]` — chain text that is not JSON,
  which round-trips only because Python's decoder is permissive.

So "every value leaving a chain passes through `core/export.pack`" and "the chain is data (JSON)" both
hold for the shapes they name and fail for this one value.

## What Changes

- **A float must be finite to be a JSON value**: `is_json_value` rejects `inf` / `-inf` / `nan`, which
  makes the exit packing rule (`UP2-E2003`) refuse a product that carries one, at the step that
  produced it, including nested in a list or a dict.
- **Chain text may not carry them either**: `loads` rejects the non-JSON constants Python's decoder
  accepts, and `dumps` refuses to write them (`UP2-E1004`, "a chain is JSON data").
- **The computing operators keep computing**: `py.float("1e999")` still answers `inf` mid-chain —
  the failure belongs at the boundary, which is where the export rule already lives.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `core-evaluator`: the JSON value domain excludes a non-finite float, in a product and in chain text.

## Impact

- `core/values.py` (`is_json_value`), `core/export.py` (the fix line names the finite requirement),
  `core/ast.py` (`loads` / `dumps`).
- Docs: `01` §4 (the value domain), `CHANGELOG.md`.
- Tests: the predicate, `pack` (top-level and nested), `loads`, `dumps`, and a CLI run whose product
  is `inf` now reporting `UP2-E2003` instead of printing `Infinity`.
- **Behaviour change**: a chain whose product is non-finite used to emit invalid JSON; it now fails
  with a diagnostic. Nothing that produced a JSON value changes.
