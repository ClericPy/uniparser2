# Spec Delta

## ADDED Requirements

### Requirement: The `py` allowlist has no identity action

The `py` function table SHALL NOT contain an `id` action. Identity SHALL be written as a whole-chain
reference (`chain-iteration`, "A chain may be a whole-chain reference"), so a chain that passes its own
input through writes the reference instead of a stage, and `up2 ops` MUST NOT list `id` among `py`'s
actions.

#### Scenario: The identity stage is rejected

- **WHEN** the chain is `[["py","id",""]]` and it is compiled
- **THEN** compilation SHALL fail with `UP2-E1003`, listing the allowlisted function names

#### Scenario: The catalogue no longer offers it

- **WHEN** `up2 ops` reports the `py` operator
- **THEN** its action list SHALL NOT contain `id`

