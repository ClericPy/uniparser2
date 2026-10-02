# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
