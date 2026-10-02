# Spec Delta

## MODIFIED Requirements

### Requirement: A story bundle declares ordered steps and a named exit

A story bundle SHALL be a JSON object carrying `steps` (a non-empty array, whose order is execution
order) and `exit` (the name of the step whose products form the run's output). It MAY carry `globals`
(a mapping of chain-level read-only constants). It SHALL NOT carry a `chains` table: a parse rule is a
step.

A step SHALL be a JSON object with `name`, an optional `type` (the product's type name), exactly one of
`parse` (an array, one field chain, or an object, a field map) and `call` (a host function name), plus
`with` only on a `call`. A field map SHALL be evaluated once, over the step's input, with `_`-prefixed
fields staying in that step's locals. A written `type` SHALL be resolved against the type registry at the
step boundary: a built-in name or a host registration is built from the product, an unregistered name is
`UP2-E1011`, and a constructor that refuses the product is `UP2-E2019`, both at that step.

#### Scenario: A bundle with one parse step

- **WHEN** the bundle is `{"steps": [{"name": "records", "parse": {"url": [["py","id",""]]},
  "type": "Record"}], "exit": "records"}` and the run's input is `{"url": "u"}`
- **THEN** the run SHALL finish with the output `[{"url": "u"}]`

#### Scenario: A step declares both parse and call

- **WHEN** a step carries `parse` and `call`
- **THEN** compilation SHALL fail with `UP2-E1005`, naming the step

#### Scenario: A bundle has no exit

- **WHEN** the bundle carries `steps` but no `exit`
- **THEN** compilation SHALL fail with `UP2-E1005`, because the exit is declared, never derived

#### Scenario: A bundle carries a chains table

- **WHEN** a bundle carries `chains` beside `steps`
- **THEN** compilation SHALL fail with `UP2-E1005`: a parse rule is a step, and the bundle has no
  second namespace for one

#### Scenario: A declared type is unknown

- **WHEN** a step declares a `type` that is neither a built-in name nor registered
- **THEN** the run SHALL fail with `UP2-E1011` at that step, because the registry is host state and the
  bundle compiles without a host
