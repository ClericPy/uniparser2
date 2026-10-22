# Spec Delta

## ADDED Requirements

### Requirement: An outcome is a value or a failure

The kernel SHALL expose exactly two outcomes: `Ok`, carrying a value, and `Failed`, carrying a code, a
reason and a fix. There SHALL be no third outcome for "not there", no action-level declaration that
accepts such an outcome, and no sentinel substituted for a value before an operator runs.

A query that matches nothing SHALL be `Ok` carrying the **empty value of its shape** (the per-action
mapping is specified in `dsl-operators`). A reference path that cannot be walked SHALL be `Failed` with
`UP2-E2001`. A failure SHALL stop the chain and reach the caller carrying the code and reason of the
stage that failed.

#### Scenario: a selector that matched nothing

- **WHEN** a chain runs `["css1","text","h1"]` against a document with no `h1`
- **THEN** the outcome SHALL be `Ok("")`, and the value SHALL flow to the next stage

#### Scenario: a reference that cannot be walked

- **WHEN** a chain reads `$locals.nope`
- **THEN** the outcome SHALL be `Failed` with `UP2-E2001`

#### Scenario: a failed stage stops the chain

- **WHEN** the first stage fails and a second stage follows it
- **THEN** the second stage SHALL NOT be evaluated

## REMOVED Requirements

### Requirement: Missing and failed have fixed outcomes

**Reason**: the state it describes no longer exists.

**Migration**: a query that matches nothing is `Ok` with the empty value of its shape; a path that does
not exist is `Failed`. `UP2-E2015` stays retired and is not reused.
