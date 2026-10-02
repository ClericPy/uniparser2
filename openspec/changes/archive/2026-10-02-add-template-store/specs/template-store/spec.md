# Spec Delta

## Purpose

Bind a finished chain to a business identity and freeze it: one `Template` row per
`(root_domain, tpl_key)`, an append-only `template_audit` trace, a `TemplateStore` protocol with a
file and a SQLite implementation, and a `publish` that refuses a chain which does not lint — design
note `04` §1–§6, the first slice of the L3 binding layer.

## ADDED Requirements

### Requirement: One Template row per chain, with no `dsl_version`

The store SHALL keep exactly one `Template` row per `(root_domain, tpl_key)`: `chain_id` (primary
key), `root_domain`, `tpl_key`, `status`, `source`, `graph`, `create_time` and `update_time`. There
SHALL be no version rows, no pinning and no `dsl_version` column: the dialect of a stored chain is
checked by the compiler, not by a stored number (`04` §3, `D-04-3`).

`chain_id` SHALL be produced by one pure function, `new_chain_id()`, whose current answer is
`uuid4().hex` (32 characters, no dashes); a later switch to ULID SHALL touch that function alone.
`create_time` and `update_time` SHALL be ISO 8601 in UTC with the `+00:00` offset. `status` SHALL be
one of `draft` / `ready` / `disabled` and SHALL default to `draft`; `source` SHALL be one of `human` /
`agent` / `import` and SHALL default to `agent`.

`(root_domain, tpl_key)` SHALL be unique. `publish` SHALL write in place: an existing row keeps its
`chain_id`, its `create_time` and its `status`, and only `graph`, `source` and `update_time` change.

#### Scenario: A new chain gets an identity

- **WHEN** a graph is published under a `(root_domain, tpl_key)` that does not exist yet
- **THEN** the store SHALL create a row whose `chain_id` is `uuid4().hex`-shaped (32 lowercase hex
  characters, no dashes), whose `status` is `draft`, whose `create_time` equals its `update_time`, and
  whose `update_time` carries the `+00:00` offset

#### Scenario: Re-publishing updates in place

- **WHEN** a second, different graph is published under the same `(root_domain, tpl_key)`
- **THEN** the row SHALL keep its `chain_id` and its `create_time`, SHALL carry the new `graph`, and its
  `update_time` SHALL be refreshed

#### Scenario: The chain data is stored as data

- **WHEN** a `Template` is read back through `get`
- **THEN** its `graph` SHALL be the chain data of the stored JSON (no compiled graph, no engine object,
  no attribute hung on a `str` subclass)

### Requirement: The audit table is append-only and holds fingerprints

The store SHALL keep an append-only `template_audit` record: `seq` (the audit order within one
`chain_id`), `chain_id`, `at`, `actor`, `source`, `old_hash`, `new_hash` and `note`. An audit row SHALL
never be modified or deleted, and SHALL hold **only fingerprints** — never a copy of the `graph`.
`old_hash` SHALL be `None` on the first write of a `chain_id`.

`actor` SHALL be a free-form string passed in by the caller, defaulting to `unknown`; the kernel
SHALL NOT infer it from the process or the environment (`04` §2.1). `note` SHALL be optional, and
SHALL be recorded on the row when it is given.

`audit(chain_id)` SHALL return the rows in ascending `seq` order; a `chain_id` with no audit row
SHALL answer an empty list.

#### Scenario: A first publish leaves one audit row

- **WHEN** a graph is published under a new `(root_domain, tpl_key)`
- **THEN** `audit` SHALL answer exactly one row with `old_hash is None`, `new_hash` equal to the
  graph's fingerprint, and the `actor` / `source` / `note` the caller passed

#### Scenario: The note is recorded

- **WHEN** `publish` is called with `note="roll back to <hash>"`
- **THEN** that text SHALL be the `note` of the appended audit row

#### Scenario: A rollback leaves a row

- **WHEN** an older graph is published again over a newer one
- **THEN** the audit SHALL gain a row whose `old_hash` is the fingerprint being replaced and whose
  `new_hash` is the older graph's fingerprint, and no earlier row SHALL change

### Requirement: The fingerprint covers the graph and nothing else

The store SHALL compute a graph fingerprint with `blake2s` at `digest_size=16` (32 hex characters)
over the **canonicalised graph only**:

- canonicalisation is `json.dumps(graph, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`;
- `status`, `source`, `create_time`, `update_time` and the `actor` SHALL NOT enter the fingerprint;
- the same graph SHALL yield the same fingerprint whether it arrives as a JSON file or as a dictionary.

