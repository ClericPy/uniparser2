# Spec Delta

## MODIFIED Requirements

### Requirement: A reference path may walk an object

Reference resolution SHALL read a mapping by key, a sequence by index and an object with `getattr`, so a
dotted path works on both a dictionary and an object. An attribute that is **callable** SHALL be refused
with `UP2-E2002`, using the same message shape and the same fix hint `py.getattr` uses: a method is not a
value, and it could not leave the run (`UP2-E2003`) in any case.

The reserved roots SHALL be `globals` (read-only for every step), `locals` (this step's own scope) and
`in` (this step's own input). Every other root SHALL name a step of the story, and a reference that names
no such root SHALL fail with `UP2-E1006`, listing the roots that are accepted. `$fields` SHALL NOT be a
root: it was a second name for `locals` and is retired, so a stage that writes it fails at compile time
like any other unknown root.

#### Scenario: a dotted path into an object

- **WHEN** a stage writes `$resp.headers` and `$resp` is a response object
- **THEN** the reference SHALL resolve through `getattr`, and a missing attribute SHALL fail naming the
  class, exactly as `getattr` does

#### Scenario: an attribute that is a method

- **WHEN** a stage writes `$resp.json` and `json` is a method of `$resp`
- **THEN** the reference SHALL fail with `UP2-E2002`, and its `fix` SHALL be the fix hint `py.getattr`
  carries (naming `["css","text",""]` or a `udf`)

#### Scenario: a header that is not a dotted path

- **WHEN** a stage needs `Content-Type`, which contains a hyphen and is therefore not a dotted path
- **THEN** it SHALL be read from the headers mapping with `["py","getitem","content-type"]`

#### Scenario: the retired root

- **WHEN** a stage writes `$fields.title`
- **THEN** the reference SHALL fail with `UP2-E1006`, an unknown reference root, and the accepted roots
  SHALL NOT list `fields`
