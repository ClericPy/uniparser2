# Spec Delta

## MODIFIED Requirements

### Requirement: The run's output is the exit step's products

The run SHALL be done when execution passes the last step, and its product SHALL be the products of
the step named by `exit`, collected in order as a list. A step whose chain product is a missing value
SHALL be skipped, so the list SHALL hold the products that exist and nothing else: no `null` is invented
for a step that produced nothing. A run whose exit step never executed SHALL be done with an empty list.

#### Scenario: A per-answer exit step

- **WHEN** the exit step runs once per answer of a batch of thirty
- **THEN** the run's product SHALL be a list of thirty products, in task order

#### Scenario: An exit step that never runs

- **WHEN** execution ends without reaching the step named by `exit`
- **THEN** the run SHALL be done with an empty list

#### Scenario: An exit step that produced nothing

- **WHEN** the exit step runs but its chain product is a missing value
- **THEN** the run's product SHALL be an empty list, and that step SHALL NOT contribute a `null`