The fingerprint SHALL be the no-op decision of `publish`: re-publishing an unchanged graph SHALL write
no template row and **no audit row**.

#### Scenario: Key order and whitespace do not matter

- **WHEN** two graphs differ only in the order of their keys, or one is loaded from JSON text and the
  other built as a dictionary
- **THEN** their fingerprints SHALL be equal

#### Scenario: Metadata does not enter the fingerprint

- **WHEN** a chain's `status` or `source` changes while its `graph` does not
- **THEN** the fingerprint SHALL stay the same, and no audit row SHALL be written

#### Scenario: The same graph twice is a no-op

- **WHEN** an unchanged graph is published a second time
- **THEN** `PublishResult.changed` SHALL be `False`, `audit_seq` SHALL be `None`, and the audit SHALL
  still hold exactly the rows it held before

### Requirement: `TemplateStore` is the storage protocol

The layer SHALL expose a `TemplateStore` protocol with exactly these four methods:

```python
class TemplateStore(Protocol):
    def get(self, root_domain: str, tpl_key: str) -> Template | None: ...
    def list(
        self, *, root_domain: str | None = None, status: Status | None = None
    ) -> list[TemplateMeta]: ...
    def publish(
        self,
        graph: Graph,
        *,
        root_domain: str,
        tpl_key: str,
        actor: str,
        source: Source,
        note: str | None = None,
    ) -> PublishResult: ...
    def audit(self, chain_id: str) -> list[AuditRow]: ...
```

It SHALL be a `Protocol` rather than a base class, so a host can inject its own implementation
(MySQL, for instance) and the kernel imports no concrete store. `get` SHALL answer the complete
`Template` including `graph`, or `None`, and SHALL **not** compile. `list` SHALL answer metadata
without `graph`, filtered by `root_domain` and `status` when they are given, and SHALL be sorted
deterministically. `publish` SHALL be the only write entry point and SHALL answer a `PublishResult`
(`chain_id`, `old_hash`, `new_hash`, `changed`, `audit_seq`).

#### Scenario: A missing chain is not an error

- **WHEN** `get` is asked for a `(root_domain, tpl_key)` that was never published
- **THEN** it SHALL answer `None`, and `list` SHALL not contain it

#### Scenario: Listings carry no graph

- **WHEN** `list` answers a row
- **THEN** the item SHALL carry the identity, `status`, `source` and the two timestamps, and SHALL
  carry no `graph`

#### Scenario: Filtering

- **WHEN** `list` is called with `root_domain` and/or `status`
- **THEN** only the rows matching both filters SHALL be returned

### Requirement: `FileStore` keeps one file per chain

`FileStore` SHALL lay out `$UP2_HOME` as `04` §4.1 shows: `chains/<root_domain>/<tpl_key>.json` holds
the complete `Template`, `audit/<root_domain>/<tpl_key>.jsonl` holds one audit row per line, and
`samples/<root_domain>/<tpl_key>/<case>/` is left for the sample runner of the later slice.

A chain file SHALL be written to a temporary file in the same directory and then moved into place with
`os.replace`, so a reader never sees a half-written chain. The chain JSON SHALL be canonical (sorted
keys, `ensure_ascii=False`, a trailing newline) so that a version-control diff stays readable.
`FileStore` SHALL assume a **single writer**; the assumption SHALL be stated in the code
documentation, and a write that fails SHALL be reported as `UP2-E3004`.

#### Scenario: Where a row lands

- **WHEN** a graph is published under `("ah.gov.cn", "政府文件列表")`
- **THEN** `$UP2_HOME/chains/ah.gov.cn/政府文件列表.json` SHALL exist, and
  `$UP2_HOME/audit/ah.gov.cn/政府文件列表.jsonl` SHALL hold one JSON object per line

#### Scenario: A crashed write is not a half-written chain

- **WHEN** a chain file is written
- **THEN** the reader SHALL see either the previous complete file or the new complete file, because the
  replacement is `os.replace` inside the chain's own directory

#### Scenario: A write failure is coded

- **WHEN** the chain directory cannot be created or written
- **THEN** `publish` SHALL fail with `UP2-E3004`, naming the path and the underlying error, and
  **no** audit row SHALL be appended

### Requirement: `SqliteStore` keeps the two tables of `04` §4.2

