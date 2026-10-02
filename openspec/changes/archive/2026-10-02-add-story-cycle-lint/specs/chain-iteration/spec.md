## ADDED Requirements

### Requirement: A story's flow is acyclic

The compiler SHALL draw the story's flow graph over its steps, from the first step, with **one edge per
step**: the step at the next array position, or — for a step whose `type` is `Request` / `RequestBatch`,
which SHALL declare `next` — the step `next` names. A step the walk enters twice SHALL be rejected at
compile time with `UP2-E1017`.

`next` SHALL remain free to name any step of the bundle, including one written earlier in the array: a
backward `next` whose target cannot reach the jumping step again SHALL compile and run. `exit` SHALL NOT
be an edge of the flow graph, and `MAX_STORY_STEPS` SHALL bound the graph, not the number of steps a run
may take.

#### Scenario: A next that closes a loop

- **WHEN** the steps are `feed` (a `Request` step whose `next` is `page`), `page`, and `again` (a
  `Request` step whose `next` is `feed`)
- **THEN** compilation SHALL fail with `UP2-E1017`, the message SHALL carry the travel path
  `feed -> page -> again -> feed`, and the JSON Pointer SHALL name the `next` of `again`

#### Scenario: A step that jumps to itself

- **WHEN** a `Request` step named `bad` declares `next: "bad"`
- **THEN** compilation SHALL fail with `UP2-E1017`

#### Scenario: A backward next into a region that cannot reach it

- **WHEN** a `RequestBatch` step written after its receivers declares `next` naming an earlier step, and
  no path leads from that receiver back to the batch step
- **THEN** the story SHALL compile, and the run SHALL deliver the batch to that receiver and finish

#### Scenario: A fan-out that falls through and jumps forward again

- **WHEN** a `Request` step's `next` names a later plain step, that step falls through to a
  `RequestBatch`, and the batch's `next` names a later step still
- **THEN** the story SHALL compile and the run SHALL finish with the last step's product

#### Scenario: A next naming a step that does not exist

- **WHEN** a `next` or an `exit` names a step the bundle does not declare
- **THEN** compilation SHALL still fail with `UP2-E1016`, not with the flow check
