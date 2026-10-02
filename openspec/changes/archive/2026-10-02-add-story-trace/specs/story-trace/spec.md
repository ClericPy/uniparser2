# Spec Delta

## Purpose

Makes one run **readable stage by stage**: which stage of which field of which step of which fan-out
result produced which value, in what state, and how long it took — without shipping the values
themselves, and without changing what a run does when nobody asks for a trace. The trace is a
**debugging aid**; it is not the replay format (`03` §13 O6).

## ADDED Requirements

### Requirement: One event per evaluated stage

The trace SHALL record one event for every stage the engine **evaluates**, and no event for a stage
the tri-state short-circuit skips. A stage event SHALL carry `seq` (1-based, in evaluation order),
`step`, `item`, `field`, `stage` (the stage's index inside its own chain), `op`, `action`, `params`,
`input`, `output`, `state`, `detail` and `ms`. `state` SHALL be `Ok`, `Missing` or `Failed`, and
`detail` SHALL carry the stage's `code` and `reason` when it is `Failed` and nothing otherwise. A
chain that is evaluated without a trace SHALL collect nothing.

#### Scenario: Every stage of a chain is one event

- **WHEN** a three-stage field chain is evaluated with a trace
- **THEN** the trace SHALL hold three events whose `stage` is `0`, `1` and `2` and whose `op` /
  `action` name the stage that ran

#### Scenario: A short-circuit stage is absent

- **WHEN** the second stage of a chain is `Missing` and no later stage accepts a missing input
- **THEN** the trace SHALL hold two events, the second of them `Missing`

#### Scenario: A run without a trace collects nothing and is unchanged

- **WHEN** the same chain is evaluated with no trace
- **THEN** no event SHALL be recorded and the outcome SHALL be the outcome the traced run produced

### Requirement: Values are previews, and the whole value is fetched by `seq`

A stage event's `input` and `output` SHALL be a view carrying `type`, `preview` and `size` instead of
the value: `preview` SHALL be the first 200 characters of the value's display text, and `size` SHALL
be the length of that text. The trace SHALL expose `get_value(seq)` returning the full value of the
event with that `seq`, and SHALL make the event's input available as well. A value the kernel cannot
render as JSON (a host object, an `Opaque` handle, the missing sentinel) SHALL still be viewable.

#### Scenario: A long value is truncated, and the full value is still reachable

- **WHEN** a stage produces a text longer than 200 characters and the trace is read
- **THEN** its event's `output.preview` SHALL be the first 200 characters, `output.size` SHALL be the
  length of the whole text, and `get_value(seq)` on that event SHALL return the whole text

#### Scenario: A host object is not JSON but is still viewable

- **WHEN** a stage's value is a host object (an answer carrying `text`)
- **THEN** the event SHALL record its type name and a preview rather than failing

### Requirement: The event locates the step, the field and the fan-out result

A stage event SHALL name the story step whose chain it belongs to, the field-map key the chain was
compiled as, and the index of the fan-out result it was evaluated for — `null` when there is no
fan-out. Inside an `each` the index SHALL be the element's position in input order; for a
`RequestBatch`'s receiving step it SHALL be the answer's position in task order; when a fan-out is
nested inside another one, the innermost index SHALL win.

#### Scenario: The third result's field is locatable

- **WHEN** an `each` runs a field map whose `title` chain misses for the third element of a list
- **THEN** an event SHALL carry that field's name, `item` `2`, and `state` `Missing`

#### Scenario: A batch's receiving step is numbered by the answer

- **WHEN** a `RequestBatch` hands over three tasks and its receiving step is evaluated once per answer
- **THEN** the events of each evaluation SHALL carry that answer's position as `item`

### Requirement: The parameters are the compiled ones

A stage event's `params` SHALL be the stage's **compiled** named parameters (the named AST of `02`
§4), so that defaults the author did not write and the action slot's presets are visible, and so that
a reference is reported as a reference rather than as its text. A `call` step's suspension event
SHALL carry its compiled `with` tree the same way.

#### Scenario: A default and a reference are visible

- **WHEN** a stage declares one reference parameter and leaves another at its default
- **THEN** the event's `params` SHALL show the reference as a reference and the default as the value
  the engine used

### Requirement: A suspension is an event carrying what was handed out

The trace SHALL record one event per **effect suspension**, carrying `effect` as `request`, `batch`
or `call`, the step it happened at, the value the step received as its input, and what the kernel
handed to the host as its output. A `call` event SHALL carry the host function's name in `action`.
The suspension's `state` SHALL be `Ok`, because a suspension is not an error (`03` §5).

#### Scenario: A batch suspension shows the tasks

- **WHEN** a `RequestBatch` step suspends with three tasks
- **THEN** the trace SHALL hold an event with `effect` `batch` whose output previews the task list,
  placed after the events of the stage that produced the batch

#### Scenario: A call suspension names the function and its arguments

- **WHEN** a `call` step suspends
- **THEN** the trace SHALL hold an event with `effect` `call`, that function's name in `action`, its
  compiled arguments in `params`, and the resolved arguments in `output`

### Requirement: `up2 trial --trace` reports the trace

`up2 trial` SHALL accept `--trace`, reporting the run's events in evaluation order: with `--json` as
one JSON document carrying the events, without it as one line per event. The trace SHALL be reported
for a field chain and for a story, and SHALL also be reported when the run suspends or fails — with
the run's own state, effect or diagnostic in the same document. Without `--trace` the command's
output SHALL be exactly what it was before.

#### Scenario: A story suspends and the trace says why

- **WHEN** `up2 trial story.json --input text=@sample.txt --trace --json` runs a story whose first
  step suspends on a `RequestBatch`
- **THEN** the document SHALL carry the suspension and a trace whose last event is that batch
  suspension

#### Scenario: A failing stage is in the trace

- **WHEN** a step's chain fails
- **THEN** the command SHALL report the run as failed, and the trace SHALL hold the failing stage's
  event with its `code` and `reason`

#### Scenario: The flag is off by default

- **WHEN** `up2 trial` runs without `--trace`
- **THEN** the output SHALL carry no trace key
