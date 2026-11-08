# Proposal

## Why

The kernel now refuses a non-finite float on its own JSON boundaries (`up2.dumps` / `up2.loads`,
export packing), but the layers beside it still call `json.dumps` / `json.loads` bare. Measured on
this commit:

- `FileStore.publish([["const", float("inf")]], ...)` succeeds and writes `Infinity` into the chain
  file — text no strict parser accepts, which the store's own JSON reader only survives because
  Python's decoder is permissive;
- `read_expected` reads a snapshot containing `Infinity` as `inf`, so a corrupt snapshot becomes a
  value instead of an error; `record_expected(inf)` writes `Infinity` back out;
- `up2.loads("not json")` raises a raw `JSONDecodeError`, not the `UP2-E1004` the public contract
  promises for chain text.

So "the chain is JSON data" holds only on the paths the previous change touched: the store and the
sample runner still round-trip values JSON does not have.

## What Changes

- **One strict text pair**: `dumps_json` / `loads_json` in `core.values` — `allow_nan=False`,
  `parse_constant` rejected, and a malformed document reported with `UP2-E1004`.
- **Chain text** (`core.ast`) delegates to that pair: malformed chain text becomes `UP2-E1004`
  instead of `JSONDecodeError`.
- **The store refuses an illegal graph before writing**: the fingerprint is taken over strict JSON,
  so `publish` fails with `UP2-E1004` in both stores and leaves no file behind.
- **Stored files are read strictly**: a chain file or audit line that is not JSON is reported as
  `UP2-E1004` naming the file, instead of crashing with `JSONDecodeError`.
- **Sample snapshots are strict both ways**: `read_expected` rejects a non-JSON constant and
  `record_expected` reports a non-serializable product as an error string instead of raising.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `core-evaluator`: chain text is read and written as strict JSON, so malformed text is a coded
  failure like any other bad chain.
- `template-store`: a stored graph and a sample snapshot are strict JSON on both write and read.

## Impact

- `core/values.py` (the pair), `core/ast.py` (delegate), `core/errors.py` (`UP2-E1004`'s
  description now names the JSON text), `store/fingerprint.py`, `store/file.py`, `store/sqlite.py`,
  `cli/samples.py`, `cli/main.py`.
- Docs: `04` §3 and §4.1 (strict JSON at the store boundary), `CHANGELOG.md`.
- Tests: `loads` on malformed text, publishing a non-finite graph, a corrupt chain file, and a
  snapshot carrying `Infinity`.
- **Behaviour change**: a graph or snapshot JSON that Python accepts but JSON does not is now an
  error; nothing that rounds-trips as strict JSON changes.
