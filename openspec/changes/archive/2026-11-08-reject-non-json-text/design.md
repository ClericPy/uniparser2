# Design

## Context

See `proposal.md` — Why. The kernel already owns the rule "a chain is JSON data" in
`core/ast.py`: `loads` rejects the constants Python's decoder accepts, `dumps` passes
`allow_nan=False`, and both report `UP2-E1004`. Four other places convert the same data to and
from text without that rule: the store fingerprint, the file store's rows, the SQLite read, and the
sample runner. `up2.loads` additionally lets a `JSONDecodeError` escape, so malformed text is the
one bad chain that is not a coded failure.

## Goals / Non-Goals

**Goals**

- One implementation of "strict JSON text" for chain data, stored rows and snapshots.
- A publish that cannot write text it would refuse to read.
- A corrupt file reported with its path, not with a decoder traceback.

**Non-Goals**

- Re-validating a product at the store boundary: `export.pack` is still the single exit, and the
  store writes what it is handed.
- Changing the value domain: finite floats, lists, dicts and scalars stay exactly as they are.
- Rejecting `Infinity` in a host's own `json.loads` calls outside this package.

## Decisions

**One pair in `core.values`, next to `is_json_value`.** `dumps_json(value, *, indent, sort_keys,
separators, subject)` and `loads_json(text, *, subject)` are pure text functions, so they belong in
the kernel without touching IO or adding a dependency. `subject` is the noun the diagnostic names
("the graph", "the audit row", the file path), which keeps one message template honest across very
different call sites.

Alternative considered: a helper per layer. Rejected — three copies of `allow_nan=False` and
`parse_constant` is exactly how the first hole appeared.

**`UP2-E1004` for every text-level violation.** It is already the code for "the chain's shape/text
is not valid", and the conformance audit counts codes, not subjects. Its `CODES` description is
widened from "stage length does not match the operator arity" to the shape **and** the text that
carries it.

**The fingerprint is the publish gate.** Both stores call `graph_hash` before `_write`, so making
`canonical_graph` strict refuses a non-finite graph once, for both, before any file or row exists.
No second validation in `write_template` is needed for that case — but the writer still passes
`allow_nan=False` so the invariant is local to the code that writes the file.

**A malformed document is wrapped, not propagated.** `loads_json` converts `JSONDecodeError` into
`UP2-E1004`; the CLI's two "parse or fall back to raw text" call sites catch `Up2Error` instead,
which preserves their fallback behaviour.

## Risks / Trade-offs

- **Behaviour change**: a JSON file that Python accepts (`Infinity`) and JSON does not is now an
  error. Intended; the same change already landed for chain text and products.
- **`record_expected` gains an error path** (a non-serializable product). It already returned
  `str | None`, so no signature changes; the path only fires where the old code raised `TypeError`.

## Migration

None. Stored text that is strict JSON is read unchanged; text carrying `Infinity` is reported and
can be republished from its source.
