# Tasks

## 1. The code table and the layer's models

- [x] 1.1 `core/errors.py`: register `UP2-E3001`–`UP2-E3005` with the triggers and fix hints of `04` §5.1
- [x] 1.2 `store/model.py`: `Status` / `Source` / `Graph`, `Template`, `TemplateMeta`, `AuditRow`,
  `PublishResult`, `new_chain_id()`, `utc_now()`, `meta_of()`
- [x] 1.3 `store/fingerprint.py`: `graph_hash` (blake2s-16 over the canonicalised graph alone, `04` §3)

## 2. The protocol and the shared write algorithm

- [x] 2.1 `store/base.py`: the `TemplateStore` protocol exactly as `04` §4 shows, plus the graph
  compiler (`compile_story` for a bundle carrying `steps`, `compile_field` otherwise)
- [x] 2.2 `store/base.py`: the §5 publish algorithm over the private storage seam — validate
  (`UP2-E3002`) → compile (G1) → read + recompile the old row → no-op on an equal fingerprint → write →
  append one audit row → commit → verify the read-back (`UP2-E3001`); a storage failure is `UP2-E3004`
  with the path and the underlying error

## 3. The two implementations

- [x] 3.1 `store/file.py`: `FileStore` — the §4.1 layout, atomic `os.replace`, canonical chain JSON,
  per-key `audit.jsonl`, the single-writer note, `inconsistencies()` (`UP2-E3003`)
- [x] 3.2 `store/sqlite.py`: `SqliteStore` — the §4.2 schema (`UNIQUE(root_domain, tpl_key)`, the two
  indexes, `AUTOINCREMENT`), `PRAGMA journal_mode=WAL`, no foreign keys, one `BEGIN IMMEDIATE`
  transaction per publish, `inconsistencies()`
- [x] 3.3 `store/__init__.py`: the layer's public surface (`TemplateStore`, `FileStore`, `SqliteStore`,
  the models, `graph_hash`, `default_home`, `open_store`, the two JSON projections)

## 4. The gates

- [x] 4.1 `store/gates.py`: G2 (`--skip-tests` without `--note` is `UP2-E3005`) and G3 (a `ready` row
  needs `--confirm-overwrite`), as pure functions returning a diagnostic or a usage message

## 5. The commands

- [x] 5.1 `cli/main.py`: `publish` (gates → store publish → print the `PublishResult`), `get`
  (`--graph` for S7 backup material, compiled before printing), `audit` (key → `chain_id` → rows)
- [x] 5.2 `cli/main.py`: the store factory reading `UP2_HOME` and `UP2_STORE`
- [x] 5.3 `uniparser2/__init__.py`: **deliberately untouched** — the store is its own layer
  (`uniparser2.store`), so importing the top-level package does not drag storage into a kernel-only
  host; `01` §1.2 lists `store/` as a layer of the tree, not as part of the core public API

## 6. Tests

- [x] 6.1 `tests/store/test_model.py`: `new_chain_id` shape, the fingerprint's canonicalisation and its
  independence from `status` / `source` / the timestamps, an equal fingerprint for a JSON file and a
  dictionary, the column set, the two vocabularies
- [x] 6.2 `tests/store/test_store.py`: file-vs-SQLite parity for `publish` / `get` / `list` / `audit`,
  the no-op publish writing no audit row, the in-place update keeping `chain_id` / `create_time` /
  `status`, the rollback row, and the recompile-on-read case
- [x] 6.3 `tests/store/test_store_errors.py`: one case per `UP2-E3xxx` — `UP2-E3001` (read-back
  mismatch), `UP2-E3002` (illegal `tpl_key`, empty `root_domain`), `UP2-E3003` (chain without audit,
  audit without chain), `UP2-E3004` (unwritable home / database path, and a broken write window),
  `UP2-E3005` (`--skip-tests` without `--note`)
- [x] 6.4 `tests/cli/test_cli.py`: `publish` / `get` / `audit` end to end with `tmp_path` as `UP2_HOME`,
  the `--skip-tests --note` trace, the unconfirmed overwrite of a `ready` row, `UP2_STORE=sqlite`
- [x] 6.5 `up2 conformance --check` stays green: 73 declared pairs = 73 covered pairs, and the five new
  codes are asserted by cases (35 implemented codes)

## 7. Docs

- [x] 7.1 `004` §1–§6: sync what the implementation settled (the audit look-up, the SQLite path and
  `UP2_STORE`, the E3001 read-back step and the E3003 findings, the G2 seam, G3's outcome, the `seq`
  scope, `--graph`)
- [x] 7.2 `005` §4: the store row and the CLI row of the test-layer table, and `§4.1`'s measurement line
- [x] 7.3 `001` §1.2 / §4.3 and `007` §3: the `store/` module list as it landed, the storage code
  segment, and the L3 progress row
- [x] 7.4 Both READMEs and `CHANGELOG.md`: the status paragraphs, the error-code count, the project
  layout, the store section and the conformance numbers

## 8. Gates

- [x] 8.1 `uv run ruff format --check` (164 files) / `uv run ruff check` / `uv run mypy` (76 files) /
  `uv run pytest --cov=uniparser2.core --cov-fail-under=95` (699 passed, 3 skipped, 98.23%) /
  `uv run up2 conformance --check` (PASS)
- [x] 8.2 The `change-linter` for every edited `.py` (L3 + S: ruff ×2, complexity, ty, pyrefly, pyright,
  bandit — 全部通过)
- [x] 8.3 The `007` §3 acceptance item for this layer: every concept of `004` deleted from the code
  (the `store/` package gone, the five codes gone, the CLI back to `ops`/`conformance`/`lint`/`trial`,
  `tests/store` gone) → **629 passed, 3 skipped**, then the tree restored and green again at 699
- [x] 8.4 `openspec validate --strict`, then archive with the `openspec-archive-change` skill
