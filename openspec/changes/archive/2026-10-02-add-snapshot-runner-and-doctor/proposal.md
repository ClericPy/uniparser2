# Add the snapshot runner and `up2 doctor`

## Why

`04` §6 makes G2 ("regression of the snapshots that already exist") a mandatory gate on `publish`,
but the slice that landed the store left the runner out: `publish` regressed an **empty** sample set
and only the `--skip-tests` / `--note` trace contract was enforced. The same gap keeps the `S0–S7`
SOP of `04` §7 from being followable — S4 (`up2 snapshot`) and S5 (`up2 test`) named commands that
did not exist, and S0/S3/S7 named commands that do not exist in the form the draft wrote them
(`up2 lint --ops`, `up2 schemas`, `trial --trace`), while `up2 doctor --fix` of `04` §10 — the
repair for "a chain without an audit row" — is `007` §3's L3 acceptance item 3. This change closes
the gate and makes the SOP an executable document.

## What Changes

- **A snapshot runner** (`cli/samples.py`): a **case** is `<tests-root>/<root_domain>/<tpl_key>/<case>/`
  carrying `input.txt` and `expected.json`. It runs every case of one key through the story executor,
  compares the product with the recorded one **structurally**, and reports a difference as a **JSON
  Pointer difference** (pointer + expected + actual), never as a text diff.
- **G2 becomes real**: `publish` regresses the key's sample set before it writes, and a red set is
  refused with `UP2-E3005` (whose message carries the pointer difference) unless `--skip-tests
  --note` says why. The store's write path is unchanged, so a refusal writes nothing.
- **`up2 snapshot <chain.json> --domain D --key K --case C --accept`** — records one case's product
  as its snapshot. `--accept` is the **only** way a snapshot is written (`04` §7-S4).
- **`up2 test <domain> <tpl_key> [--case C] [--json]`** — runs the stored chain over the key's whole
  sample set once, printing the pointer difference of each failure (`04` §7-S5).
- **`up2 doctor [--fix] [--json]`** — reports the `UP2-E3003` inconsistencies and, with `--fix`,
  writes the audit row a chain is missing. The synthesized row carries actor `doctor` and a note,
  because `04` §2.1 gives an audit row nowhere else to say it was synthesized.
- **A structural comparison in the kernel** (`core/export.py`): `compare_products` answers the
  pointer differences of two products, so `up2 test` and G2 share one comparison and the kernel stays
  IO-free.
- **`04` §6/§7/§8/§10 corrected** wherever the implemented command differs from the text, and
  `007` §3's L3 progress records what landed. `CHANGELOG.md` gains the outstanding `[Unreleased]`
  entries of this session's eight archived changes.
- **The committed example** `samples/local/demo/` (story + `input.txt` + `expected.json`) gives the
  documented layout a real inhabitant and `tests/snapshots/` the case `05` §4 expects.

## Capabilities

### New Capabilities

None. The runner, the two commands and the repair all belong to the capability that already owns the
store, the publish gates and the SOP; a second capability would split one lifecycle across two specs.

### Modified Capabilities

- `template-store`: the publish gate's G2 requirement gains the real regression (a sample case's
  layout, the structural comparison, the two commands that run it, and the refusal that carries the
  pointer difference), and the `UP2-E3003` requirement gains the `--fix` repair the earlier slice
  explicitly deferred.

## Impact

- Kernel: `core/export.py` (`ProductDifference`, `compare_products`, `render_difference`),
  `core/__init__.py` and `uniparser2/__init__.py` re-export `compare_products`; no error code is
  added, and no retired number is reused (`UP2-E3005` covers both G2 branches).
- Layers: new `cli/samples.py` (the IO side: the layout, the run, the snapshot write); `cli/main.py`
  gains the two sample commands and `doctor`, and `publish` gains `--tests-root`; `store/base.py`
  gains `DoctorBackend` and `repair_chain`, and both stores a `find_chain`.
- Data: `samples/local/demo/` (the committed snapshot case); no schema change and no dependency
  change.
- Docs: `04` §4.1/§5.1/§6/§7/§8/§10 and its status header, `005` §3/§4, `007` §3, both READMEs,
  `CHANGELOG.md`.
- Tests: `tests/core/test_export_diff.py`, `tests/cli/test_snapshot.py`,
  `tests/store/test_repair.py`, `tests/snapshots/test_demo_case.py`; conformance stays green
  (73 pairs, 35 codes).
