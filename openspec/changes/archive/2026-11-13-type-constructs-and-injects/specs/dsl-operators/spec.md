# Spec Delta

## REMOVED Requirements

### Requirement: The `type` stage validates a chain's product

**Reason**: the stage now answers the constructed value and may appear anywhere, so "validates a
chain's product" and "must be the last stage" no longer describe it. Superseded by "The `type` stage
constructs the declared type".

## ADDED Requirements

### Requirement: The `type` stage constructs the declared type

A chain MAY carry `["type","name"]` at any position. The operator SHALL build the host-registered type
from the current value and answer the **constructed value**, so a later stage receives it. It MUST
take exactly two slots, one action and the name in slot 2. An unregistered name is `UP2-E1011`; a
raising constructor is `UP2-E2019`. The built-in names need no registration, and a host registration
wins over a built-in of the same name.

#### Scenario: A constructed value reaches the next stage

- **WHEN** `Article` is registered and the chain is `[["type","Article"], ["py","getattr","title"]]`
- **THEN** the answer SHALL be the `title` of the constructed `Article`

#### Scenario: A missing required field

- **WHEN** the registered constructor raises on the value
- **THEN** the outcome is `UP2-E2019` with the constructor's message

#### Scenario: A type stage is not last

- **WHEN** the chain is `[["type","Article"], ["py","strip",""]]`
- **THEN** compilation SHALL succeed, and `py.strip` SHALL receive the constructed instance

#### Scenario: A built-in name converts

- **WHEN** the value is `"42"` and the stage is `["type","int"]`
- **THEN** the answer SHALL be the number `42`
