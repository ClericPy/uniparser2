# template-store Specification

## Purpose
Bind a finished chain to a business identity and freeze it: one `Template` row per
`(root_domain, tpl_key)`, an append-only `template_audit` trace, a `TemplateStore` protocol with a
file and a SQLite implementation, and a `publish` that refuses a chain which does not lint — design
note `04` §1–§6, the first slice of the L3 binding layer.

## Requirements

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
state. A diagnostic SHALL carry the `chain_id` it is about as its own field, so the command that reads
the findings does not have to parse the message to learn which chain is meant.

`up2 doctor` SHALL report the findings (`04` §10), exiting non-zero while any remains, and
`up2 doctor --fix` SHALL repair "a chain without an audit row" by writing the missing audit row. The
repair SHALL be one append, through the store's own write scope, with `old_hash` `None`, `new_hash`
equal to the fingerprint of the **stored** graph, the `source` of the chain row, and an `actor` and
`note` that identify the row as synthesized — an audit row has nowhere else to say it was written by a
repair. "An audit row without a chain" SHALL remain a finding: there is no chain to append beside.

#### Scenario: A chain without an audit row

- **WHEN** a file store holds a chain file whose audit file is missing
- **THEN** the consistency check SHALL report one `UP2-E3003` naming that `chain_id`

#### Scenario: An audit row without a chain

- **WHEN** a SQLite database holds a `template_audit` row whose `chain_id` is not in `template`
- **THEN** the consistency check SHALL report one `UP2-E3003` naming that `chain_id`

#### Scenario: A consistent store reports nothing

- **WHEN** every chain row has at least one audit row and every audit row has a chain
- **THEN** the consistency check SHALL answer an empty list

#### Scenario: The fix writes the missing audit row

- **WHEN** `up2 doctor --fix` runs against a store holding a chain that has no audit row
- **THEN** it SHALL append exactly one audit row for that chain whose `new_hash` is the fingerprint of
  the stored graph, it SHALL report the row it wrote, and a second run of `up2 doctor` SHALL report no
  finding

#### Scenario: The fix leaves an orphan audit row alone

- **WHEN** the only finding is an audit row whose chain is gone
- **THEN** `up2 doctor --fix` SHALL write nothing and SHALL still exit non-zero

### Requirement: The publish gates

`publish` SHALL be a quality gate, not a file write (`04` §6). G1 SHALL be enforced by the store's
`publish` itself, because it compiles the graph before the write, so no flag can store a chain that
does not lint. G2 and G3 SHALL be enforced by the layer's publish gate, which the CLI runs before it
calls the store:

- **G1** lint SHALL be mandatory and SHALL NOT be skippable.
- **G2** the regression of the snapshots that already exist SHALL be mandatory unless `--skip-tests` is
  given, and `--skip-tests` SHALL be accepted **only together with `--note`**; the note SHALL be
  recorded in the audit row of that publish. `--skip-tests` without `--note` SHALL be refused with
  `UP2-E3005`, and nothing SHALL be written. The regression SHALL **run** the cases recorded for this
  `(root_domain, tpl_key)`: when one of them no longer matches, the publish SHALL be refused with
  `UP2-E3005` carrying the JSON Pointer difference, and nothing SHALL be written. A key with no
  recorded case SHALL be green, so a chain may be stored before its samples exist; a case that carries
  an input but no snapshot SHALL be red, so a chain cannot quietly stop being regressed.
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

#### Scenario: A red sample refuses the publish

- **WHEN** a case recorded for the key no longer matches what the chain produces, and `publish` is run
  without `--skip-tests`
- **THEN** it SHALL fail with `UP2-E3005` whose message names the case and the JSON Pointer of the
  differing value, and the store SHALL be unchanged (no new fingerprint, no new audit row)

#### Scenario: A key with no samples still publishes

- **WHEN** no case is recorded for the key and `publish` is run without `--skip-tests`
- **THEN** the publish SHALL succeed

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

### Requirement: A sample case is a case directory with an input and a snapshot

