# Tasks

## 1. The structural comparison (kernel)

- [x] 1.1 `core/export.py`: `ProductDifference` + `compare_products` + `render_difference` (mapping by
      key, list by position, scalar by exact type; the pointer of every difference)
- [x] 1.2 Re-export from `core/__init__.py` and `uniparser2/__init__.py`
- [x] 1.3 `tests/core/test_export_diff.py`: identity, a changed value's pointer, a type change, a
      missing and an extra key, both list tails, a container type mismatch, a caller-supplied pointer

## 2. The runner (CLI, the IO side)

- [x] 2.1 `cli/samples.py`: the case layout (`input.txt` / `expected.json`), `find_cases`,
      `read_input` / `read_expected` / `record_expected`, `check_case_name`
- [x] 2.2 `run_graph`: a story bundle through the story executor, a field chain through the field
      evaluator, and a suspension reported as a plain error (`03` §4.1)
- [x] 2.3 `failure_line` / `regression_message`: one failure as the JSON Pointer difference

## 3. The commands

- [x] 3.1 `up2 snapshot <chain.json> --domain D --key K --case C --accept [--tests-root R] [--json]`;
      without `--accept` it refuses and writes nothing
- [x] 3.2 `up2 test D K [--case C] [--tests-root R] [--json]`: compile the stored row once, then
      regress every case and exit non-zero on the first difference
- [x] 3.3 `publish` runs G2 over the key's sample set before it calls the store, and refuses a red set
      with `UP2-E3005` carrying the pointer difference (both stores; nothing is written)
- [x] 3.4 `up2 doctor [--fix] [--json]`: report the `UP2-E3003` findings, repair the missing audit row

## 4. The repair (store)

- [x] 4.1 `store/base.py`: `DoctorBackend` + `repair_chain` (one append through the store's write
      scope, `old_hash` `None`, `new_hash` the stored graph's fingerprint)
- [x] 4.2 A `chain_id` field on `Diagnostic`, so a finding names its chain without parsing its message
- [x] 4.3 `find_chain` on `FileStore` and on `SqliteStore`
- [x] 4.4 `tests/store/test_repair.py`: parity of the repair, a no-op for an unknown chain, the row it
      numbers

## 5. CLI and snapshot cases

- [x] 5.1 `tests/cli/test_snapshot.py`: both runner paths, `--accept`, a case name that is a path, a
      suspending story, a green/red publish on both stores, `--skip-tests --note`, `up2 test` (all
      cases, one case, text and JSON), `up2 doctor` on both stores
- [x] 5.2 `samples/local/demo/`: the committed story + `input.txt` + `expected.json`
- [x] 5.3 `tests/snapshots/test_demo_case.py`: the committed case compared structurally

## 6. Docs and metadata

- [x] 6.1 `04`: the status header, §4.1 (`samples/`), §5.1 (`UP2-E3003`/`UP2-E3005`), §6 (G2), §7-S0/S3/
      S4/S5/S7 and §7.1, §8 (`--trace`), §10 (`doctor --fix`) — corrected wherever the implemented
      command differs from the text
- [x] 6.2 `005` §4: the snapshot and CLI rows
- [x] 6.3 `007` §3: the L3 deliverable and progress rows
- [x] 6.4 Both READMEs: the status paragraph, the SOP command block, the layout
- [x] 6.5 `CHANGELOG.md`: the outstanding `[Unreleased]` entries of this session's eight archived
      changes, and the version bump they carry
- [x] 6.6 The change is archived with `openspec-archive-change` once every gate is green

## 7. Gates

- [x] 7.1 `uv run ruff format --check` · `uv run ruff check` · `uv run mypy`
- [x] 7.2 `uv run pytest --cov=uniparser2.core --cov-fail-under=95`
- [x] 7.3 `uv run up2 conformance --check` (no new pair, no new code)
- [x] 7.4 The `change-linter` on the edited `.py` files (L3 + `--security`)
- [x] 7.5 `openspec validate --strict`
