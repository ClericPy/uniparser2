# Spec Delta

## MODIFIED Requirements

### Requirement: A story bundle declares ordered steps and a named exit

A story bundle SHALL be a JSON object carrying `entry` (the name of the step the run starts at), `steps`
(a non-empty array, whose order is execution order) and `exit` (the name of the step whose products form
the run's output). It MAY carry `globals` (a mapping of chain-level read-only constants). It SHALL NOT
carry a `chains` table: a parse rule is a step.

The run SHALL start at the step `entry` names, with the value the caller handed to the run as that
step's input. `entry` SHALL name a step of the same bundle; a missing `entry` or one that does not name a
string SHALL be `UP2-E1005` at `/entry`, and one that names no declared step SHALL be `UP2-E1016`, listing
the declared step names.

A step SHALL be a JSON object with `name`, an optional `type` (the product's type name), exactly one of
`parse` (an array, one field chain, or a `$` reference, or an object, a field map) and `call` (a host
function name), plus `with` only on a `call`. A field map SHALL be evaluated once, over the step's input,
with `_`-prefixed fields staying in that step's locals. A written `type` SHALL be resolved against the
type registry at the step boundary: a built-in name or a host registration is built from the product, an
unregistered name is `UP2-E1011`, and a constructor that refuses the product is `UP2-E2019`, both at that
step.

#### Scenario: A bundle with one parse step

- **WHEN** the bundle is `{"entry": "records", "steps": [{"name": "records", "parse": {"url": [["py","id",""]]},
  "type": "Record"}], "exit": "records"}` and the run's input is `{"url": "u"}`
- **THEN** the run SHALL finish with the output `[{"url": "u"}]`

#### Scenario: The run starts at the entry, not at the first step

- **WHEN** the bundle's `steps` array is `[a, b]` and its `entry` is `b`
- **THEN** the run SHALL execute `b` first, with the caller's value as its input

#### Scenario: A bundle has no entry

- **WHEN** the bundle carries `steps` and `exit` but no `entry`
- **THEN** compilation SHALL fail with `UP2-E1005` at `/entry`, because the start is declared, never
  derived from the array order

#### Scenario: An entry names a step that does not exist

- **WHEN** `entry` names a step the bundle does not declare
- **THEN** compilation SHALL fail with `UP2-E1016`, listing the declared step names

#### Scenario: A step declares both parse and call

- **WHEN** a step carries `parse` and `call`
- **THEN** compilation SHALL fail with `UP2-E1005`, naming the step

#### Scenario: A bundle has no exit

- **WHEN** the bundle carries `steps` but no `exit`
- **THEN** compilation SHALL fail with `UP2-E1005`, because the exit is declared, never derived

#### Scenario: A bundle carries a chains table

- **WHEN** a bundle carries `chains` beside `steps`
- **THEN** compilation SHALL fail with `UP2-E1005`: a parse rule is a step, and the bundle has no
  second namespace for one

#### Scenario: A declared type is unknown

- **WHEN** a step declares a `type` that is neither a built-in name nor registered
- **THEN** the run SHALL fail with `UP2-E1011` at that step, because the registry is host state and the
  bundle compiles without a host

### Requirement: The field map is validated recursively at compile time

The argument of `each` — and a step's `parse` field map, which is the same object shape — MUST be an
object of field name to chain; anything else MUST be rejected at compile time with `UP2-E1005` and a fix
line showing the accepted writing. Every sub-chain MUST be compiled like a top-level chain — so an
unknown operator, an unknown action, a malformed parameter or a dangling reference inside it is reported
at compile time with a pointer that reaches that stage inside the field map — and each sub-chain MUST
respect the per-chain stage limit. A field map nested deeper than `MAX_EACH_DEPTH` MUST fail at compile
time with `UP2-E1012`.

#### Scenario: An argument that is not an object

- **WHEN** the chain is `["each", "title"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` and the fix line shows `["each", {"title": [...]}]`

#### Scenario: A malformed sub-chain

- **WHEN** the chain is `[["each", {"title": [["py","no_such_function",""]]}]]` and it is compiled
- **THEN** compilation fails with `UP2-E1003` at the pointer of that stage inside the field map

#### Scenario: A field map nested too deeply

- **WHEN** four `each` stages are nested inside one another and the chain is compiled
- **THEN** compilation fails with `UP2-E1012`

## REMOVED Requirements

### Requirement: `py.id` returns its input unchanged

**Reason**: A step whose value is its own input no longer needs a stage. The reference form ("a chain may
be a whole-chain reference") spells identity directly, so `["py","id",""]` had no case left and the
action is deleted with its two uses in the samples. This re-settles `03` §13 O5.

**Migration**: replace `["py","id",""]` with the reference `"$in"`, and a chain that opened with the
identity stage by dropping that stage — the chain's first stage already receives the same input.

## ADDED Requirements

### Requirement: A chain may be a whole-chain reference

Wherever a chain is expected — the value of a field-map entry, or a step's `parse` when it is written as
an array — a **string beginning with `$`** SHALL be accepted and SHALL mean "the value the reference
names, unchanged and unconverted". It SHALL be the same reference spelling a parameter uses (`$globals`
/ `$locals` / `$in` / a step name, with a dotted path), resolved through the same path walk and the same
scope, and it SHALL be the **only** way to express identity: no single-element stage form SHALL be added.

Inside an `each` field map the chain's **input value** is the current element, so the first stage of such a
chain consumes that element; `$in` keeps naming the **step's** input (`02` §5). The reference SHALL be
validated at compile time by the same rules a parameter's reference uses: an unknown root or a step's own
name is `UP2-E1006`, and a `_`-prefixed key of another step is `UP2-E1014`.

#### Scenario: A field-map entry that is the step's input

- **WHEN** a step's field map is `{"url": "$in"}` and its input is the string
  `https://example.com/list.html`
- **THEN** the field SHALL hold that string, unchanged, with no stage evaluated for it

#### Scenario: A step's parse that is a whole chain

- **WHEN** a step's `parse` is the string `"$in"` and the run's input is the seed URL
- **THEN** the step's product SHALL be that URL

#### Scenario: A reference's value is not converted

- **WHEN** a chain is the reference `"$in"` and the input is a host object
- **THEN** the product SHALL be that same object

#### Scenario: A reference inside an each field map

- **WHEN** the chain is `[["each", {"whole": "$in", "elem": [["py","upper",""]]}]]`, the value is
  `["a", "b"]` and the step's input is `{"seed": "s"}`
- **THEN** the result SHALL be `[{"whole": {"seed": "s"}, "elem": "A"}, {"whole": {"seed": "s"}, "elem": "B"}]`,
  because the element is the stage's input value while `$in` still names the step's input (`02` §5)

#### Scenario: A chain that opens with a reference

- **WHEN** a chain is `["$globals.base", ["py","strip",""]]` and `globals.base` is `"  a  "`
- **THEN** the reference SHALL be read first and the stages after it evaluated in order

#### Scenario: A reference root that does not exist

- **WHEN** a chain is the string `"$nope"` and no step or reserved root carries that name
- **THEN** compilation SHALL fail with `UP2-E1006`, listing the accepted roots

#### Scenario: A step references its own name through a chain reference

- **WHEN** the field map of the step named `rows` is `{"url": "$rows.url"}`
- **THEN** compilation SHALL fail with `UP2-E1006`

### Requirement: A step unreachable from the entry is rejected

The compiler SHALL draw the story's flow graph over its steps from the step `entry` names, with one edge
per step (the step at the next array position, or the step a request step's `next` names), and every step
the walk cannot reach SHALL be rejected at compile time with `UP2-E1018`, whose diagnostic SHALL name the
unreachable step and point at it.

#### Scenario: A step nothing reaches

- **WHEN** the steps are `start` (a `Request` step whose `next` is `done`) and `done`, and a third step
  `orphan` is declared after them with nothing jumping to it
- **THEN** compilation SHALL fail with `UP2-E1018`, naming `orphan`

#### Scenario: The entry is not the first step of the array

- **WHEN** the steps are `[dead, start]` and `entry` is `start`
- **THEN** compilation SHALL fail with `UP2-E1018`, naming `dead`

#### Scenario: Every step is reachable

- **WHEN** every step is entered by the fall-through edge or by a `next` from a reachable step
- **THEN** the story SHALL compile
