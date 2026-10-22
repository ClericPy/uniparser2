# Spec Delta

## ADDED Requirements

### Requirement: The scope actions name the shape they produce

The `ctx` operator SHALL provide `dict` and `list` as separate actions instead of one polymorphic `map`:
`ctx.dict` SHALL take an object mapping a name to a bare scope path and produce an object of those
values; `ctx.list` SHALL take an array of bare scope paths and produce a list of those values, in order.
The action name SHALL state the result shape, so a reader does not have to inspect the parameter to know
what the stage yields.

#### Scenario: A named object from several paths

- **WHEN** the chain is `[["ctx","dict",{"a":"locals.x","b":"locals.y"}]]`
- **THEN** the outcome SHALL be `Ok({"a": <value of locals.x>, "b": <value of locals.y>})`

#### Scenario: A list from several paths

- **WHEN** the chain is `[["ctx","list",["locals.x","locals.y"]]]`
- **THEN** the outcome SHALL be `Ok([<value of locals.x>, <value of locals.y>])`

#### Scenario: The polymorphic action is gone

- **WHEN** a chain writes `["ctx","map",…]`
- **THEN** compilation SHALL fail with `UP2-E1002`, listing the legal actions

### Requirement: The `py` allowlist turns a mapping into key/value pairs

The `py` operator SHALL provide an `items` action that takes a mapping and produces `[[key, value], …]`
in the mapping's own order, with values limited to JSON. It SHALL take no parameter. Applied to a value
that is not a mapping it SHALL fail with the operator's input-type code rather than converting the value.

#### Scenario: A mapping becomes pairs

- **WHEN** the chain is `[["const",{"a":1,"b":2}], ["py","items",""]]`
- **THEN** the outcome SHALL be `Ok([["a",1],["b",2]])`

#### Scenario: The pairs feed each

- **WHEN** the chain is `[["const",{"a":1}], ["py","items",""], ["each",{"k":[["py","getitem",0]],"v":[["py","getitem",1]]}]]`
- **THEN** the outcome SHALL be `Ok([{"k":"a","v":1}])`

#### Scenario: A non-mapping is refused

- **WHEN** the chain is `[["const",[1,2]], ["py","items",""]]`
- **THEN** the outcome SHALL be `Failed` with the operator's input-type code

### Requirement: A conversion failure describes its input, not a fallback

When a `py` conversion action (`str`, `int`, `float`, `bool`, `list`, `from_json`) fails, its `fix` text
SHALL state the input the action expects and point at the upstream stage that produced the value. It
SHALL NOT recommend another operator, and in particular SHALL NOT present a fallback as the remedy for a
failure.

#### Scenario: A conversion failure names what was expected

- **WHEN** the chain is `[["py","int",""]]` and the input is `"not-a-number"`
- **THEN** the `fix` SHALL describe the accepted input and the upstream stage, and SHALL NOT name another
  operator as a fallback
