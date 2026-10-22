# Spec Delta

## MODIFIED Requirements

### Requirement: One event per evaluated stage

The trace SHALL record one event for every stage the engine **evaluates**, and no event for a stage a
failure stopped the chain before. A stage event SHALL carry `seq` (1-based, in evaluation order), `step`,
`item`, `field`, `stage` (the stage's index inside its own chain), `op`, `action`, `params`, `input`,
`output`, `state`, `detail` and `ms`. `state` SHALL be `Ok` or `Failed`, and `detail` SHALL carry the
stage's `code` and `reason` when it is `Failed` and nothing otherwise. A chain that is evaluated without
a trace SHALL collect nothing.

#### Scenario: Every stage of a chain is one event

- **WHEN** a three-stage field chain is evaluated with a trace
- **THEN** the trace SHALL hold three events whose `stage` is `0`, `1` and `2` and whose `op` /
  `action` name the stage that ran

#### Scenario: A short-circuit stage is absent

- **WHEN** the second stage of a chain fails, so the third stage is never evaluated
- **THEN** the trace SHALL hold two events, the second of them `Failed`, carrying that stage's code

#### Scenario: A run without a trace collects nothing and is unchanged

- **WHEN** the same chain is evaluated with no trace
- **THEN** no event SHALL be recorded and the outcome SHALL be the outcome the traced run produced
