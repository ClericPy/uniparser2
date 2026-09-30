# dsl-operators Specification

## Purpose
The operator layer's chain-facing contract: which writing an action's parameter slot takes, what each
action validates about its own parameters before a chain runs, and how the operator registry
self-describes both to a chain writer.

## Requirements

### Requirement: A scalar action parameter is validated at compile time

When an action declares a parameter that only accepts a scalar (a string or an integer), a chain that
gives that parameter a JSON container MUST be rejected at compile time with `UP2-E1005`, reporting the
position of that parameter and a fix line that shows the accepted writing. This applies to every
operator, `py`'s function table included: the selector family's selector, `re`'s pattern, `ctx`'s path
and `json`'s expression already behave this way, and `py`'s scalar parameters MUST behave the same way
instead of failing during evaluation.

A parameter that accepts any JSON value MUST keep accepting containers: a container written for such a
parameter is a value, not a malformed parameter binding.

#### Scenario: A named object written for a single-parameter `py` function

- **WHEN** the chain is `["py", "urljoin", {"base": "https://example.com/news/"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the `base` parameter, and the fix line shows the
  accepted writing `["py", "urljoin", "https://example.com/news/"]`

#### Scenario: A container written for a scalar parameter of `py`

- **WHEN** the chain is `["py", "slice", {"spec": "0:4"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the `spec` parameter

#### Scenario: The same mistake on an operator that already validates it

- **WHEN** the chain is `["css1", "text", {"selector": "h1"}]` and it is compiled
- **THEN** compilation still fails with `UP2-E1005` at the `selector` parameter

#### Scenario: A container value for a parameter that accepts any type

- **WHEN** the chain is `[["ctx", "get", "locals.nope"], ["py", "default", {"a": 1}]]` and it is
  evaluated
- **THEN** compilation succeeds and the result is the container `{"a": 1}`

#### Scenario: The named form of a multi-parameter action is unaffected

- **WHEN** the chain is `["py", "split", {"sep": ",", "maxsplit": 1}]` and it is evaluated on `a,b,c`
- **THEN** compilation succeeds and the result is `["a", "b,c"]`

### Requirement: The operator self-description states the parameter-slot shape

For every action, the capability self-description printed by `up2 ops` MUST state which writing the
action's parameter slot takes — the value itself (`value`), a named object with a positional array
equally accepted (`named`), or no parameter at all (`none`) — and the machine-readable and human views
MUST use the same three tokens and agree on the value. The shape is decided by the number of
parameters the action still has to fill, so a parameter that the action slot itself already provides
does not count towards it. The reported shape MUST agree with what compilation accepts for that
action.

#### Scenario: A single-parameter action

- **WHEN** `up2 ops` reports `py`'s `slice` action
- **THEN** its parameter-slot shape is `value`

#### Scenario: A multi-parameter action

- **WHEN** `up2 ops` reports `re`'s `group` action
- **THEN** its parameter-slot shape is `named`

#### Scenario: An action whose parameter is provided by the action slot

- **WHEN** `up2 ops` reports the `css` / `css1` attribute accessor `@<attribute>`, whose `attr`
  parameter is provided by the accessor itself
- **THEN** its parameter-slot shape is `value`, because only the selector is left to fill

#### Scenario: An action with no parameters

- **WHEN** `up2 ops` reports `py`'s `strip` action
- **THEN** its parameter-slot shape is `none`

#### Scenario: An open action space reports the shape compilation sees

- **WHEN** `up2 ops` reports the `udf` extension point, whose action space is declared by the host and
  is modelled as a single parameter on the compilation side
- **THEN** its parameter-slot shape is `value` (the writing that compiles), and the operator's own
  evaluation still requires that value to be the host function's keyword-argument object

#### Scenario: The two views agree

- **WHEN** the same action is reported once by `up2 ops` and once by `up2 ops --json`
- **THEN** both report the same parameter-slot shape token

### Requirement: A parameter whose value is a field map is validated recursively at compile time

An action MAY declare a parameter whose value is a **field map**: an object mapping a field name to a
chain, rather than a scalar or an arbitrary JSON value. For such a parameter, a value that is not an
object MUST be rejected at compile time with `UP2-E1005` at that parameter, and the fix line MUST show
the accepted writing. Every value of the map MUST be compiled like a top-level chain, so an unknown
operator, an unknown action, a wrong stage length or a malformed parameter inside a sub-chain is
reported at compile time with a pointer that reaches the offending stage inside that sub-chain.
Containers that appear where a chain is expected are NOT values: the rule that a container written for a
parameter accepting any JSON value is a value MUST NOT be applied to a field map. The
parameter-slot shape reported by `up2 ops` remains decided by the existing rule (the number of
parameters the action still has to fill).

#### Scenario: A field map compiles and evaluates

- **WHEN** the chain is `[["each", {"title": [["py","strip",""]]}]]` and the value is `[" a "]`
- **THEN** compilation succeeds and the result is `[{"title": "a"}]`

#### Scenario: A value that is not an object

- **WHEN** the chain is `["each", "title"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the parameter

#### Scenario: An unknown operator inside a sub-chain

- **WHEN** the chain is `[["each", {"title": [["nope","text",""]]}]]` and it is compiled
- **THEN** compilation fails with `UP2-E1001`, and the pointer reaches the stage inside the field map

#### Scenario: A wrong stage length inside a sub-chain

- **WHEN** the chain is `[["each", {"title": [["py"]]}]]` and it is compiled
- **THEN** compilation fails with `UP2-E1004`, and the pointer reaches the stage inside the field map

#### Scenario: The parameter-slot shape of a field-map parameter

- **WHEN** `up2 ops` reports the `each` operator
- **THEN** its parameter-slot shape is `value`, because only the field map is left to fill
