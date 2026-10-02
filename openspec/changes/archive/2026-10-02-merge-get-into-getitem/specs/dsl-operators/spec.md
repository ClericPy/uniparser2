## ADDED Requirements

### Requirement: `py.getitem` reads a subscript

The `py` operator SHALL provide `getitem` as its only subscript action, and `py.get` SHALL be absent from
the registry. The parameter SHALL be named `at`, SHALL be `ref_or_literal` and required, and the action
SHALL apply Python's subscript semantics — a sequence by index, a mapping by key, a str by character —
with no type coercion.

#### Scenario: a list index

- **WHEN** the value is a list and the action is `["py","getitem",0]`
- **THEN** it SHALL return the first element

#### Scenario: a dict key

- **WHEN** the value is a mapping and the action is `["py","getitem","title"]`
- **THEN** it SHALL return the value stored under that key

#### Scenario: a computed key

- **WHEN** the parameter is a reference, such as `["py","getitem","$globals.key"]`
- **THEN** the reference SHALL be resolved and used as the key

#### Scenario: a key or an index that is not there

- **WHEN** the mapping has no such key, or the index is out of range
- **THEN** it SHALL fail with `UP2-E2018`, and `reason` SHALL begin with the exception class and name the
  key or index, such as `KeyError: 'text' — the dict has no key 'text'`

#### Scenario: a parameter of the wrong type

- **WHEN** the value is a list and the parameter is the string `"0"`
- **THEN** it SHALL fail with `UP2-E2002` and SHALL NOT convert the parameter to an integer

#### Scenario: the catalogue

- **WHEN** `up2 ops --json` is asked for the `py` action list
- **THEN** `getitem` SHALL be present and `get` SHALL NOT
