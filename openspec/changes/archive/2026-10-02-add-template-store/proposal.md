# Add the template store (L3, first slice)

## Why

L1 and L2 are done: a chain is data, compiles, runs and is snapshotted. What does not exist yet is
anywhere to **keep** one. `04` §1–§6 designs that layer in full — a `Template` row per chain,
`template_audit` for the trace, a `TemplateStore` protocol with two implementations, a `blake2s`
fingerprint, and the three gates a `publish` must pass — and the roadmap (`07` §3) makes it the first
slice of L3, the binding layer where `root_domain` / `tpl_key` appear for the first time.

The pieces are all designed and none of them is implemented: `errors.CODES` deliberately stops at
`UP2-E2019` ("all of `E3xxx` are not in this table; they join it as their layer lands"), there is no
`store/` package, and `up2` has no storage command. This change lands §1–§6 and stops there: the
`S0–S7` SOP walkthrough and `up2 doctor` are a later slice.

## What Changes

- **`store/` lands as its own layer** (stdlib only, synchronous, the only layer that touches disk,
  `core/` untouched apart from the code table). It holds the models (`Template`, `TemplateMeta`,
  `AuditRow`, `PublishResult`, `Status`, `Source`), the fingerprint (§3), the `TemplateStore`
  protocol (§4) and two implementations: `FileStore` (§4.1) and `SqliteStore` (§4.2, `sqlite3`).
- **`graph_hash`**: `blake2s(digest_size=16)` over the canonicalised `graph` only — `status`,
  `source` and the timestamps never enter it, and there is **no `dsl_version`** (§3, `D-04-3`).
- **`publish` is the only write entry point** and runs the fixed steps of §5 in one place shared by
  both stores: validate `tpl_key` / `root_domain` (`UP2-E3002`) → compile the graph (mandatory lint,
  G1) → read the old row and recompile what was read back → no-op when the fingerprint is unchanged →
  write the row → append one audit row → commit. A store write failure is `UP2-E3004`, and the row
  written back is verified against the expected fingerprint (`UP2-E3001`).
- **The audit table is append-only** and holds fingerprints only; `up2 audit` answers "who changed
  which chain to which fingerprint, and when". `UP2-E3003` covers the "chain without an audit row /
  audit row without a chain" inconsistency, detected in the store layer (`up2 doctor --fix` is the
  later slice that consumes it).
- **The publish gates (§6)**: G1 lint mandatory; G2 skippable only with `--skip-tests --note`, and
  the note lands in the audit row (`UP2-E3005` when the note is missing); G3 requires
  `--confirm-overwrite` when the old row is `ready`.
- **`up2 publish` / `up2 get` / `up2 audit`** become the layer's own commands, with the store chosen
  by configuration (`UP2_STORE`, `UP2_HOME`).
- **Tests**: `tests/store/` lands with one case per `UP2-E3xxx`, file-vs-SQLite parity, the no-op
  publish, the inconsistent audit, recompile-on-read, and the `--skip-tests` refusal; `tests/cli/`
  gains the end-to-end cases for the three commands.

## Capabilities

### New Capabilities

- `template-store`: the `Template` / `template_audit` records, the fingerprint, the `TemplateStore`
  protocol with `FileStore` / `SqliteStore`, the `publish` write algorithm and its gates, the
  storage error codes `UP2-E3001`–`UP2-E3005`, and the `up2 publish` / `get` / `audit` commands.

### Modified Capabilities

None. No existing requirement changes: `04` §1 states that L1/L2 need no concept from this document,
and this change keeps it that way (the layer adds no field to a chain and no operator).

## Impact

- Kernel: `core/errors.py` gains `UP2-E3001`–`UP2-E3005` (the codes `04` §5.1 already declared); no
  other `core/` file changes.
- New layer: `src/uniparser2/store/` (`model.py`, `fingerprint.py`, `base.py`, `gates.py`, `file.py`,
  `sqlite.py`, `__init__.py`).
- CLI: `cli/main.py` gains `publish` / `get` / `audit` and a store factory; `uniparser2/__init__.py`
  re-exports the layer's public surface.
- Tests: new `tests/store/` and new `tests/cli/` cases; `up2 conformance --check` stays green because
  the five codes are asserted by cases.
- Docs: `004` §2–§6 synced with what the implementation settled (the audit lookup, the SQLite file
  location, the store-selection configuration, the E3001 / E3003 mechanics, the G2 seam) and `005`
  §4's test-layer table.
- No dependency change (SQLite is `sqlite3`), no DSL change, no chain-format change.