`SqliteStore` SHALL create the `template` and `template_audit` tables with the columns, constraints and
indexes of `04` §4.2 (`UNIQUE(root_domain, tpl_key)`, `idx_template_domain`, `idx_template_status`,
`idx_audit_chain`, `seq INTEGER PRIMARY KEY AUTOINCREMENT`) and SHALL set
`PRAGMA journal_mode=WAL`. It SHALL declare **no foreign key**: an audit row must be able to outlive
the template row it points at.

A write SHALL be one `BEGIN IMMEDIATE` … `COMMIT` transaction, so "a chain without an audit row" and
"an audit row without a chain" cannot both appear; a SQLite failure SHALL be reported as `UP2-E3004`
with the underlying error.

#### Scenario: The schema is the designed one

- **WHEN** a `SqliteStore` is opened on an empty file
- **THEN** the `template` and `template_audit` tables SHALL exist with the designed columns, the unique
  constraint on `(root_domain, tpl_key)` SHALL hold, and the journal mode SHALL be `wal`

#### Scenario: Chain and audit land together

- **WHEN** a publish commits
- **THEN** both the template row and its audit row SHALL be visible, and the audit row SHALL be
  readable by `chain_id`

#### Scenario: A look-up uses the index

- **WHEN** `get` answers a row by `(root_domain, tpl_key)`
- **THEN** it SHALL use the unique index rather than a scan of all rows

### Requirement: `publish` runs the fixed write algorithm

Both stores SHALL run the same steps in the same order (`04` §5):

1. `tpl_key` SHALL match `^[\w\u4e00-\u9fff][\w\u4e00-\u9fff.-]{0,63}$` and `root_domain` SHALL be
   non-empty, otherwise `UP2-E3002` — whose message SHALL carry the character-set rule and the actual
   value — and nothing SHALL be written.
2. The graph SHALL be compiled; a graph that does not lint SHALL be refused and SHALL leave no residue,
   so a bad chain cannot enter the store.
3. The old row SHALL be read (`changed=True`, `old_hash=None` when absent), and its graph SHALL be
   recompiled before it is trusted. When the new fingerprint equals the old one, `publish` SHALL return
   immediately and write nothing at all (`changed=False`).
4. The template row SHALL be written (INSERT or in-place UPDATE, `update_time` refreshed).
5. Exactly one audit row SHALL be appended.
6. The write SHALL be committed: SQLite inside one transaction; the file store lands `chains` first and
   appends `audit` afterwards, so a crash between the two leaves "a chain without an audit row", which
   the consistency check reports.

