# Spec Delta

## ADDED Requirements

### Requirement: The evaluation scope carries the run's materialization cache

The evaluation scope SHALL carry the materialization cache of the run it belongs to, and it SHALL make
that cache available to the operators it evaluates. A scope created for a nested evaluation SHALL share
its parent's cache, so an operator invoked at any depth of one run reaches the same cache. Creating a
scope SHALL NOT itself materialize anything, and a scope that never evaluates a text-consuming operator
SHALL hold no artifact.

#### Scenario: An operator reaches the run's cache

- **WHEN** an operator is evaluated through a scope of a run
- **THEN** it SHALL be able to materialize its source through that run's cache

#### Scenario: A nested scope shares the parent's cache

- **WHEN** a nested evaluation creates a child scope and materializes a document its parent's step
  already materialized
- **THEN** the child SHALL hit the parent's entry and no second artifact SHALL be built

#### Scenario: A scope without materialization

- **WHEN** a scope is created and only non-materializing actions are evaluated through it
- **THEN** the run's cache SHALL hold no artifact and account no materialized bytes
