# core-evaluator Specification

## Purpose

The value domain: what a run may carry, what may leave it, and what a no-match and a failure mean.

## Requirements

### Requirement: A value that flows may be a host object

A run SHALL accept a host object as a value (a response object, a DOM handle, anything an action returns),
using the same mechanism that already carries an `Opaque` handle. Such an object SHALL NOT be copied,
wrapped or converted on the way in. A `datetime` that `py.strptime` or `py.from_timestamp` produced SHALL
be such an internal value: it MAY flow between stages (`py.strftime` and `py.to_timestamp` consume one),
because what the value domain forbids is its **export**, not its existence.

#### Scenario: an object flows through a step

- **WHEN** a step's input is a response object and its field map reads `["py","getattr","text"]`
- **THEN** the chain SHALL read that object's own `text` attribute, unchanged

#### Scenario: an object reaches the exit

- **WHEN** a run's exit product would contain a host object
- **THEN** the run SHALL fail with `UP2-E2003`

#### Scenario: a datetime flows between stages

- **WHEN** the chain is `[["py","strptime","%d.%m.%Y"], ["py","strftime","%Y/%m/%d"]]` and the input is
  `"24.09.2026"`
- **THEN** both stages succeed and the result is `"2026/09/24"`

#### Scenario: a datetime reaches the exit

- **WHEN** the chain is `[["py","strptime","%d.%m.%Y"]]` and the input is `"24.09.2026"`
- **THEN** the run fails with `UP2-E2003`, and the fix line names `["py","strftime","…"]` as the way to
  export it

### Requirement: A step product SHALL be JSON

Every step product SHALL be JSON after the host-registered type constructor has run. A host object MAY be an
input, a `call` argument or an answer; it SHALL NOT be a product.

#### Scenario: a `udf` returns an object

- **WHEN** a `udf` returns a dataclass instance
- **THEN** the stage SHALL fail with `UP2-E2009`, whose message says the value cannot be a product

### Requirement: `getattr` reads an attribute of the value that flows in

The `py` operator SHALL provide a `getattr` action whose required `ref_or_literal` parameter names an
attribute of the stage's input value, and it SHALL return that attribute's value.

#### Scenario: the attribute exists

- **WHEN** the input is a `selectolax` node and the action is `["py","getattr","attributes"]`
- **THEN** it SHALL return the node's attribute dictionary

#### Scenario: the attribute does not exist

- **WHEN** the action is `["py","getattr","txet"]` on a response object
- **THEN** it SHALL fail with `UP2-E2002`, and `reason` SHALL begin with the exception class, such as
  `AttributeError: 'Response' object has no attribute 'txet'`

#### Scenario: the attribute is a method

- **WHEN** the action is `["py","getattr","text"]` on a `selectolax` node, where `text` is a method
- **THEN** it SHALL fail with `UP2-E2002`, and `fix` SHALL name the operator to use instead
  (`["css","text",""]`) or a `udf`

### Requirement: A reference path may walk an object

Reference resolution SHALL read a mapping by key, a sequence by index and an object with `getattr`, so a
dotted path works on both a dictionary and an object. An attribute that is **callable** SHALL be refused
with `UP2-E2002`, using the same message shape and the same fix hint `py.getattr` uses: a method is not a
value, and it could not leave the run (`UP2-E2003`) in any case.

