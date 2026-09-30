# Spec Delta

## ADDED Requirements

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
