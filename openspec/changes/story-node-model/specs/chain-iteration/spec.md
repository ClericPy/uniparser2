# Spec Delta

## MODIFIED Requirements

### Requirement: The field map is one ordered program per element

In the field-map mode the argument of `each` MUST be an object whose values are chains, and its fields
SHALL be evaluated in declaration order, all of them against the same element and in one scope per
element, so a later field can read what an earlier field of the same element produced. Every field's
value MUST be written into the element scope's `$locals` under the field name. The dictionary an
element yields MUST carry the field names that do not start with `_`, in declaration order.

#### Scenario: A later field reads an earlier field's value

- **WHEN** the chain is `[["each", {"_raw": [["py","strip"]], "seen": [["ctx","get","locals._raw"]]}]]`
  and the value is `["  a  "]`
- **THEN** the result is `[{"seen": "a"}]`

#### Scenario: A product field is a local too

- **WHEN** the chain is `[["each", {"a": [["py","strip"]], "b": [["ctx","get","locals.a"]]}]]` and the
  value is `["  x  "]`
- **THEN** the result is `[{"a": "x", "b": "x"}]`

### Requirement: A `_`-prefixed key is a per-element local and never enters the dictionary

Every field of an element SHALL be stored as a local of that element. A field name beginning with `_`
MUST be absent from the element's dictionary while remaining readable by the later fields of the same
element; a field without the prefix MUST appear in the dictionary as well.

#### Scenario: A temporary that two fields consume

- **WHEN** the chain is `[["each", {"_t": [["py","strip",""]], "a": [["ctx","get","locals._t"]],
  "b": [["ctx","get","locals._t"], ["py","upper",""]]}]]` and the value is `[" x "]`
- **THEN** the result is `[{"a": "x", "b": "X"}]`, with no `_t` key

### Requirement: The field map is validated recursively at compile time

The argument of `each` — and a story node's field map, which is the same object shape — MUST be an
object of field name to chain, or an array holding exactly one chain; anything else MUST be rejected at
compile time with `UP2-E1005` and a fix line showing both accepted writings. Every sub-chain MUST be
compiled like a top-level chain — so an unknown operator, an unknown action, a malformed parameter or a
dangling reference inside it is reported at compile time with a pointer that reaches that stage inside
the field map — and each sub-chain MUST respect the per-chain stage limit. A field map nested deeper
than `MAX_EACH_DEPTH` MUST fail at compile time with `UP2-E1012`.

#### Scenario: An argument that is not an object

- **WHEN** the chain is `["each", "title"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` and the fix line shows both accepted writings,
  `["each", {"title": [...]}]` and `["each", [[...]]]`

#### Scenario: A malformed sub-chain

- **WHEN** the chain is `[["each", {"title": [["py","no_such_function"]]}]]` and it is compiled
- **THEN** compilation fails with `UP2-E1003` at the pointer of that stage inside the field map

#### Scenario: A malformed chain in the array form

- **WHEN** the chain is `[["each", [["py","no_such_function"]]]]` and it is compiled
- **THEN** compilation fails with `UP2-E1003` at the pointer of that stage inside the array

#### Scenario: A field map nested too deeply

- **WHEN** four `each` stages are nested inside one another and the chain is compiled
- **THEN** compilation fails with `UP2-E1012`

## REMOVED Requirements

### Requirement: A story bundle declares ordered steps and a named exit

**Reason**: replaced by the node model (`story-nodes`): `globals` + `nodes`, no `entry`, `collect` or
`steps`, and node bodies are chains or field maps.

**Migration**: rewrite the bundle as `{"globals": …, "nodes": {"name": <chain or field map>, …}}`;
call `run(story, node=…, input=…)` instead of `start`/`go`/`feed`.

### Requirement: Step names are unique, unreserved and resolvable

**Reason**: node names are the keys of the `nodes` object, so uniqueness is structural; reserved-root
and character rules are redefined in `story-nodes`.

**Migration**: rename a step to a node key; do not use `globals`, `locals`, `public`, `in` or `obj`,
or a name containing `.`, `/` or `~`.

### Requirement: A request step names the step that receives the responses

**Reason**: there are no request steps and no `next`; `fetch` is a `udf` and the value it returns is the
next stage's input.

**Migration**: write `["udf","fetch"]` in the chain, then read the response with `py.getattr`.

### Requirement: An answer is parsed by the step that receives it

**Reason**: the answer is the udf's return value, consumed by the same chain; there is no receiving
step.

**Migration**: put the parsing stages after `["udf","fetch"]`, or call a parse node with
`["node","parse"]`.

### Requirement: The run's output is the exit step's products

**Reason**: `collect` is gone; `run` returns the product of the node it was called with.

**Migration**: make the exit node the entry of the run, or call it from a wrapper node.

### Requirement: `$in` names the current step's own input

**Reason**: `$in` now names the current **node invocation's** input; the rule is restated in
`story-nodes`.

**Migration**: no change for a chain at the top of a node; inside `each`, the element is the stage
value and `$in` is still the node input.

### Requirement: A chain may be a whole-chain reference

**Reason**: the identity form is `[]`; a string in chain position is no longer accepted, and references
are parameter leaves (`$in.url`, `$locals.name`, …).

**Migration**: replace `"field": "$in"` with `"field": []`, and `["$in", [...]]` with the stage list
that starts from the input value.

### Requirement: A step unreachable from the entry is rejected

**Reason**: every node is an entry point, so nothing is unreachable.

**Migration**: none; remove the unreachable node or keep it as a callable entry.

### Requirement: The run loop suspends on an effect and resumes the same run

**Reason**: the kernel is synchronous; there are no effects. Host code enters through `udf`, and a
`fetch` blocks inside the run.

**Migration**: register `fetch` (and any other host function) in `run(udfs={...})`; call `run` from the
thread or event-loop strategy the host chooses.

### Requirement: The CLI accepts a story file

**Reason**: the CLI still accepts a story, but the shape and the entry rule changed; the replacement is
in `story-nodes`.

**Migration**: `up2 lint site.json`; `up2 trial site.json --node <name>` (the first node is the
default).

### Requirement: A story's flow is acyclic

**Reason**: the step flow is gone; the replacement is the node-call graph rule in `story-nodes`.

**Migration**: break the cycle by inlining one node or by running two calls from the host.