A **sample case** SHALL be the directory `<samples-root>/<root_domain>/<tpl_key>/<case>/`, carrying
`input.txt` (the run's input) and `expected.json` (the recorded product). The samples root SHALL be
given by `--tests-root` and SHALL default to `samples`, so the repository's own directory is the
committed contract and `$UP2_HOME/samples` the place for temporary cases (`05` §3). A case name SHALL
be one path component: the commands SHALL refuse a name that is not.

The recorded product SHALL be the run's **exit product**, frozen as JSON. Writing one SHALL require
the explicit confirmation of the `--accept` flag, because a snapshot is a behavioral contract and
"the chain ran once" is not evidence that it extracted the right content (`04` §7-S4).

#### Scenario: The layout locates a case

- **WHEN** `--tests-root R`, `--domain D`, `--key K` and `--case C` are given
- **THEN** the case SHALL be read from and written to `R/D/K/C/input.txt` and `R/D/K/C/expected.json`

#### Scenario: Writing a snapshot needs the confirmation

- **WHEN** `up2 snapshot` runs without `--accept`
- **THEN** it SHALL refuse, and no `expected.json` SHALL be created or changed

#### Scenario: A case name cannot escape the samples root

- **WHEN** `--case ../escape` is given
- **THEN** the command SHALL refuse and SHALL write nothing outside the samples root

### Requirement: The regression compares products structurally

Two products SHALL be compared as **values**, not as text: a mapping SHALL be compared key by key, a
list position by position, and a scalar by its exact type and value. A difference SHALL be reported as
the **JSON Pointer** of the value that differs, together with what was expected and what the run
produced, so a failure is readable without a text diff (`04` §7-S5, `05` §4.2). A key the expected
product does not carry and a list tail on either side SHALL each be reported at their own pointer.

#### Scenario: A changed value names its pointer

- **WHEN** the expected product is `{"list": [{"title": "b"}]}` and the run produced `"B"` at that
  title
- **THEN** the difference SHALL name `/list/0/title` with both values

#### Scenario: A type change is named

- **WHEN** the expected value is a string and the run produced a number at the same pointer
- **THEN** the difference SHALL name both types

#### Scenario: A missing and an extra key are both reported

- **WHEN** the expected mapping carries a key the product does not, and the product carries one the
  expected mapping does not
- **THEN** both SHALL be reported, the first as a value that is absent and the second as one that was
  not expected

### Requirement: `up2 snapshot` and `up2 test` run the sample regression

`up2` SHALL gain the two SOP commands of `04` §7-S4/S5:

- `up2 snapshot <chain.json> --domain D --key K --case C --accept [--tests-root R] [--json]` — runs the
  given chain over that case's input and writes its product as that case's `expected.json`. A run that
  cannot produce a product (a chain that does not compile, a step that fails, or a story that suspends
  on an effect a snapshot runner cannot answer) SHALL exit non-zero and write nothing.
- `up2 test <domain> <tpl_key> [--case C] [--tests-root R] [--json]` — reads the chain stored under
  that key, runs it over **every** case recorded for the key, and prints one JSON Pointer difference
  per mismatch. It SHALL exit non-zero when any case mismatches, and `--json` SHALL report each failure
  as data (the case, the pointer, the expected and the actual value).

Both commands SHALL run a story bundle through the story executor and a field chain through the field
evaluator, so a case is regressed exactly the way the chain is executed.

#### Scenario: A snapshot is recorded and then matches

- **WHEN** `up2 snapshot … --accept` records a case's product, and `up2 test D K` follows
- **THEN** the test SHALL pass and report no difference

#### Scenario: A red case prints the pointer and exits non-zero

- **WHEN** a recorded case no longer matches the chain's product
- **THEN** `up2 test D K` SHALL exit non-zero and its output SHALL name the case and the JSON Pointer
  of the differing value

#### Scenario: One case can be run alone

- **WHEN** `up2 test D K --case C` is given and another case of the key is red
- **THEN** only `C` SHALL be regressed

#### Scenario: A story that suspends is reported, not guessed at

- **WHEN** a case's chain is a story whose next effect is a request
- **THEN** the runner SHALL report that it has no host to answer it, and SHALL write no snapshot

#### Scenario: A chain that does not compile is reported by the compiler

- **WHEN** the stored chain of the key no longer compiles
- **THEN** `up2 test` SHALL report the compiler's diagnostic at that chain and SHALL not run any case

### Requirement: The snapshot runner answers a suspension from the request cache

The snapshot runner (`up2 snapshot`, `up2 test`) SHALL answer a story's `Request` and `RequestBatch`
suspensions from the **request cache** (`host-runtime`), so a chain that fetches can be frozen and
regressed **offline**. The runner SHALL NOT reach the network: a request with no cached answer is a
**miss**, and a miss SHALL be reported as a plain error naming the request, not guessed at and not
fetched.

A `call` suspension SHALL still be reported as needing a host: the cache holds network answers, not
the result of a host function.

#### Scenario: A suspended story runs from the cache

- **WHEN** the cache holds the answer for the request the story makes, and `up2 snapshot` runs the
  story
- **THEN** the run SHALL continue with the cached answer and reach its exit product

#### Scenario: A missing answer is reported

- **WHEN** the cache holds no answer for the request the story makes
- **THEN** the command SHALL report that the request is not cached, and SHALL write no snapshot

#### Scenario: A call suspension still needs a host

- **WHEN** the story declares a `call` step
- **THEN** the command SHALL report that a snapshot runner has no host to answer it
