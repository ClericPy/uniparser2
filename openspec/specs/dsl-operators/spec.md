# dsl-operators Specification

## Purpose
The operator layer's chain-facing contract: which writing an action's parameter slot takes, what each
action validates about its own parameters before a chain runs, and how the operator registry
self-describes both to a chain writer.

## Requirements

### Requirement: A scalar action parameter is validated at compile time

When an action declares a parameter that only accepts a scalar (a string or an integer), a chain that
gives that parameter a JSON container MUST be rejected at compile time with `UP2-E1005`, reporting the
position of that parameter and a fix line that shows the accepted writing. This applies to every
operator, `py`'s function table included: the selector family's selector, `re`'s pattern, `ctx`'s path
and `json`'s expression already behave this way, and `py`'s scalar parameters MUST behave the same way
instead of failing during evaluation.

A parameter that accepts any JSON value MUST keep accepting containers: a container written for such a
parameter is a value, not a malformed parameter binding.

#### Scenario: A named object written for a single-parameter `py` function

- **WHEN** the chain is `["py", "urljoin", {"base": "https://example.com/news/"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the `base` parameter, and the fix line shows the
  accepted writing `["py", "urljoin", "https://example.com/news/"]`

#### Scenario: A container written for a scalar parameter of `py`

- **WHEN** the chain is `["py", "slice", {"spec": "0:4"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the `spec` parameter

#### Scenario: The same mistake on an operator that already validates it

- **WHEN** the chain is `["css1", "text", {"selector": "h1"}]` and it is compiled
- **THEN** compilation still fails with `UP2-E1005` at the `selector` parameter

#### Scenario: A container value for a parameter that accepts any type

- **WHEN** the chain is `[["ctx", "get", "locals.nope"], ["py", "default", {"a": 1}]]` and it is
  evaluated
- **THEN** compilation succeeds and the result is the container `{"a": 1}`

#### Scenario: The named form of a multi-parameter action is unaffected

- **WHEN** the chain is `["py", "split", {"sep": ",", "maxsplit": 1}]` and it is evaluated on `a,b,c`
- **THEN** compilation succeeds and the result is `["a", "b,c"]`

### Requirement: The operator self-description states the parameter-slot shape

For every action, the capability self-description printed by `up2 ops` MUST state which writing the
action's parameter slot takes — the value itself (`value`), a named object with a positional array
equally accepted (`named`), or no parameter at all (`none`) — and the machine-readable and human views
MUST use the same three tokens and agree on the value. The shape is decided by the number of
parameters the action still has to fill, so a parameter that the action slot itself already provides
does not count towards it. The reported shape MUST agree with what compilation accepts for that
action.

#### Scenario: A single-parameter action

- **WHEN** `up2 ops` reports `py`'s `slice` action
- **THEN** its parameter-slot shape is `value`

#### Scenario: A multi-parameter action

- **WHEN** `up2 ops` reports `re`'s `group` action
- **THEN** its parameter-slot shape is `named`

#### Scenario: An action whose parameter is provided by the action slot

- **WHEN** `up2 ops` reports the `css` / `css1` attribute accessor `@<attribute>`, whose `attr`
  parameter is provided by the accessor itself
- **THEN** its parameter-slot shape is `value`, because only the selector is left to fill

#### Scenario: An action with no parameters

- **WHEN** `up2 ops` reports `py`'s `strip` action
- **THEN** its parameter-slot shape is `none`

#### Scenario: An open action space reports the shape compilation sees

- **WHEN** `up2 ops` reports the `udf` extension point, whose action space is declared by the host and
  is modelled as a single parameter on the compilation side
- **THEN** its parameter-slot shape is `value` (the writing that compiles), and the operator's own
  evaluation still requires that value to be the host function's keyword-argument object

#### Scenario: The two views agree

- **WHEN** the same action is reported once by `up2 ops` and once by `up2 ops --json`
- **THEN** both report the same parameter-slot shape token

### Requirement: A parameter whose value is a field map is validated recursively at compile time

An action MAY declare a parameter whose value is a **field map**: an object mapping a field name to a
chain, rather than a scalar or an arbitrary JSON value. For such a parameter, a value that is not an
object MUST be rejected at compile time with `UP2-E1005` at that parameter, and the fix line MUST show
the accepted writing. A map with **no** fields MUST be rejected with `UP2-E1005`, because every element
would then yield an empty dictionary; a field name that is empty or contains `.` MUST also be rejected
with `UP2-E1005`, because no reference path can address such a key — both fix lines MUST name the
offending key and show a legal one. A map MUST hold at most `MAX_FIELDS_PER_MAP` fields, and exceeding
that bound MUST be rejected with `UP2-E1012` at compile time, naming the count and the bound.

Every value of the map MUST be compiled like a top-level chain, so an unknown operator, an unknown
action, a wrong stage length or a malformed parameter inside a sub-chain is reported at compile time with
a pointer that reaches the offending stage inside that sub-chain. Containers that appear where a chain is
expected are NOT values: the rule that a container written for a parameter accepting any JSON value is a
value MUST NOT be applied to a field map. The parameter-slot shape reported by `up2 ops` remains decided
by the existing rule (the number of parameters the action still has to fill).

#### Scenario: A field map compiles and evaluates

- **WHEN** the chain is `[["each", {"title": [["py","strip",""]]}]]` and the value is `[" a "]`
- **THEN** compilation succeeds and the result is `[{"title": "a"}]`

#### Scenario: A value that is not an object

- **WHEN** the chain is `["each", "title"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the parameter

#### Scenario: An empty field map

- **WHEN** the chain is `[["each", {}]]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the parameter, and the fix line shows a map with one
  field

#### Scenario: A field name no reference can address

- **WHEN** the chain is `[["each", {"_a.b": [["py","strip",""]]}]]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at that key, and the fix line names it and shows a legal
  name

#### Scenario: A field map over the field bound

- **WHEN** a field map with 257 fields is compiled
- **THEN** compilation fails with `UP2-E1012`, naming the count and `MAX_FIELDS_PER_MAP`

#### Scenario: An unknown operator inside a sub-chain

- **WHEN** the chain is `[["each", {"title": [["nope","text",""]]}]]` and it is compiled
- **THEN** compilation fails with `UP2-E1001`, and the pointer reaches the stage inside the field map

#### Scenario: A wrong stage length inside a sub-chain

- **WHEN** the chain is `[["each", {"title": [["py"]]}]]` and it is compiled
- **THEN** compilation fails with `UP2-E1004`, and the pointer reaches the stage inside the field map

#### Scenario: The parameter-slot shape of a field-map parameter

- **WHEN** `up2 ops` reports the `each` operator
- **THEN** its parameter-slot shape is `value`, because only the field map is left to fill

### Requirement: `py.getitem` reads a subscript

The `py` operator SHALL provide `getitem` as its only subscript action, and `py.get` SHALL be absent from
the registry. The parameter SHALL be named `at`, SHALL be `ref_or_literal` and required, and the action
SHALL apply Python's subscript semantics — a sequence by index, a mapping by key, a str by character —
with no type coercion.

#### Scenario: a list index

- **WHEN** the value is a list and the action is `["py","getitem",0]`
- **THEN** it SHALL return the first element

#### Scenario: a dict key

- **WHEN** the value is a mapping and the action is `["py","getitem","title"]`
- **THEN** it SHALL return the value stored under that key

#### Scenario: a computed key

- **WHEN** the parameter is a reference, such as `["py","getitem","$globals.key"]`
- **THEN** the reference SHALL be resolved and used as the key

#### Scenario: a key or an index that is not there

- **WHEN** the mapping has no such key, or the index is out of range
- **THEN** it SHALL fail with `UP2-E2018`, and `reason` SHALL begin with the exception class and name the
  key or index, such as `KeyError: 'text' — the dict has no key 'text'`

#### Scenario: a parameter of the wrong type

- **WHEN** the value is a list and the parameter is the string `"0"`
- **THEN** it SHALL fail with `UP2-E2002` and SHALL NOT convert the parameter to an integer

#### Scenario: the catalogue

- **WHEN** `up2 ops --json` is asked for the `py` action list
- **THEN** `getitem` SHALL be present and `get` SHALL NOT

### Requirement: The `py` allowlist has no identity action

The `py` function table SHALL NOT contain an `id` action. Identity SHALL be written as a whole-chain
reference (`chain-iteration`, "A chain may be a whole-chain reference"), so a chain that passes its own
input through writes the reference instead of a stage, and `up2 ops` MUST NOT list `id` among `py`'s
actions.

#### Scenario: The identity stage is rejected

- **WHEN** the chain is `[["py","id",""]]` and it is compiled
- **THEN** compilation SHALL fail with `UP2-E1003`, listing the allowlisted function names

#### Scenario: The catalogue no longer offers it

- **WHEN** `up2 ops` reports the `py` operator
- **THEN** its action list SHALL NOT contain `id`

### Requirement: A text-consuming operator materializes through the run's cache

Every operator that must turn text into structure — `css` / `css1` (HTML), `xpath` (XML) and `json`
(JSON text) — SHALL obtain that structure from the run's materialization cache, keyed by its own target
format and the source text, instead of building one structure per stage. The operator SHALL behave
identically whether the structure was freshly materialized or came from the cache, and it SHALL NOT
depend on the cache being present: a chain evaluated outside a run SHALL still materialize on demand.

#### Scenario: Two stages over one document

- **WHEN** two stages of one run select from the same document text
- **THEN** the document SHALL be materialized once, and both stages SHALL produce the values they
  produce without a cache

#### Scenario: A format an operator does not own is not reused

- **WHEN** a chain selects from a document as HTML and another stage queries the same text as XML
- **THEN** each SHALL materialize the structure of its own format, and neither SHALL be served the
  other's artifact

#### Scenario: Evaluation without a run

- **WHEN** a single field chain is evaluated outside any run
- **THEN** each consuming stage SHALL still materialize what it needs, with no error

### Requirement: An operator never mutates a cached structure

An operator whose work would alter the materialized structure SHALL apply that work to a copy of its
own, so a second consumer of the same source sees the structure as materialized. This holds for every
consuming operator, not only for the ones whose pruning is visible today.

#### Scenario: Pruning leaves the cached document alone

- **WHEN** one stage prunes nodes from a document and a later stage selects from the same document
- **THEN** the later stage SHALL select from the unpruned document

#### Scenario: A node a stage handed on

- **WHEN** a stage hands out a node of a materialized document and a later stage reads that node
- **THEN** the node SHALL resolve against the document it came from, unchanged

### Requirement: The ctx surface names one writable root

The `ctx` operator's readable roots SHALL be `globals` and `locals`, and its writable root SHALL be
`locals` alone. A `ctx.get` / `ctx.map` path whose root is neither SHALL be `UP2-E1005` naming the
accepted roots, and a `ctx.set` / `ctx.del` path outside `locals` SHALL be `UP2-E1015`. `fields` SHALL NOT
be accepted by either: it was a second name for `locals` and is retired (`chain-iteration`, "A reference
path may walk an object").

#### Scenario: a write to the retired root

- **WHEN** the chain is `["ctx","set","fields._tmp"]` and it is compiled
- **THEN** compilation SHALL fail with `UP2-E1015`, and the accepted prefixes SHALL be `locals` alone

#### Scenario: a read of the retired root

- **WHEN** the chain is `["ctx","get","fields.title"]` and it is compiled
- **THEN** compilation SHALL fail with `UP2-E1005`, listing `globals` and `locals` as the readable roots

#### Scenario: the writable root still works

- **WHEN** the chain is `[["ctx","set","locals._tmp"], ["ctx","get","locals._tmp"]]` and the input is `7`
- **THEN** the result SHALL be `7`, because `locals` is the scope a write lands in

### Requirement: A query that matches nothing yields the empty value of its shape

When a query action finds nothing it SHALL return `Ok` carrying the empty value of the shape that action
produces, and SHALL NOT raise. The mapping SHALL be:

| Action family | No-match result |
|---|---|
| text accessors (`css` / `css1` `text`, `@<attribute>`, `html`, `outer`) | `""` |
| list accessors (`css` / `css1` `nodes`, `xpath` `text` / `nodes`, `re` `findall`) | `[]` |
| element-handle accessors (`css` / `css1` / `xpath` `self`) | `None` |
| `json` query | `None` |
| `re` `search` / `group` | `""` |
| `py.first` / `py.last` over an empty list | `None` |
| `py.parse_time` over empty text | `""` |

`css exists` and `css1 exists` answer `False` for a selector that matches nothing; that is a boolean and
is unchanged.

#### Scenario: a text accessor that matched nothing

- **WHEN** the chain is `[["css1","text","h1"]]` and the document has no `h1`
- **THEN** the outcome SHALL be `Ok("")`

#### Scenario: a list accessor that matched nothing

- **WHEN** the chain is `[["css","nodes","li"]]` and the document has no `li`
- **THEN** the outcome SHALL be `Ok([])`

#### Scenario: an element handle that matched nothing

- **WHEN** the chain is `[["css1","self","div.missing"]]`
- **THEN** the outcome SHALL be `Ok(None)`

#### Scenario: a regex that matched nothing

- **WHEN** the chain is `[["re","search","\\d+"]]` and the input has no digits
- **THEN** the outcome SHALL be `Ok("")`

#### Scenario: a JSON query that matched nothing

- **WHEN** the chain is `[["json","data.nope"]]`
- **THEN** the outcome SHALL be `Ok(None)`

### Requirement: The scope actions name the shape they produce

The `ctx` operator SHALL provide `dict` and `list` as separate actions instead of one polymorphic `map`:
`ctx.dict` SHALL take an object mapping a name to a bare scope path and produce an object of those
values; `ctx.list` SHALL take an array of bare scope paths and produce a list of those values, in order.
The action name SHALL state the result shape, so a reader does not have to inspect the parameter to know
what the stage yields.

#### Scenario: A named object from several paths

- **WHEN** the chain is `[["ctx","dict",{"a":"locals.x","b":"locals.y"}]]`
- **THEN** the outcome SHALL be `Ok({"a": <value of locals.x>, "b": <value of locals.y>})`

#### Scenario: A list from several paths

- **WHEN** the chain is `[["ctx","list",["locals.x","locals.y"]]]`
- **THEN** the outcome SHALL be `Ok([<value of locals.x>, <value of locals.y>])`

#### Scenario: The polymorphic action is gone

- **WHEN** a chain writes `["ctx","map",…]`
- **THEN** compilation SHALL fail with `UP2-E1002`, listing the legal actions

### Requirement: The `py` allowlist turns a mapping into key/value pairs

The `py` operator SHALL provide an `items` action that takes a mapping and produces `[[key, value], …]`
in the mapping's own order, with values limited to JSON. It SHALL take no parameter. Applied to a value
that is not a mapping it SHALL fail with the operator's input-type code rather than converting the value.

#### Scenario: A mapping becomes pairs

- **WHEN** the chain is `[["const",{"a":1,"b":2}], ["py","items",""]]`
- **THEN** the outcome SHALL be `Ok([["a",1],["b",2]])`

#### Scenario: The pairs feed each

- **WHEN** the chain is `[["const",{"a":1}], ["py","items",""], ["each",{"k":[["py","getitem",0]],"v":[["py","getitem",1]]}]]`
- **THEN** the outcome SHALL be `Ok([{"k":"a","v":1}])`

#### Scenario: A non-mapping is refused

- **WHEN** the chain is `[["const",[1,2]], ["py","items",""]]`
- **THEN** the outcome SHALL be `Failed` with the operator's input-type code

### Requirement: A conversion failure describes its input, not a fallback

When a `py` conversion action (`str`, `int`, `float`, `bool`, `list`, `from_json`) fails, its `fix` text
SHALL state the input the action expects and point at the upstream stage that produced the value. It
SHALL NOT recommend another operator, and in particular SHALL NOT present a fallback as the remedy for a
failure.

#### Scenario: A conversion failure names what was expected

- **WHEN** the chain is `[["py","int",""]]` and the input is `"not-a-number"`
- **THEN** the `fix` SHALL describe the accepted input and the upstream stage, and SHALL NOT name another
  operator as a fallback