The reserved roots SHALL be `globals` (read-only for every step), `locals` (this step's own scope) and
`in` (this step's own input). Every other root SHALL name a step of the story, and a reference that names
no such root SHALL fail with `UP2-E1006`, listing the roots that are accepted. `$fields` SHALL NOT be a
root: it was a second name for `locals` and is retired, so a stage that writes it fails at compile time
like any other unknown root.

#### Scenario: a dotted path into an object

- **WHEN** a stage writes `$resp.headers` and `$resp` is a response object
- **THEN** the reference SHALL resolve through `getattr`, and a missing attribute SHALL fail naming the
  class, exactly as `getattr` does

#### Scenario: an attribute that is a method

- **WHEN** a stage writes `$resp.json` and `json` is a method of `$resp`
- **THEN** the reference SHALL fail with `UP2-E2002`, and its `fix` SHALL be the fix hint `py.getattr`
  carries (naming `["css","text",""]` or a `udf`)

#### Scenario: a header that is not a dotted path

- **WHEN** a stage needs `Content-Type`, which contains a hyphen and is therefore not a dotted path
- **THEN** it SHALL be read from the headers mapping with `["py","getitem","content-type"]`

#### Scenario: the retired root

- **WHEN** a stage writes `$fields.title`
- **THEN** the reference SHALL fail with `UP2-E1006`, an unknown reference root, and the accepted roots
  SHALL NOT list `fields`

### Requirement: The answer to a request has no declared type

`Response` SHALL NOT be part of the type vocabulary. The answer the host `send`s back SHALL be the value the
story continues with, unwrapped and unconverted.

#### Scenario: a story parses an answer

- **WHEN** a step receives the host's answer — an object or a mapping — and reads it with `getattr` or
  `getitem`
- **THEN** the read SHALL match the host's own object, with no kernel-side conversion

### Requirement: A host registers type names and their constructors

The kernel SHALL keep a registry of type names to constructors, with the operations `register_type(name,
constructor)`, `unregister_type(name)` and `type_names()`. A registration SHALL require a non-empty name
and a callable, and SHALL replace an earlier registration of the same name. `type_names()` SHALL report
every name a step may declare — the host's registrations and the built-in names — sorted.

The registry SHALL be process-wide host state and SHALL NOT be carried by the bundle: a story references a
type by name only, so the bundle stays library-independent data. A registration SHALL win over a built-in
name of the same spelling.

#### Scenario: A host registers a name

- **WHEN** a host calls `register_type("Article", Article)` with a dataclass
- **THEN** a step whose `type` is `"Article"` SHALL find that constructor, and `type_names()` SHALL contain
  `"Article"`

#### Scenario: A registration is replaced

- **WHEN** the same name is registered twice
- **THEN** the second constructor SHALL be the one used, and `unregister_type(name)` SHALL remove only
  that host registration

#### Scenario: A name is not registrable

- **WHEN** `register_type` is called with an empty name or a non-callable constructor
- **THEN** it SHALL raise `ValueError` and the registry SHALL stay unchanged

### Requirement: A step product is built from its declared type at the boundary

At the step boundary the kernel SHALL build the `type` the step declared from the product the step
produced: a dictionary product SHALL become `Cls(**payload)`, a list product `Cls(*items)`, and any other
product SHALL be handed to the constructor as it is. The registry SHALL be consulted at that boundary, not
at compile time, because a story bundle compiles without a host.

The **product SHALL continue as JSON**: the constructor is a validator, not a container. A constructor
that answers JSON built from the product (a `dict`, or a dataclass whose fields are exactly the payload)
SHALL determine the product; an answer that is not JSON (an object, a handle) SHALL be refused by the
exit packing rule at that same step (`UP2-E2003`).

#### Scenario: A registered dataclass validates a product

- **WHEN** a step's field map produces `{"url": "u", "title": "t"}` and its `type` is a registered
  `Article` dataclass with those fields
- **THEN** the step SHALL produce that same JSON dictionary, and no `Article` instance SHALL appear in the
  run's products or its exit product

#### Scenario: A list product is built from its items

- **WHEN** a step's product is a list `["a", "b"]` and its `type` is registered as `Cls(*items)`
- **THEN** the constructor SHALL be called as `Cls("a", "b")`, and the product SHALL remain the list

#### Scenario: A product that is not JSON still fails

- **WHEN** a step's product is a host object and its `type` is registered
- **THEN** the run SHALL fail with `UP2-E2003` at that step

### Requirement: An unregistered type name fails at that step

A step whose `type` is neither a built-in name nor registered SHALL fail at the step that declares it with
`UP2-E1011`, whose diagnostic SHALL name the declared type, SHALL list the names that are registered, and
SHALL point at that step.

#### Scenario: A name no host registered

- **WHEN** a step declares `"type": "NoticeList"` and no host registered that name
- **THEN** the run SHALL fail with `UP2-E1011` at that step's pointer, naming `"NoticeList"`

#### Scenario: The allowed names are reported

- **WHEN** `UP2-E1011` is raised
- **THEN** the diagnostic SHALL carry the sorted registered names as its allowed values

### Requirement: A constructor that raises is a coded failure of that step

A constructor that raises SHALL fail the run at the step that declared the type, with the new code
`UP2-E2019`, and the diagnostic's `reason` SHALL keep the constructor's own exception text. The step's
JSON Pointer SHALL be the pointer of the diagnostic.

#### Scenario: A dataclass rejects a missing field

- **WHEN** a step's product lacks a key the registered constructor requires
- **THEN** the run SHALL fail with `UP2-E2019` at that step, and `reason` SHALL contain the constructor's
  own message (for example `missing 1 required positional argument: 'title'`)

#### Scenario: A nested record is rejected

- **WHEN** a registered container type is handed a record whose shape it refuses
- **THEN** the run SHALL fail with `UP2-E2019` at that step, and no later step SHALL run

#### Scenario: A scalar-shaped type is validated

- **WHEN** a step's product is a scalar and its `type` is registered
- **THEN** the constructor SHALL receive that scalar, and a constructor that refuses it SHALL fail with
  `UP2-E2019`

#### Scenario: A constructor that answers an object

- **WHEN** a registered constructor answers a value that cannot be serialized
- **THEN** the run SHALL fail with `UP2-E2003` at that same step, and no object SHALL appear in the
  products or the exit

### Requirement: The evaluation scope carries the run's materialization cache

The evaluation scope SHALL carry the materialization cache of the run it belongs to, and it SHALL make
that cache available to the operators it evaluates. A scope created for a nested evaluation SHALL share
its parent's cache, so an operator invoked at any depth of one run reaches the same cache. Creating a
scope SHALL NOT itself materialize anything, and a scope that never evaluates a text-consuming operator
SHALL hold no artifact.

#### Scenario: An operator reaches the run's cache

- **WHEN** an operator is evaluated through a scope of a run
- **THEN** it SHALL be able to materialize its source through that run's cache

#### Scenario: A nested scope shares the parent's cache

- **WHEN** a nested evaluation creates a child scope and materializes a document its parent's step
  already materialized
- **THEN** the child SHALL hit the parent's entry and no second artifact SHALL be built

#### Scenario: A scope without materialization

- **WHEN** a scope is created and only non-materializing actions are evaluated through it
- **THEN** the run's cache SHALL hold no artifact and account no materialized bytes

### Requirement: An outcome is a value or a failure

The kernel SHALL expose exactly two outcomes: `Ok`, carrying a value, and `Failed`, carrying a code, a
reason and a fix. There SHALL be no third outcome for "not there", no action-level declaration that
accepts such an outcome, and no sentinel substituted for a value before an operator runs.

A query that matches nothing SHALL be `Ok` carrying the **empty value of its shape** (the per-action
mapping is specified in `dsl-operators`). A reference path that cannot be walked SHALL be `Failed` with
`UP2-E2001`. A failure SHALL stop the chain and reach the caller carrying the code and reason of the
stage that failed.

#### Scenario: a selector that matched nothing

- **WHEN** a chain runs `["css1","text","h1"]` against a document with no `h1`
- **THEN** the outcome SHALL be `Ok("")`, and the value SHALL flow to the next stage

#### Scenario: a reference that cannot be walked

- **WHEN** a chain reads `$locals.nope`
- **THEN** the outcome SHALL be `Failed` with `UP2-E2001`

#### Scenario: a failed stage stops the chain

- **WHEN** the first stage fails and a second stage follows it
- **THEN** the second stage SHALL NOT be evaluated

### Requirement: A non-finite float is not a JSON value

The JSON value domain SHALL exclude `inf`, `-inf` and `nan`. A product that carries one — at the top
level or nested in a list or a dict — MUST be refused by the exit packing rule with `UP2-E2003` at the
step that produced it, and a host-registered function or a sandboxed snippet that returns one MUST be
reported with `UP2-E2009`. Chain text MUST NOT carry one: loading it MUST fail with `UP2-E1004`, and
serializing a chain that holds one MUST fail with the same code, because a chain is JSON data.

The rule applies at the boundary only: a computation MAY still answer a non-finite float internally,
because Python's arithmetic does.

#### Scenario: A product is non-finite

- **WHEN** a step's product is `float("inf")`
- **THEN** the run fails with `UP2-E2003` at that step, and the diagnostic names the value

#### Scenario: A non-finite value nested in a product

- **WHEN** a step's product is `{"ratio": float("nan")}`
- **THEN** the run fails with `UP2-E2003` at that step

#### Scenario: A finite float remains a value

- **WHEN** a step's product is `1.5`
- **THEN** the run succeeds and the value is exported unchanged

#### Scenario: Chain text carries a non-JSON constant

- **WHEN** the chain text is `[["const",Infinity]]` and it is loaded
- **THEN** loading fails with `UP2-E1004`, whose fix line says a chain is JSON data

#### Scenario: Serializing a chain that holds one

- **WHEN** `dumps` is called on a stage whose parameter is `float("inf")`
- **THEN** it raises an `Up2Error` with code `UP2-E1004` instead of emitting `Infinity`

#### Scenario: The computation itself still answers it

- **WHEN** `["py", "float", ""]` is evaluated on `"1e999"`
- **THEN** evaluation succeeds and answers `inf`; only the boundary refuses it

### Requirement: Chain text is read and written as strict JSON

Every conversion between a chain and text SHALL be strict: writing MUST pass `allow_nan=False`, and
reading MUST reject the non-JSON constants `Infinity`, `-Infinity` and `NaN`. A text that is not
valid JSON MUST fail with `UP2-E1004` and a fix line, never with a bare decoder exception, because
the same public entry point answers a coded diagnostic for every other kind of bad chain.

#### Scenario: Malformed chain text is a coded failure

- **WHEN** `loads("not json")` is called
- **THEN** it raises an `Up2Error` with code `UP2-E1004` whose message says the text is not valid JSON

#### Scenario: A non-JSON constant is still refused

- **WHEN** `loads('[["const",Infinity]]')` is called
- **THEN** it raises `UP2-E1004`, as it did before this change

#### Scenario: Writing stays strict

- **WHEN** `dumps` is called on a stage whose parameter is `float("nan")`
- **THEN** it raises `UP2-E1004` and writes no text

### Requirement: A stage is an operator, an optional action and an optional parameter

A stage SHALL be `[operator]` when the operator's single action has no required parameter,
`[operator, parameter]` for a single-action operator with a parameter, or `[operator, action]` /
`[operator, action, parameter]` for a multi-action one; slot 2 is thus the action for a multi-action
operator and the parameter for a single-action one. A trailing slot SHALL be omitted when no required
parameter remains: an omitted required parameter MUST be `UP2-E1005`, and an extra slot MUST be
`UP2-E1004`.

#### Scenario: A single-action operator writes two slots

- **WHEN** the chains are `[["json"]]` and `[["json","data.list[*].url"]]`
- **THEN** both compile, the first answering the document whole and the second the selected list

#### Scenario: A multi-action operator writes three slots

- **WHEN** the chain is `[["py","replace",["old","new"]]]`
- **THEN** it compiles: slot 2 is the action and slot 3 is the two-element parameter array

#### Scenario: An action with no parameters omits the third slot

- **WHEN** the chain is `[["py","strip"]]` and the value is `"  a  "`
- **THEN** it compiles and the result is `"a"`

#### Scenario: An optional parameter may be omitted

- **WHEN** the chains are `[["py","strip"]]` and `[["py","strip","\"'"]]` and the value is `"'a'"`
- **THEN** both compile; the first answers `"'a'"` and the second answers `"a"`

#### Scenario: An explicitly empty third slot is not a placeholder

- **WHEN** the chain is `[["py","strip",""]]` and it is compiled
- **THEN** compilation fails with `UP2-E1004`, because the slot is omitted, never written empty

#### Scenario: An extra slot is an arity error

- **WHEN** the chain is `[["json","data.url","extra"]]` and it is compiled
- **THEN** compilation fails with `UP2-E1004`, because a single-action operator takes two slots

#### Scenario: A required parameter whose slot is omitted

- **WHEN** the chain is `[["code"]]` and it is compiled
- **THEN** compilation fails with `UP2-E1005`, naming the missing source parameter

### Requirement: `$obj` names the value a stage received

A parameter MAY read `$obj`: the value the stage's own `Call` received, the same value `ctx.obj` reads.
It SHALL name the whole value and MUST NOT take a path, because it is a value rather than a scope;
`$obj.a` MUST be `UP2-E1006`. `$in` still names the story step's input and never changes per stage.
Outside a stage — a story `call` step's `args` — `$obj` MUST be `UP2-E2001`.

#### Scenario: A parameter reads the stage's value

- **WHEN** the chain is `[["py","strip"], ["py","==","$obj"]]` and the step's input is `" a "`
- **THEN** the result is `true`, because `$obj` is the stripped value the stage received — had it been
  the step's input, `"a"` would not equal `" a "`

#### Scenario: The value is the stage's, not the step's

- **WHEN** the chain is `[["py","strip"], ["py","or",["$obj","fallback"]]]` and the step's input is
  `"  "`
- **THEN** the result is `"fallback"`, because the second stage's `$obj` is the stripped text `""`, not
  the step's input `"  "` (which `$in` would name)

#### Scenario: The root takes no path

- **WHEN** the chain is `[["py","or",["$obj.title","fallback"]]]` and it is compiled
- **THEN** compilation fails with `UP2-E1006`, because `obj` names the whole value and a field is read
  with `["py","getitem","title"]` after it

#### Scenario: No stage value exists outside a stage

- **WHEN** a story `call` step's `args` carries `"$obj"` and the run reaches that step
- **THEN** it fails with `UP2-E2001`, because a `call` step's arguments are not a stage
