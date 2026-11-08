# Spec Delta

## ADDED Requirements

### Requirement: A stored graph is strict JSON

`publish` SHALL take the graph's fingerprint over strict JSON text (`allow_nan=False`). A graph that
contains a non-finite float or a value JSON cannot express MUST fail with `UP2-E1004` **before** the
`Template` row or its audit line is written, in every store implementation. Reading a stored chain
file or audit line that is not valid JSON MUST fail with `UP2-E1004` naming the file, rather than
surfacing a decoder exception.

#### Scenario: Publishing a non-finite graph writes nothing

- **WHEN** a graph whose chain carries `float("inf")` is published to a `FileStore`
- **THEN** the publish raises `UP2-E1004` and no chain file is written

#### Scenario: A finite graph is unaffected

- **WHEN** the same shape with `1.5` instead of `inf` is published
- **THEN** the publish succeeds and the stored text is valid JSON

#### Scenario: A corrupt chain file is a coded failure

- **WHEN** a chain file on disk contains `{not json` and it is read through `get`
- **THEN** the read raises `UP2-E1004` and its message names the file

### Requirement: A sample snapshot is strict JSON

The sample runner SHALL read and write `expected.json` as strict JSON. A snapshot that contains
`Infinity`, `-Infinity` or `NaN` MUST be reported as an error, not read as a value; a product that
cannot be written as JSON MUST be reported as an error string instead of raising out of
`record_expected`.

#### Scenario: A snapshot carrying a non-JSON constant

- **WHEN** `expected.json` holds `Infinity` and the case is read
- **THEN** reading answers an error naming the file, not the value `inf`

#### Scenario: Recording a product JSON cannot express

- **WHEN** `record_expected` is called with a non-finite product
- **THEN** it answers an error string and writes no snapshot

## MODIFIED Requirements

### Requirement: The fingerprint covers the graph and nothing else

The store SHALL compute a graph fingerprint with `blake2s` at `digest_size=16` (32 hex characters)
over the **canonicalised graph only**:

- canonicalisation is `json.dumps(graph, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
  allow_nan=False)`;
- `status`, `source`, `create_time`, `update_time` and the `actor` SHALL NOT enter the fingerprint;
- the same graph SHALL yield the same fingerprint whether it arrives as a JSON file or as a dictionary.

The fingerprint SHALL be the no-op decision of `publish`: re-publishing an unchanged graph SHALL write
no template row and **no audit row**. A graph that strict JSON cannot express MUST be refused with
`UP2-E1004` when the fingerprint is taken, which is before the store writes anything.

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

#### Scenario: A graph JSON cannot express

- **WHEN** the graph carries a non-finite float and its fingerprint is taken
- **THEN** it raises `UP2-E1004` and nothing is written
