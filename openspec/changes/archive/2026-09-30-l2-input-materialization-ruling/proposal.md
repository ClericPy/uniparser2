# Proposal

## Why

The L2 node layer's input story still assumes **eager materialization**: `seed.config.input_format` decides
up front how the primary input becomes structure, and `parse.config.format` materializes it a second time.
Neither is implemented, and both are now known to be unnecessary: `css`/`css1`, `json` and `xpath` already
parse a `str` **on demand** (measured on this commit), so the format is decided by whoever consumes the
value. What eager materialization bought — one document, one parse — is a **performance** property, and a
run-scoped cache can provide it without forcing every chain to name a format.

The same conversation settled three neighbouring questions that the notes currently answer only by
implication: `globals` stays **read-only** (the caller writes it before the run; cross-node sharing belongs
to node products), no third mutable scope is introduced, and `bytes` never enters a chain.

## What Changes

- **Delete `seed.config.input_format` and `parse.config.format`.** The `seed` product is the caller's inputs
  **verbatim** — a `str` stays a `str`; `parse.input` still references a value that already exists.
- **Materialization is on demand**: the operator that needs a format parses the `str` it is given
  (`css`/`css1` → HTML, `json` → JSON text, `xpath` → XML). The capability becomes **one shared
  implementation** whose per-format entry declares its own optional dependency (TOML/CSV are stdlib, YAML is
  third-party; a missing dependency is `UP2-E1107` with the install line, exactly like `css`'s selectolax).
- **A run-scoped, bounded materialization cache**: keyed by (format, source), released with the run, never
  shared across runs, with a byte cap and LRU eviction. Eviction re-parses (correct, only slower), so a hit
  and a miss MUST be observably identical. The tree is ≈24× the text in memory (measured), which is what the
  cap is sized against.
- **The cache is load-bearing** rather than an optimization: with no eager materialization, "one document,
  one parse" is guaranteed only by it. It lands with the node layer and gets its own tests.
- **`bytes` still never enters the value domain** (measured); decoding moves from the `seed` layer to the
  caller/boundary.
- **Rejected alternatives recorded**: writable `globals` / a third mutable scope (a chain-level writable
  store makes one value evaluate differently in different fields, and needs order and rollback rules —
  against `N1`), a module-level cache inside the operators (unbounded, `Opaque` handles crossing runs,
  concurrency), and keeping eager materialization *and* the cache (two mechanisms for one property).

## Capabilities

None. This is a **design-document ruling only**: the L2 node layer does not exist yet, and the operators
already behave this way, so no implemented behavior changes. The change's `.openspec.yaml` therefore sets
`skip_specs: true`; there is no delta to merge.

## Impact

- `docs/specs/003-parse-chain-spec.md` — §3 loses `input_format` and gains §3.1 "On-demand materialization
  and the run-scoped cache"; §4 loses `parse.format`; §4.5 records both deletions; §11's two walkthrough
  chains and the legacy mapping table are updated.
- `docs/specs/001-architecture-and-value-model.md` — the `bytes` invariant's mechanism.
- `docs/specs/004-persistence-and-sop.md` — the S1 drafting line about the input contract.
- `docs/specs/007-source-decisions-and-roadmap.md` — the ruling and its tie-in to the L2 acceptance item.
- No code, no tests, no error codes, no spec delta. The measurements behind the ruling were taken on this
  commit (selectolax, 2 MB and 5 MB synthetic HTML).
