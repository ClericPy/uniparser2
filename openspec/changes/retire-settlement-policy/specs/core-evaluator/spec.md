## Purpose

The value domain: what a run may carry, what may leave it, and what a missing or failed value means.

## ADDED Requirements

### Requirement: Missing and failed have fixed outcomes

The kernel SHALL NOT offer a settlement policy: `Policy`, the missing and error strategies, the `policy`
parameter of `eval_field`, the `policy` block of a story and the CLI's `--on-missing` / `--on-error` SHALL
be absent, and `UP2-E2015` SHALL be retired without reusing its number.

A missing value SHALL mean "not there": in a field map the key SHALL be absent from the product and in a
batch the item SHALL be skipped, with no empty string and no null invented. A failed stage SHALL always
raise, carrying its code and JSON Pointer.

#### Scenario: a selector that never matched

- **WHEN** a field's chain ends in a selector that matched nothing
- **THEN** the field SHALL be absent from the step's product

#### Scenario: a value the type requires

- **WHEN** a host-registered type constructor is handed a product that lacks a required key
- **THEN** the constructor SHALL raise and the run SHALL fail at that step

#### Scenario: a failing stage

- **WHEN** any stage fails
- **THEN** the run SHALL fail with that stage's code and pointer, and no configuration SHALL degrade it

#### Scenario: tolerating one absence

- **WHEN** an author wants a fallback for a value that may be missing
- **THEN** the fallback SHALL be expressed at the action level (`py.default` / `py.or`), not by policy
