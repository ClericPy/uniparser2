# chain-iteration Specification

## Purpose
The chain layer's iteration construct: one operator that turns a list into one dictionary per element,
so a collected node set (or any other list a stage produces) can be parsed per item without a second
fan-out mechanism, a named chain container or a template directive.

## Requirements

### Requirement: `each` turns a list into one dictionary per element

`each` SHALL be an operator with arity 2 and exactly one action, written `["each", {<field name>:
<chain>, …}]`, so the stage carries its argument in slot 2 and no action text. Its input MUST be a
list; its result MUST be a list of dictionaries holding exactly one dictionary per input element, in
input order. Each field chain SHALL be evaluated with the element as its input value.

An empty list MUST yield an empty list, not a missing value. A non-list input MUST fail with
`UP2-E2002`, naming the type that arrived. A missing input is handled by the shared stage rule: `each`
does not accept a missing value, so the chain short-circuits before the operator runs.

#### Scenario: A list of two strings

- **WHEN** the chain is `[["each", {"n": [["py","len",""]], "u": [["py","upper",""]]}]]` and the value is
  `["ab", "cd"]`
- **THEN** the result is `[{"n": 2, "u": "AB"}, {"n": 2, "u": "CD"}]`

#### Scenario: An empty list

- **WHEN** the chain is `[["each", {"n": [["py","len",""]]}]]` and the value is `[]`
- **THEN** the result is `[]`

#### Scenario: The input order is preserved

- **WHEN** the chain is `[["each", {"raw": [["py","strip",""]]}]]` and the value is `["b", "a"]`
- **THEN** the result is `[{"raw": "b"}, {"raw": "a"}]`

#### Scenario: A collected node set

- **WHEN** the chain is `[["css","nodes","li"], ["each", {"title": [["css1","text","a"]]}]]` and the
  value is a document whose list holds two `<li>` elements
- **THEN** the result is a list of two dictionaries, each holding the title of its own element

#### Scenario: An input that is not a list

- **WHEN** the chain is `[["each", {"n": [["py","len",""]]}]]` and the value is `{"a": 1}`
- **THEN** the outcome is `UP2-E2002`, naming an object as the type that arrived

### Requirement: The field map is one ordered program per element

The argument of `each` MUST be an object whose values are chains, and its fields SHALL be evaluated in
declaration order, all of them against the same element and in one scope per element, so a later field
can read what an earlier field of the same element produced. The dictionary an element yields MUST
carry exactly those field names, in that order.

#### Scenario: A later field reads an earlier field's value

- **WHEN** the chain is `[["each", {"_raw": [["py","strip",""]], "seen": [["ctx","get","locals._raw"]]}]]`
  and the value is `["  a  "]`
- **THEN** the result is `[{"seen": "a"}]`

### Requirement: A `_`-prefixed key is a per-element local and never enters the dictionary

A field name beginning with `_` SHALL be stored as a local of that element instead of becoming a key of
its dictionary: it MUST be absent from the result, and it MUST remain readable by the later fields of
the same element.

#### Scenario: A temporary that two fields consume

- **WHEN** the chain is `[["each", {"_t": [["py","strip",""]], "a": [["ctx","get","locals._t"]],
  "b": [["ctx","get","locals._t"], ["py","upper",""]]}]]` and the value is `[" x "]`
- **THEN** the result is `[{"a": "x", "b": "X"}]`, with no `_t` key

### Requirement: Every element is evaluated in its own scope

Each element SHALL be evaluated in a fresh child scope of the scope that called `each`. Reads SHALL fall
back outward (the element's own locals first, then the calling scope's locals, then the chain-level
values), writes SHALL land in the element's own scope, and the element's locals MUST NOT outlive the
element or be visible to another element.

#### Scenario: An element local shadows an outer one

- **WHEN** the chain is `[["ctx","set","locals.t"], ["each", {"seen": [["py","upper",""],
  ["ctx","set","locals.t"], ["ctx","get","locals.t"]]}]]` and the value is `["a"]`
- **THEN** the result is `[{"seen": "A"}]`, not the value the calling scope wrote

#### Scenario: An element reads a value from the calling scope

- **WHEN** the chain is `[["ctx","set","locals.base"], ["each", {"base":
  [["ctx","get","locals.base"]]}]]` and the value is `["a"]`
- **THEN** the result is `[{"base": ["a"]}]`

#### Scenario: An element's local does not outlive the element

- **WHEN** the chain is `[["each", {"_t": [["py","strip",""]]}], ["ctx","get","locals._t"]]` and the
  value is `["a"]`
- **THEN** the final read resolves as a missing value under the effective policy, never as the
  element's temporary

### Requirement: A failure stays inside its element and no element is dropped

The effective policy SHALL be applied per element, so a value that is missing for one element resolves
for that element alone and does not disturb the others. `each` MUST NOT drop an element silently: the
result holds one dictionary per input element even when every field of an element resolves to absent,
and a failure whose effective policy is `raise` MUST propagate out of `each` with the code the failing
stage reported.

#### Scenario: Every field is missing under a dropping policy

- **WHEN** the chain is `[["each", {"n": [["ctx","get","locals.nope"]]}]]` is evaluated with
  `on_missing="drop"` and the value is `["a", "b"]`
- **THEN** the result is `[{}, {}]`, a list of two dictionaries

#### Scenario: A failing stage propagates

- **WHEN** the chain is `[["each", {"first": [["py","getitem","0"]]}]]` is evaluated with the default
  `on_error="raise"` and the value is `["ab"]`
- **THEN** the outcome is `UP2-E2002`, the code the failing stage reported

### Requirement: The field map is validated recursively at compile time

The argument MUST be an object of field name to chain; anything else MUST be rejected at compile time
with `UP2-E1005` and a fix line showing the accepted writing. Every sub-chain MUST be compiled like a
top-level chain — so an unknown operator, an unknown action, a malformed parameter or a dangling
reference inside it is reported at compile time with a pointer that reaches that stage inside the field
map — and each sub-chain MUST respect the per-chain stage limit. A field map nested deeper than
`MAX_EACH_DEPTH` MUST fail at compile time with `UP2-E1012`.

#### Scenario: An argument that is not an object

- **WHEN** the chain is `["each", "title"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` and the fix line shows `["each", {"title": [...]}]`

#### Scenario: A malformed sub-chain

- **WHEN** the chain is `[["each", {"title": [["py","no_such_function",""]]}]]` and it is compiled
- **THEN** compilation fails with `UP2-E1003` at the pointer of that stage inside the field map

#### Scenario: A field map nested too deeply

- **WHEN** four `each` stages are nested inside one another and the chain is compiled
- **THEN** compilation fails with `UP2-E1012`

### Requirement: The input length limit is checked before evaluation

An input list longer than `MAX_EACH_ITER` MUST fail with `UP2-E2012` before any field chain runs.

#### Scenario: One element over the limit

- **WHEN** the chain is `[["each", {"n": [["py","len",""]]}]]` and the value is a list of 10 001
  elements
- **THEN** the outcome is `UP2-E2012`, and the fix line names `py.slice` as the way to truncate first
