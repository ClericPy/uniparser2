# story-nodes Specification

## Purpose
Defines a story as a map of callable nodes: the bundle shape, node bodies, node calls, the field-map
rule that writes every field to `$locals`, the `type` constructor stage, the synchronous `run` facade,
and the JSON boundary at the exit.

## Requirements

### Requirement: A story is globals plus nodes

A story bundle SHALL be a JSON object with an optional `globals` object and a required non-empty
`nodes` object. It MUST NOT declare `entry`, `collect` or `steps`. A story with no nodes, or with
`nodes` that is not an object, MUST be rejected at compile time with `UP2-E1005` and a JSON Pointer.

#### Scenario: A minimal story compiles

- **WHEN** the bundle is `{"nodes": {"parse": [["py", "strip"]]}}`
- **THEN** it compiles and the node `parse` is the only entry point

#### Scenario: The old keys are rejected

- **WHEN** the bundle declares `steps`, `entry` or `collect`
- **THEN** compilation fails with `UP2-E1005` at the offending key

#### Scenario: An empty node table is rejected

- **WHEN** the bundle is `{"nodes": {}}`
- **THEN** compilation fails with `UP2-E1005` at `/nodes`

### Requirement: A node is a chain or a field map

A node body SHALL be either an array (one chain, `[]` is identity) or an object (one field map).
The two shapes are the only node bodies: a string, a number or any other shape MUST be rejected at
compile time with `UP2-E1005`. An empty field map MUST be rejected; an empty array MUST compile as
identity.

#### Scenario: An empty chain is identity

- **WHEN** a node is `[]` and the run calls it with `"x"`
- **THEN** the node answers `"x"`

#### Scenario: An empty field map is rejected

- **WHEN** a node is `{}`
- **THEN** compilation fails with `UP2-E1005`

#### Scenario: A scalar node body is rejected

- **WHEN** a node is `"$in"` or `7`
- **THEN** compilation fails with `UP2-E1005` at that node

### Requirement: A field map writes every field to the current locals

A field map SHALL evaluate every field chain against the node's input, in declaration order. Every
field's value MUST be written into the current scope's `$locals` under the field name. A field whose
name starts with `_` MUST NOT be added to the product; every other field MUST be. A later field can
therefore read an earlier one with `$locals.name`.

#### Scenario: A local field feeds a later field

- **WHEN** the field map is `{"_tmp": [["py","upper"]], "up": [["py","const","AB"]]}` on `"ab"`
- **THEN** the product is `{"up": "AB"}` and `$locals._tmp` is `"AB"`

#### Scenario: A product field is also a local

- **WHEN** the field map is `{"title": [["py","strip"]], "seen": [["ctx","get","locals.title"]]}`
  on `"  a  "`
- **THEN** the product is `{"title": "a", "seen": "a"}`

#### Scenario: Fields do not chain into each other

- **WHEN** the field map is `{"a": [["py","upper"]], "b": [["py","lower"]]}` on `"x"`
- **THEN** both chains see `"x"`, and the product is `{"a": "X", "b": "x"}`

### Requirement: A node call runs a named node on the current value

A chain SHALL support `["node", "name"]` as a stage. The current stage value MUST become the
callee's `$in`; the callee's product MUST become the stage value. The name MUST resolve to a node of
the same story at compile time, otherwise `UP2-E1016` names the available nodes. A node call MUST
share the caller's `$locals` and MUST restore the caller's `$in` when it returns.

#### Scenario: A node call composes two chains

- **WHEN** `a` is `[["py","upper"], ["node","b"]]`, `b` is `[["py","strip"]]`, and `a` is called
  with `" x "`
- **THEN** the result is `"X"`

#### Scenario: The callee sees the call value

- **WHEN** `b` is `{"seen": []}` and `a` calls `["node","b"]` with `"v"`
- **THEN** the result is `{"seen": "v"}`

#### Scenario: An unknown node is rejected at compile time

- **WHEN** a stage is `["node", "gone"]` and no node has that name
- **THEN** compilation fails with `UP2-E1016`, listing the node names

#### Scenario: A callee sees the caller's locals

- **WHEN** a field map writes `title`, then calls `["node","detail"]`, and `detail` reads
  `$locals.title`
- **THEN** the read succeeds

### Requirement: The node-call graph is acyclic

Compilation SHALL collect every `node` stage, including the sub-chains of `each`, and MUST reject a
cycle with `UP2-E1017`, naming the travel path and pointing at the stage that closes the loop.

#### Scenario: A direct self-call is a cycle

- **WHEN** node `a` contains `["node","a"]`
- **THEN** compilation fails with `UP2-E1017` at that stage

#### Scenario: An indirect cycle is a cycle

- **WHEN** `a` calls `b` and `b` calls `a`
- **THEN** compilation fails with `UP2-E1017` and the message contains `a -> b -> a`

### Requirement: `run` is the synchronous facade

The package SHALL expose `run(story, node=None, input=None, *, globals=None, udfs=None, types=None,
trace=None)`. It MUST compile the story, merge `globals` over the story's constants, `udfs` over the
process-wide udf table and `types` over the process-wide type registry, execute the named node (the
first when omitted) and return its product. A udf the chosen node reaches MUST be in the effective
table, else `UP2-E1010` before evaluation. The run MUST be synchronous.

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

### Requirement: A run may inject its own type table

`types` MAY be a mapping of name to constructor, or a sequence of callables whose `__name__` is the
name. The merge SHALL NOT mutate the process-wide registry, and two runs with different overlays SHALL
resolve one name to their own constructors.

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

### Requirement: The exit reports the product unchanged

`run` SHALL return the entry node's product exactly as the run produced it. There MUST be no export
check, no handle rejection and no substituted error: a host object, a DOM handle, a `datetime` or a
`type` stage's constructed instance IS the product when the chain produced it. Serializing a product
is the host's concern, and a value the host cannot serialize fails in the host's own serializer.

#### Scenario: A response object can be the exit

- **WHEN** the entry node returns a host response object
- **THEN** `run` returns that same object

#### Scenario: A response object can be parsed mid-chain

- **WHEN** a node fetches a response, reads `py.getattr text`, and returns a JSON field map
- **THEN** the run succeeds

#### Scenario: A constructed value is the exit

- **WHEN** the entry node's product is a constructed instance
- **THEN** `run` SHALL answer that instance

### Requirement: The CLI accepts the node model

`up2 lint` SHALL compile a story and report its node count and names. `up2 trial` SHALL accept a
`--node` option; without it the first node runs. Because the CLI has no host, a story that calls a
udf SHALL report `UP2-E1010` listing the missing function names instead of reaching the network.

#### Scenario: Linting a story

- **WHEN** `up2 lint site.json` runs on a valid node story
- **THEN** it prints the node count and exits `0`

#### Scenario: Trial names the node

- **WHEN** `up2 trial site.json --node parse --input text=…` runs
- **THEN** node `parse` runs with the input

#### Scenario: A fetch story without a host fails clearly

- **WHEN** a story calls `["udf","fetch"]` and the CLI has no host
- **THEN** the trial fails with `UP2-E1010` naming `fetch`

### Requirement: `type` constructs the declared type

A chain MAY carry `["type", "Name"]` at any position. The stage SHALL build the host-registered type
from the current value and carry the **constructed value** onward, and it SHALL reject an unregistered
name with `UP2-E1011` or a raising constructor with `UP2-E2019`. A `type` stage that is not the last
stage of its chain MUST NOT be rejected: a later stage receives the constructed value.

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
- **THEN** `run` SHALL answer that instance
