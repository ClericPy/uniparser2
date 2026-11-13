# Spec Delta

## REMOVED Requirements

### Requirement: `type` is a chain-tail validator

**Reason**: the stage now answers the constructed value instead of the payload, so a later stage sees
the instance and the tail rule has nothing left to protect. Superseded by "`type` constructs the
declared type".

## ADDED Requirements

### Requirement: `type` constructs the declared type

A chain MAY carry `["type", "Name"]` at any position. The stage SHALL build the host-registered type
from the current value and carry the **constructed value** onward, and it SHALL reject an unregistered
name with `UP2-E1011` or a raising constructor with `UP2-E2019`. A `type` stage that is not the last
stage of its chain MUST NOT be rejected: a later stage receives the constructed value. A constructed
value that reaches the run's exit MUST fail with `UP2-E2003`, because the exit is JSON.

#### Scenario: A constructed value flows on

- **WHEN** the host registers `Article` and a chain is `[["type","Article"], ["py","getattr","title"]]`
- **THEN** the stage SHALL answer the instance and the later stage SHALL read its `title`

#### Scenario: A missing key fails at the stage

- **WHEN** the registered dataclass requires `title` and the value has no `title`
- **THEN** the run fails with `UP2-E2019` and the constructor's message

#### Scenario: A type stage in the middle is accepted

- **WHEN** a chain is `[["type","Article"], ["py","strip",""]]`
- **THEN** compilation SHALL succeed and the stage SHALL run at its position

#### Scenario: A constructed value cannot be the exit

- **WHEN** the entry node's product is a constructed instance
- **THEN** `run` SHALL fail with `UP2-E2003` at the entry node

## MODIFIED Requirements

### Requirement: `run` is the synchronous facade

The package SHALL expose `run(story, node=None, input=None, *, globals=None, udfs=None, types=None,
trace=None)`. It MUST compile the story, merge `globals` over the story's constants, `udfs` over the
process-wide udf table and `types` over the process-wide type registry, execute the named node (the
first when omitted) and return its product. A udf the chosen node reaches MUST be in the effective
table, else `UP2-E1010` before evaluation. The run MUST be synchronous.

`types` MAY be a mapping of name → constructor, or a sequence of callables whose `__name__` is the
name. The merge SHALL NOT mutate the process-wide registry, and two runs with different overlays SHALL
resolve one name to their own constructors.

#### Scenario: The first node is the default

- **WHEN** a story has nodes `a` and `b` and `run(story, input="x")` is called
- **THEN** node `a` runs

#### Scenario: A named node runs

- **WHEN** `run(story, node="b", input="x")` is called
- **THEN** node `b` runs with `"x"` as its `$in`

#### Scenario: Globals are overridden for the run

- **WHEN** the story declares `base_url` and the run passes `globals={"base_url": "https://x/"}`
- **THEN** `$globals.base_url` is `"https://x/"` for that run, and the story's own table is unchanged

#### Scenario: A missing udf fails before evaluation

- **WHEN** the story uses `["udf","fetch"]` and the run provides no `fetch`
- **THEN** `run` raises `UP2-E1010` naming `fetch`

#### Scenario: The kernel does not await

- **WHEN** a udf returns an awaitable
- **THEN** the run fails with `UP2-E2009`

#### Scenario: A run injects its own type

- **WHEN** no host called `register_type` and the run passes `types={"Article": Article}`
- **THEN** a `["type","Article"]` stage SHALL construct `Article` for that run

#### Scenario: A class is named by its own name

- **WHEN** the run passes `types=[Article]`
- **THEN** the chain's `["type","Article"]` SHALL resolve, because the name comes from `__name__`

#### Scenario: The overlay does not leak into the process

- **WHEN** one run passes `types=[A]` and a later run passes nothing
- **THEN** the later run SHALL fail `UP2-E1011` on `["type","A"]`, because the first run's table was
  local to it
