# Spec Delta

## ADDED Requirements

### Requirement: A non-finite float is not a JSON value

The JSON value domain SHALL exclude `inf`, `-inf` and `nan`. A product that carries one — at the top
level or nested in a list or a dict — MUST be refused by the exit packing rule with `UP2-E2003` at the
step that produced it, and a host-registered function or a sandboxed snippet that returns one MUST be
reported with `UP2-E2009`. Chain text MUST NOT carry one: loading it MUST fail with `UP2-E1004`, and
serializing a chain that holds one MUST fail with the same code, because a chain is JSON data.

The rule applies at the boundary only: a computation MAY still answer a non-finite float internally,
because Python's arithmetic does.

#### Scenario: A product is non-finite

- **WHEN** a step's product is `float("inf")`
- **THEN** the run fails with `UP2-E2003` at that step, and the diagnostic names the value

#### Scenario: A non-finite value nested in a product

- **WHEN** a step's product is `{"ratio": float("nan")}`
- **THEN** the run fails with `UP2-E2003` at that step

#### Scenario: A finite float remains a value

- **WHEN** a step's product is `1.5`
- **THEN** the run succeeds and the value is exported unchanged

#### Scenario: Chain text carries a non-JSON constant

- **WHEN** the chain text is `[["const",Infinity]]` and it is loaded
- **THEN** loading fails with `UP2-E1004`, whose fix line says a chain is JSON data

#### Scenario: Serializing a chain that holds one

- **WHEN** `dumps` is called on a stage whose parameter is `float("inf")`
- **THEN** it raises an `Up2Error` with code `UP2-E1004` instead of emitting `Infinity`

#### Scenario: The computation itself still answers it

- **WHEN** `["py", "float", ""]` is evaluated on `"1e999"`
- **THEN** evaluation succeeds and answers `inf`; only the boundary refuses it