After the write, the stored row SHALL be read back and its fingerprint compared with the expected one;
a mismatch SHALL be `UP2-E3001` ("the graph written under the same `(root_domain, tpl_key)` does not
match the expected fingerprint"), whose fix hint names `up2 get` and a concurrent writer.

#### Scenario: A bad chain cannot get in

- **WHEN** a graph with an unknown operator is published
- **THEN** `publish` SHALL fail with the compiler's code (`UP2-E1xxx`), and the store SHALL be
  byte-for-byte what it was before

#### Scenario: The stored graph is recompiled

- **WHEN** the row read back inside `publish` holds a graph that no longer compiles
- **THEN** `publish` SHALL fail with that graph's compiler diagnostic instead of overwriting it

#### Scenario: The graph written back is verified

- **WHEN** the store hands back a graph whose fingerprint differs from the one that was written
- **THEN** `publish` SHALL fail with `UP2-E3001`

#### Scenario: An illegal key is refused before anything is written

- **WHEN** `tpl_key` is `"a:b"` or `root_domain` is empty
- **THEN** `publish` SHALL fail with `UP2-E3002` carrying the character-set rule and the actual value

### Requirement: An inconsistent audit is reported as `UP2-E3003`

The store layer SHALL be able to report the two inconsistencies of `04` §5.1: a chain row without an
audit row, and an audit row whose `chain_id` has no chain row. Each finding SHALL be a diagnostic with
the code `UP2-E3003`, naming the `chain_id`, and both stores SHALL report the same finding for the same
state. Repairing a finding (`up2 doctor --fix`) is a later slice and SHALL NOT be part of this one.

#### Scenario: A chain without an audit row

- **WHEN** a file store holds a chain file whose audit file is missing
- **THEN** the consistency check SHALL report one `UP2-E3003` naming that `chain_id`

#### Scenario: An audit row without a chain

- **WHEN** a SQLite database holds a `template_audit` row whose `chain_id` is not in `template`
- **THEN** the consistency check SHALL report one `UP2-E3003` naming that `chain_id`

#### Scenario: A consistent store reports nothing

- **WHEN** every chain row has at least one audit row and every audit row has a chain
- **THEN** the consistency check SHALL answer an empty list

### Requirement: The publish gates

`publish` SHALL be a quality gate, not a file write (`04` §6). G1 SHALL be enforced by the store's
`publish` itself, because it compiles the graph before the write, so no flag can store a chain that
does not lint. G2 and G3 SHALL be enforced by the layer's publish gate, which the CLI runs before it
calls the store:

- **G1** lint SHALL be mandatory and SHALL NOT be skippable.
- **G2** the regression of the snapshots that already exist SHALL be mandatory unless `--skip-tests` is
  given, and `--skip-tests` SHALL be accepted **only together with `--note`**; the note SHALL be
  recorded in the audit row of that publish. `--skip-tests` without `--note` SHALL be refused with
  `UP2-E3005`, and nothing SHALL be written.
- **G3** when the old row's `status` is `ready`, the write SHALL require `--confirm-overwrite`; without
  it the command SHALL refuse and write nothing.

#### Scenario: Skipping the tests must leave a trace

- **WHEN** `publish` is asked to skip the regression and gives no note
- **THEN** it SHALL fail with `UP2-E3005`, and neither a template row nor an audit row SHALL be written

#### Scenario: The bypass is recorded

- **WHEN** the regression is skipped and `--note "samples not ready yet"` is given
- **THEN** the publish SHALL succeed and that text SHALL be the `note` of the appended audit row

#### Scenario: Overwriting a ready chain is confirmed

- **WHEN** the old row's `status` is `ready` and `--confirm-overwrite` is not given
- **THEN** the command SHALL refuse, name the overwrite it would perform, and write nothing

### Requirement: Everything read back from a store is recompiled, never trusted

A stored `graph` SHALL be data, never a compilation product: the store SHALL hold no engine state, SHALL
write no compiled object, and SHALL never deserialize a trusted compile product (`01` §8; `04` §1, §4).
Every read-back path inside the layer SHALL compile the graph again — `publish` recompiles the row it
read before it trusts it, and `up2 get` compiles the graph before printing it, so a hand-edited or
corrupted stored chain is reported by the compiler instead of being served as if it were valid.

#### Scenario: A corrupted stored chain is caught on read

- **WHEN** a chain file is edited by hand to hold an uncompilable graph, and `up2 get` reads it
- **THEN** the command SHALL report the compiler's diagnostic, and SHALL not print the graph as a
  valid chain

#### Scenario: The store caches no compilation

- **WHEN** the same chain is `get` twice
- **THEN** each answer SHALL be freshly parsed JSON data, and no compiled object SHALL be reachable
  from it

### Requirement: The store layer's commands

`up2` SHALL gain three commands belonging to this layer (`04` §4, §7-S6/S7):

- `up2 publish <chain.json> --domain D --key K [--actor A] [--source S] [--note N] [--skip-tests]
  [--confirm-overwrite] [--json]` — calls the store's `publish` and prints the `PublishResult`
  (`chain_id`, `old_hash`, `new_hash`, `changed`, `audit_seq`). `--actor` SHALL default to `unknown`
  and `--source` to `agent`.
- `up2 get D K [--json] [--graph]` — prints the stored `Template` with its fingerprint; `--graph`
  prints only the graph, the backup material of S7.
- `up2 audit D K [--json]` — resolves the key to its `chain_id` and prints the fingerprint chain in
  `seq` order (`at` / `actor` / `source` / `old_hash → new_hash` / `note`).

All three SHALL take the store from configuration: `UP2_HOME` (default `~/.uniparser2`) for the
location, and `UP2_STORE` (`file` or `sqlite`, default `file`) for the implementation. A `publish` that fails a gate or a store step SHALL exit non-zero and print the
diagnostic; asking for a chain that does not exist SHALL exit non-zero with a message.

#### Scenario: Publish, then read back

- **WHEN** `up2 publish chain.json --domain ah.gov.cn --key 政府文件列表` succeeds and `up2 get
  ah.gov.cn 政府文件列表 --json` follows
- **THEN** the printed fingerprint SHALL equal the `new_hash` the publish reported, and `changed` SHALL
  have been `True`

#### Scenario: The audit chain answers who and when

- **WHEN** `up2 audit ah.gov.cn 政府文件列表` runs after two different graphs were published
- **THEN** it SHALL print two rows in `seq` order, the second one's `old_hash` being the first one's
  `new_hash`

#### Scenario: The store is chosen by configuration

- **WHEN** `UP2_STORE` is `sqlite`
- **THEN** the three commands SHALL read and write the SQLite store under `UP2_HOME`, and a chain
  published by the file store SHALL NOT be visible
