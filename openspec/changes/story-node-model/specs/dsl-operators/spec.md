# Spec Delta

## ADDED Requirements

### Requirement: `py.sleep` blocks for a number of seconds and returns its input

`["py","sleep", seconds]` SHALL wait `seconds` seconds with `time.sleep` and answer the upstream value
unchanged. `seconds` MUST be a non-negative number written as a literal or a reference; a negative
number or a non-number MUST fail with `UP2-E2002`. The action is the allowlist's only blocking side
effect; the engine stays synchronous and the host owns concurrency.

#### Scenario: Sleep returns the same value

- **WHEN** the chain is `[["py","const",7], ["py","sleep",0]]` and it is evaluated
- **THEN** the result is `7`

#### Scenario: A negative number is refused

- **WHEN** the stage is `["py","sleep",-1]` and it is evaluated
- **THEN** the outcome is `UP2-E2002`

#### Scenario: A non-number is refused

- **WHEN** the stage is `["py","sleep","2"]` and it is evaluated
- **THEN** the outcome is `UP2-E2002`

### Requirement: `py.filter` keeps truthy or falsy list elements

`["py","filter"]` SHALL keep the elements that are truthy; `["py","filter", true]` SHALL do the same,
and `["py","filter", false]` SHALL keep the falsy elements. The input MUST be a list; the answer MUST
be a new list in input order. The action takes no callable: complex predicates belong to a sub-chain.

#### Scenario: Truthy elements are kept

- **WHEN** the chain is `[["py","filter"]]` and the value is `[0, 1, "", "a", None]`
- **THEN** the answer is `[1, "a"]`

#### Scenario: Falsy elements are kept

- **WHEN** the chain is `[["py","filter",false]]` and the value is `[0, 1, "", "a", None]`
- **THEN** the answer is `[0, "", null]`

#### Scenario: A non-list is refused

- **WHEN** the chain is `[["py","filter"]]` and the value is `"abc"`
- **THEN** the outcome is `UP2-E2002`

### Requirement: The `node` stage calls a story node

A chain SHALL support `["node","name"]`. The operator SHALL pass the current value to the named node
as its `$in` and answer the node's product. The name MUST be a literal naming a node of the same
story, otherwise `UP2-E1016` names the available nodes. The stage MUST take exactly two slots.

#### Scenario: A node call

- **WHEN** a story has `b` and a chain stage `["node","b"]` with value `"x"`
- **THEN** `b` runs with `$in = "x"` and its product is the stage value

#### Scenario: A three-slot node stage is malformed

- **WHEN** the stage is `["node","b","extra"]` and it is compiled
- **THEN** compilation fails with `UP2-E1004`

#### Scenario: An unknown node name

- **WHEN** the stage is `["node","gone"]` and no node has that name
- **THEN** compilation fails with `UP2-E1016`

### Requirement: The `type` stage validates a chain's product

A chain MAY end with `["type","name"]`. The operator SHALL build the host-registered type from the
current value, answer the validated JSON, and reject an unregistered name with `UP2-E1011` or a raising
constructor with `UP2-E2019`. The stage MUST take exactly two slots and MUST be the last stage of its
chain; a later stage is `UP2-E1005`. A non-JSON value is `UP2-E2003`.

#### Scenario: A valid product

- **WHEN** `Article` is registered and the chain ends with `["type","Article"]`
- **THEN** the answer is the JSON the constructor approved

#### Scenario: A missing required field

- **WHEN** the registered constructor raises on the value
- **THEN** the outcome is `UP2-E2019` with the constructor's message

#### Scenario: A type stage is not last

- **WHEN** the chain is `[["type","Article"], ["py","strip"]]`
- **THEN** compilation fails with `UP2-E1005`

### Requirement: `udf` binds its argument in four forms

The third slot of a `udf` stage SHALL select the call: omitted = `f(value)`; the literal `"*"` =
`f(*value)` with a list upstream; the literal `"**"` = `f(**value)` with a mapping upstream; any other
value = `f(argument)`. The name MUST resolve from the run's udf table, otherwise `UP2-E1010`. A udf MAY
answer any value; an awaitable answer is `UP2-E2009`.

#### Scenario: The DTO form

- **WHEN** the stage is `["udf","f"]` and the value is `{"a": 1}`
- **THEN** `f` receives one argument, `{"a": 1}`

#### Scenario: The spread forms

- **WHEN** the stage is `["udf","f","*"]` and the value is `[1, 2]`
- **THEN** `f` receives two positional arguments
- **AND** when the stage is `["udf","f","**"]` and the value is `{"a": 1}`, `f` receives `a=1`

#### Scenario: The explicit argument

- **WHEN** the stage is `["udf","f","x"]`
- **THEN** `f` receives the literal `"x"`

#### Scenario: A missing function

- **WHEN** the story uses `["udf","gone"]` and the run registers no such function
- **THEN** the run fails with `UP2-E1010` naming `gone`

#### Scenario: An awaitable answer

- **WHEN** the udf answers a coroutine
- **THEN** the outcome is `UP2-E2009`
