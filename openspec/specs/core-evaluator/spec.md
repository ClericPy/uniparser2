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

#### Scenario: an object flows through the chain

- **WHEN** a node's field map reads `["py","getattr","text"]` on its input response object
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

### Requirement: A run's product SHALL be JSON

The value a run exports SHALL be JSON after the host-registered type constructor has run. A host object MAY be an input, a `udf` answer or a stage value, and it MAY flow between stages; it MUST NOT leave the run.

#### Scenario: a `udf` returns an object that reaches the exit

- **WHEN** a `udf` returns a dataclass instance and no later stage converts it
- **THEN** the run SHALL fail with `UP2-E2003`, whose message says the value cannot be exported

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
dotted path works on both a dictionary and an object. An attribute that is **callable** MUST be refused
with `UP2-E2002`, using the same message shape and fix hint `py.getattr` uses: a method is not a value,
and it could not leave the run (`UP2-E2003`) in any case.

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

### Requirement: The reserved reference roots

The reserved roots SHALL be `globals` (the story's read-only constants), `locals` (the current scope),
`public` (the run's shared scope), `in` (the current node invocation's input) and `obj` (the value the
stage received). A standalone field chain MAY declare external product roots when it is compiled
(`products=…`, `--product`).

#### Scenario: An external product root is available

- **WHEN** a standalone field chain is compiled with `products=("n1",)` and writes `$n1.url`
- **THEN** compilation succeeds and the reference reads that product's field at run time

### Requirement: An undeclared reference root is a compile error

Any root that is neither reserved nor declared MUST fail with `UP2-E1006`, listing the accepted roots.
`$fields` SHALL NOT be a root: it was a second name for `locals` and is retired, so a stage that writes
it fails at compile time like any other unknown root.

#### Scenario: the retired root

- **WHEN** a stage writes `$fields.title`
- **THEN** the reference SHALL fail with `UP2-E1006`, an unknown reference root, and the accepted roots
  SHALL NOT list `fields`

### Requirement: The answer to a request has no declared type

`Response` SHALL NOT be part of the type vocabulary. The answer the host `send`s back SHALL be the value the
story continues with, unwrapped and unconverted.

#### Scenario: a story parses an answer

- **WHEN** a node receives the host's answer — an object or a mapping — and reads it with `getattr` or
  `getitem`
- **THEN** the read SHALL match the host's own object, with no kernel-side conversion

### Requirement: A host registers type names and their constructors

The kernel SHALL keep a registry of type names to constructors, with the operations `register_type(name,
constructor)`, `unregister_type(name)` and `type_names()`. A registration MUST require a non-empty name
and a callable, SHALL replace an earlier registration of the same name, and SHALL win over a built-in name
of the same spelling. `type_names()` SHALL report the built-in names and the host's, sorted.

#### Scenario: A host registers a name

- **WHEN** a host calls `register_type("Article", Article)` with a dataclass
- **THEN** a chain whose tail is `["type","Article"]` SHALL find that constructor, and `type_names()` SHALL
  contain `"Article"`

#### Scenario: A registration is replaced

- **WHEN** the same name is registered twice
- **THEN** the second constructor SHALL be the one used, and `unregister_type(name)` SHALL remove only
  that host registration

#### Scenario: A name is not registrable

- **WHEN** `register_type` is called with an empty name or a non-callable constructor
- **THEN** it SHALL raise `ValueError` and the registry SHALL stay unchanged

### Requirement: The type registry is host state, not chain data

The registry SHALL be process-wide host state and MUST NOT be carried by the bundle: a story references a
type by name only, so the bundle stays library-independent data.

#### Scenario: The same bundle runs against different hosts

- **WHEN** one host registers `Article` and another does not, and both run the same story whose tail is
  `["type","Article"]`
- **THEN** the first SHALL validate the product and the second SHALL fail with `UP2-E1011` at that stage

### Requirement: An unregistered type name fails at that stage

A `type` stage whose name is neither a built-in name nor registered in the effective table SHALL fail
at the stage that declares it with `UP2-E1011`, whose diagnostic MUST name the declared type, list the
names that are registered, and point at that stage.

#### Scenario: A name no host registered

- **WHEN** a stage declares `["type","NoticeList"]` and neither the process-wide table nor the run's
  overlay registers that name
- **THEN** the run SHALL fail with `UP2-E1011` at that stage's pointer, naming `"NoticeList"`

#### Scenario: The allowed names are reported

- **WHEN** `UP2-E1011` is raised
- **THEN** the diagnostic SHALL carry the sorted effective names as its allowed values, including the
  run's own overlay

### Requirement: A constructor that raises is a coded failure of that stage

A constructor that raises SHALL fail the run at the stage that declared the type, with the code
`UP2-E2019`, and the diagnostic's `reason` MUST keep the constructor's own exception text. The stage's
JSON Pointer SHALL be the pointer of the diagnostic.

#### Scenario: A dataclass rejects a missing field

- **WHEN** a chain's product lacks a key the registered constructor requires
- **THEN** the run SHALL fail with `UP2-E2019` at that stage, and `reason` SHALL contain the constructor's
  own message (for example `missing 1 required positional argument: 'title'`)

#### Scenario: A nested record is rejected

- **WHEN** a registered container type is handed a record whose shape it refuses
- **THEN** the run SHALL fail with `UP2-E2019` at that stage, and no later stage SHALL run

#### Scenario: A scalar-shaped type is validated

- **WHEN** a chain's product is a scalar and its tail declares a registered type
- **THEN** the constructor SHALL receive that scalar, and a constructor that refuses it SHALL fail with
  `UP2-E2019`

#### Scenario: A constructor that answers an object

- **WHEN** a registered constructor answers a value that cannot be serialized
- **THEN** the run SHALL fail with `UP2-E2003` at that same stage, and no object SHALL appear in the
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

- **WHEN** a nested evaluation creates a child scope and materializes a document its parent's scope
  already materialized
- **THEN** the child SHALL hit the parent's entry and no second artifact SHALL be built

#### Scenario: A scope without materialization

- **WHEN** a scope is created and only non-materializing actions are evaluated through it
- **THEN** the run's cache SHALL hold no artifact and account no materialized bytes

### Requirement: An outcome is a value or a failure

The kernel SHALL expose exactly two outcomes: `Ok`, carrying a value, and `Failed`, carrying a code, a
reason and a fix. There SHALL be no third outcome for "not there", no action-level declaration that
accepts such an outcome, and no sentinel substituted for a value before an operator runs.

#### Scenario: a failed stage stops the chain

- **WHEN** the first stage fails and a second stage follows it
- **THEN** the second stage SHALL NOT be evaluated

### Requirement: A missing value is an empty value or a coded failure

A query that matches nothing SHALL be `Ok` carrying the empty value of its shape (the per-action mapping
is specified in `dsl-operators`). A reference path that cannot be walked MUST be `Failed` with
`UP2-E2001`. A failure SHALL stop the chain and reach the caller carrying the code and reason of the
stage that failed.

#### Scenario: a selector that matched nothing

- **WHEN** a chain runs `["css1","text","h1"]` against a document with no `h1`
- **THEN** the outcome SHALL be `Ok("")`, and the value SHALL flow to the next stage

#### Scenario: a reference that cannot be walked

- **WHEN** a chain reads `$locals.nope`
- **THEN** the outcome SHALL be `Failed` with `UP2-E2001`

### Requirement: A non-finite float is not a JSON value

The JSON value domain SHALL exclude `inf`, `-inf` and `nan`. A product that carries one — at the top
level or nested in a list or a dict — MUST be refused by the exit packing rule with `UP2-E2003` at the
stage that produced it, and a host function or sandboxed snippet returning one MUST be reported with
`UP2-E2009`.

#### Scenario: A product is non-finite

- **WHEN** a stage's product is `float("inf")`
- **THEN** the run fails with `UP2-E2003` at that stage, and the diagnostic names the value

#### Scenario: A non-finite value nested in a product

- **WHEN** a stage's product is `{"ratio": float("nan")}`
- **THEN** the run fails with `UP2-E2003` at that stage

#### Scenario: A finite float remains a value

- **WHEN** a stage's product is `1.5`
- **THEN** the run succeeds and the value is exported unchanged

### Requirement: Chain text cannot carry a non-finite float

Chain text MUST NOT carry a non-finite float: loading it MUST fail with `UP2-E1004`, and serializing a
chain that holds one MUST fail with the same code, because a chain is JSON data. The rule applies at the
boundary only: a computation MAY still answer a non-finite float internally.

#### Scenario: Chain text carries a non-JSON constant

- **WHEN** the chain text is `[["py","const",Infinity]]` and it is loaded
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

- **WHEN** `loads('[["py","const",Infinity]]')` is called
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

#### Scenario: A written slot for an action with no parameters is an error

- **WHEN** the chain is `[["py","len",""]]` and it is compiled
- **THEN** compilation fails with `UP2-E1004`, because the action has nothing left to configure and the
  slot must be omitted, never written empty

#### Scenario: An extra slot is an arity error

- **WHEN** the chain is `[["json","data.url","extra"]]` and it is compiled
- **THEN** compilation fails with `UP2-E1004`, because a single-action operator takes two slots

#### Scenario: A required parameter whose slot is omitted

- **WHEN** the chain is `[["code"]]` and it is compiled
- **THEN** compilation fails with `UP2-E1005`, naming the missing source parameter

### Requirement: `$obj` names the value a stage received

A parameter MAY read `$obj`: the value the stage's own `Call` received, the same value `ctx.obj` reads.
It SHALL name the whole value and MUST NOT take a path, because it is a value rather than a scope;
`$obj.a` MUST be `UP2-E1006`. `$in` names the current node invocation's input and never changes per
stage. A read where no stage value is set MUST fail with `UP2-E2001`.

#### Scenario: A parameter reads the stage's value

- **WHEN** the chain is `[["py","strip"], ["py","==","$obj"]]` and the node's input is `" a "`
- **THEN** the result is `true`, because `$obj` is the stripped value the stage received — had it been
  the node's input, `"a"` would not equal `" a "`

#### Scenario: The value is the stage's, not the node's input

- **WHEN** the chain is `[["py","strip"], ["py","or",["$obj","fallback"]]]` and the node's input is
  `"  "`
- **THEN** the result is `"fallback"`, because the second stage's `$obj` is the stripped text `""`, not
  the node's input `"  "` (which `$in` would name)

#### Scenario: The root takes no path

- **WHEN** the chain is `[["py","or",["$obj.title","fallback"]]]` and it is compiled
- **THEN** compilation fails with `UP2-E1006`, because `obj` names the whole value and a field is read
  with `["py","getitem","title"]` after it

#### Scenario: No stage value exists outside a stage

- **WHEN** a caller resolves `"$obj"` through a scope that carries no stage value
- **THEN** it fails with `UP2-E2001`, because there is no value to name

### Requirement: A chain's value is built from its declared type at any stage

At a `["type", name]` stage the kernel SHALL build the declared type from the current value: a
dictionary value SHALL become `Cls(**payload)`, a list value `Cls(*items)`, and any other value SHALL
be handed to the constructor as it is. The stage MAY appear anywhere in a chain; a later stage SHALL
receive the **constructed value**, which is a host object for a container type. The registry MUST be
consulted when the stage runs, not at compile time, because a story compiles without a host.

#### Scenario: A registered dataclass builds a product

- **WHEN** a node's field map produces `{"url": "u", "title": "t"}` and its chain ends with
  `["type","Article"]`
- **THEN** the stage SHALL answer an `Article` instance whose fields are those two values

#### Scenario: A list product is built from its items

- **WHEN** a chain's value is a list `["a", "b"]` and it declares a type registered as `Cls(*items)`
- **THEN** the constructor SHALL be called as `Cls("a", "b")`, and the stage SHALL answer its result

#### Scenario: A later stage reads the constructed value

- **WHEN** the chain is `[["type","Article"], ["py","getattr","title"]]`
- **THEN** `py.getattr` SHALL read `title` from the `Article` instance the stage built

### Requirement: The declared type is constructed; the value flows

The constructor SHALL be a **constructor**, not a validator: whatever it answers is what the chain
carries on, so a JSON-shaped answer flows as JSON and a container answer flows as a host object. The
stage MUST NOT substitute the value it was handed for the value the constructor answered. A non-JSON
value at the **exit** is refused by the packing rule there (`UP2-E2003`), which is the only place JSON
is required.

#### Scenario: A container answer flows as an object

- **WHEN** a chain declares a registered dataclass and a later stage reads an attribute of the result
- **THEN** the later stage SHALL receive the instance, not the mapping it was built from

#### Scenario: A non-JSON exit is refused at the exit

- **WHEN** the entry node's product is a constructed instance
- **THEN** `run` SHALL fail with `UP2-E2003` at the entry node
