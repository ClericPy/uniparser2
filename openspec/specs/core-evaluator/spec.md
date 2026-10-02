# core-evaluator Specification

## Purpose

The value domain: what a run may carry, what may leave it, and what a missing or failed value means.

## Requirements

### Requirement: Missing and failed have fixed outcomes

The kernel SHALL NOT offer a settlement policy: `Policy`, the missing and error strategies, the `policy`
parameter of `eval_field`, the `policy` block of a story and the CLI's `--on-missing` / `--on-error` SHALL
be absent, and `UP2-E2015` SHALL be retired without reusing its number.

A missing value SHALL mean "not there": in a field map the key SHALL be absent from the product, in a
batch the item SHALL be skipped, and **at a step boundary the step SHALL be skipped** — no product is
recorded for it and the exit collects nothing for it — with no empty string and no null invented. A
failed stage SHALL always raise, carrying its code and reason.

#### Scenario: a selector that never matched

- **WHEN** a field's chain ends in a selector that matched nothing
- **THEN** the field SHALL be absent from the step's product

#### Scenario: a step whose chain product is missing

- **WHEN** a step's chain product is a missing value
- **THEN** the step SHALL be skipped: no product SHALL be recorded, and if it is the exit step its
  product SHALL NOT appear in the run's output — never as `null`

#### Scenario: a receiving step that produces nothing

- **WHEN** the step a suspension names as `next` produces a missing value
- **THEN** the run SHALL continue at the step after it, because there is no product to hand on

#### Scenario: a value the type requires

- **WHEN** a host-registered type constructor is handed a product that lacks a required key
- **THEN** the constructor SHALL raise and the run SHALL fail at that step

#### Scenario: a failing stage

- **WHEN** any stage fails
- **THEN** the run SHALL fail with that stage's code and pointer, and no configuration SHALL degrade it

#### Scenario: tolerating one absence

- **WHEN** an author wants a fallback for a value that may be missing
- **THEN** the fallback SHALL be expressed at the action level (`py.default` / `py.or`), not by policy

### Requirement: A value that flows may be a host object

A run SHALL accept a host object as a value (a response object, a DOM handle, anything an action returns),
using the same mechanism that already carries an `Opaque` handle. Such an object SHALL NOT be copied,
wrapped or converted on the way in.

#### Scenario: an object flows through a step

- **WHEN** a step's input is a response object and its field map reads `["py","getattr","text"]`
- **THEN** the chain SHALL read that object's own `text` attribute, unchanged

#### Scenario: an object reaches the exit

- **WHEN** a run's exit product would contain a host object
- **THEN** the run SHALL fail with `UP2-E2003`

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
