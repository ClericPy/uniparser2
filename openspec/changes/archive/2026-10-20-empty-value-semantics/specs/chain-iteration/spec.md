# Spec Delta

## MODIFIED Requirements

### Requirement: A failure stays inside its element and no element is dropped

`each` SHALL produce one dictionary per input element, holding the keys its field map declares. A field
whose query matched nothing SHALL carry the empty value of that action's shape (it is a value, not an
absent key). `each` MUST NOT drop an element silently, and a failure MUST propagate out of `each` with
the code the failing stage reported.

#### Scenario: Every field is missing

- **WHEN** the chain is `[["each", {"n": [["css1","text","h1"]]}]]` and the value is
  `["<p>a</p>", "<h1>b</h1>"]`
- **THEN** the result is `[{"n": ""}, {"n": "b"}]`, a list of two dictionaries

#### Scenario: A failing stage propagates

- **WHEN** the chain is `[["each", {"first": [["py","getitem","0"]]}]]` and the value is `[42]`
- **THEN** the outcome is `UP2-E2018`, the code the failing stage reported

### Requirement: The run's output is the exit step's products

The run SHALL be done when execution passes the last step, and its product SHALL be the products of the
step `collect` names, collected in order as a list. Every executed step SHALL either contribute its
product or fail the run: there SHALL be no "skipped step", and no `null` is invented for a step that
produced nothing. A run whose exit step never executed SHALL be done with an empty list.

#### Scenario: A per-answer exit step

- **WHEN** the exit step runs once per answer of a batch of thirty
- **THEN** the run's product SHALL be a list of thirty products, in task order

#### Scenario: An exit step that never runs

- **WHEN** execution ends without reaching the step named by `collect`
- **THEN** the run SHALL be done with an empty list

#### Scenario: An exit step that produced nothing

- **WHEN** the exit step runs and its field chains each matched nothing
- **THEN** the run's product SHALL hold that step's product (its fields carrying the empty values), and
  SHALL NOT hold a `null`
