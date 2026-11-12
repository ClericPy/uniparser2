# dsl-operators Specification

## Purpose
The operator layer's chain-facing contract: which writing an action's parameter slot takes, what each
action validates about its own parameters before a chain runs, and how the operator registry
self-describes both to a chain writer.

## Requirements

### Requirement: A scalar action parameter is validated at compile time

When an action declares a scalar parameter (a string or an integer), a chain that gives it a JSON
container MUST be rejected at compile time with `UP2-E1005` at that parameter, with a fix line showing
the accepted writing. A literal of another type, and a string the runtime parses but would reject,
MUST fail the same way. `py`'s scalar parameters follow this rule too.

#### Scenario: A named object written for a single-parameter `py` function

- **WHEN** the chain is `["py", "urljoin", {"base": "https://example.com/news/"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at `/0/2`, and the fix line shows the accepted writing
  `["py", "urljoin", "https://example.com/news/"]`

#### Scenario: A container written for a scalar parameter of `py`

- **WHEN** the chain is `["py", "slice", {"spec": "0:4"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at `/0/2`

#### Scenario: A literal of the wrong type

- **WHEN** the chain is `["py", "urljoin", 42]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at `/0/2`, and the fix line is not empty

#### Scenario: A slice notation that cannot be parsed

- **WHEN** the chain is `["py", "slice", "bogus"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at `/0/2`

#### Scenario: The same mistake on an operator that already validates it

- **WHEN** the chain is `["css1", "text", {"selector": "h1"}]` and it is compiled
- **THEN** compilation still fails with `UP2-E1005` at `/0/2`

### Requirement: Fixed parameters are one positional array

An action with two or more fixed parameters SHALL take one **positional array** whose length is exactly
the declared arity, never a named object. A missing, unknown or wrong-length parameter MUST be
`UP2-E1005` at `/0/2` or at the array index `/0/2/<index>` it occupies. An object is reserved for a
data-map parameter (`each`'s field map, `ctx.dict`, xpath's namespace map), so a named object where a
positional array belongs is rejected.

#### Scenario: A maxsplit that is not an integer

- **WHEN** the chain is `["py", "split", {"sep": ",", "maxsplit": "x"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at `/0/2`, because `split` takes its separator bare and a
  named object is not a positional array

#### Scenario: The no-limit spellings of maxsplit keep working

- **WHEN** the chain is `["py", "split", ","]` and it is evaluated on `a,b,c`
- **THEN** the result is `["a", "b", "c"]`, because a split without a limit is now the only spelling

#### Scenario: The named form of a multi-parameter action is unaffected

- **WHEN** the chain is `["xpath", "text", ["//dc:creator", {"dc": "https://purl.org/dc/elements/1.1/"}]]`
  and it is compiled
- **THEN** compilation succeeds, because the namespace map is a data map: a named object is still
  accepted where a data map is the value, even though the parameter list itself is positional

#### Scenario: A multi-parameter action takes a positional array

- **WHEN** the chain is `["py", "replace", ["old", "new"]]` and it is evaluated on `"old old"`
- **THEN** compilation succeeds and the result is `"new new"`

#### Scenario: A positional array of the wrong length

- **WHEN** the chain is `["py", "replace", ["old"]]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at `/0/2`, because the action declares two parameters and
  the array holds one

#### Scenario: The retired maxsplit key is rejected

- **WHEN** the chain is `["py", "split", {"sep": ",", "maxsplit": ""}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at `/0/2`, because `maxsplit` is retired and the no-limit
  spelling is `["py", "split", ","]`

### Requirement: A parameter that accepts any JSON value keeps containers

A parameter that accepts any JSON value MUST keep accepting containers: a container is a value, not a
malformed parameter binding. An array that is itself a value stays a value (`["py","in",[200,301]]`).
A parameter the runtime coerces rather than rejects MUST keep accepting the value.

#### Scenario: A container value for a parameter that accepts any type

- **WHEN** the chain is `[["py", "or", [{"a": 1}, "fallback"]]]` and the value is `""`
- **THEN** compilation succeeds and the result is the container `{"a": 1}`

#### Scenario: A value the runtime coerces is not rejected

- **WHEN** the chain is `["py", "join", 42]` and it is evaluated on `["a", "b"]`
- **THEN** compilation succeeds and the result is `"a42b"`, because the separator is coerced

### Requirement: The operator self-description states the parameter-slot shape

For every action, `up2 ops` MUST state the parameter-slot shape: `value` (the value itself), `array`
(one positional array of the declared parameters) or `none`. The machine-readable and human views
MUST use the same tokens. The shape is decided by the parameters the action still has to fill, so a
parameter the action slot provides does not count, and it MUST agree with what compilation accepts.

#### Scenario: A single-parameter action

- **WHEN** `up2 ops` reports `py`'s `slice` action
- **THEN** its parameter-slot shape is `value`

#### Scenario: A multi-parameter action

- **WHEN** `up2 ops` reports `re`'s `search` action, which declares a pattern and an optional group
- **THEN** its parameter-slot shape is `array`

#### Scenario: An action whose parameter is provided by the action slot

- **WHEN** `up2 ops` reports the `css` / `css1` attribute accessor `@<attribute>`, whose `attr`
  parameter is provided by the accessor itself
- **THEN** its parameter-slot shape is `value`, because only the selector is left to fill

#### Scenario: An action with no parameters

- **WHEN** `up2 ops` reports `py`'s `strip` action
- **THEN** its parameter-slot shape is `none`

#### Scenario: An open action space reports the shape compilation sees

- **WHEN** `up2 ops` reports the `udf` extension point, whose action space is declared by the host and
  whose stage takes no parameter of its own
- **THEN** its parameter-slot shape is `none`, because the upstream value is the only argument and the
  host function is called unary

#### Scenario: The two views agree

- **WHEN** the same action is reported once by `up2 ops` and once by `up2 ops --json`
- **THEN** both report the same parameter-slot shape token

### Requirement: A field-map parameter is validated at compile time

A parameter whose value is a **field map** (an object mapping a field name to a chain) MUST be an
object with at least one field. A non-object is `UP2-E1005` at the parameter with the accepted writing;
an empty map is `UP2-E1005` because every element would be an empty dictionary; a field name that is
empty or contains `.` is `UP2-E1005` because no reference path can address it. A map over
`MAX_FIELDS_PER_MAP` fields is `UP2-E1012`.

#### Scenario: A field map compiles and evaluates

- **WHEN** the chain is `[["each", {"title": [["py","strip"]]}]]` and the value is `[" a "]`
- **THEN** compilation succeeds and the result is `[{"title": "a"}]`

#### Scenario: A value that is not an object

- **WHEN** the chain is `["each", "title"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the parameter

#### Scenario: An empty field map

- **WHEN** the chain is `[["each", {}]]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the parameter, and the fix line shows a map with one
  field

#### Scenario: A field name no reference can address

- **WHEN** the chain is `[["each", {"_a.b": [["py","strip"]]}]]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at that key, and the fix line names it and shows a legal
  name

#### Scenario: A field map over the field bound

- **WHEN** a field map with 257 fields is compiled
- **THEN** compilation fails with `UP2-E1012`, naming the count and `MAX_FIELDS_PER_MAP`

### Requirement: A field-map parameter's chains are compiled recursively

Every value of a field map MUST be compiled like a top-level chain, so an unknown operator, an unknown
action, a wrong stage length or a malformed parameter inside a sub-chain reports at compile time with a
pointer that reaches the offending stage. Containers where a chain is expected are NOT values: the
"any JSON value accepts containers" rule MUST NOT apply to a field map. `up2 ops` reports the
parameter-slot shape by the usual rule.

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

### Requirement: A text-consuming operator materializes through the run's cache

Every operator that turns text into structure — `css`/`css1`, `xpath`, `json` — SHALL take it from the
run's materialization cache, keyed by target format and source text. A hit and a miss MUST be
observationally identical, and a chain evaluated outside a run SHALL still materialize on demand.

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

### Requirement: The ctx surface names its readable and writable roots

The `ctx` readable roots SHALL be `globals`, `locals`, `public` and `obj`; writable roots SHALL be
`locals` and `public`. A read path with another root is `UP2-E1005` listing the readable roots; a write
path outside the writable roots is `UP2-E1015`. `globals` is read-only because a chain's constants must
not change mid-run; `public` is the run's own notes; `fields` is retired and accepted by neither.

#### Scenario: a write to the retired root

- **WHEN** the chain is `["ctx","set","fields._tmp"]` and it is compiled
- **THEN** compilation SHALL fail with `UP2-E1015`, and the accepted prefixes SHALL be `locals` and `public`

#### Scenario: a read of the retired root

- **WHEN** the chain is `["ctx","get","fields.title"]` and it is compiled
- **THEN** compilation SHALL fail with `UP2-E1005`, listing `globals`, `locals`, `public` and `obj` as
  the readable roots

#### Scenario: the writable root still works

- **WHEN** the chain is `[["ctx","set","locals._tmp"], ["ctx","get","locals._tmp"]]` and the input is `7`
- **THEN** the result SHALL be `7`, because `locals` is the scope a write lands in

#### Scenario: the run's shared scope is writable

- **WHEN** the chain is `[["ctx","set","public.page"], ["ctx","get","public.page"]]` and the input is `7`
- **THEN** the result SHALL be `7`, because `public` is the run's shared scope (`chain-iteration`)

### Requirement: `obj` names the whole stage value

`obj` SHALL name the whole value the stage received, read-only, and it SHALL be a value rather than a
scope: it takes no path. `ctx.get "obj"` reads it, `ctx.get "obj.x"` is `UP2-E1005`, and
`ctx.set obj` / `ctx.del obj` are `UP2-E1015`. A field is read with `["py","getitem",…]` after
`ctx.get "obj"`.

#### Scenario: the value the stage received

- **WHEN** the chain is `[["py","strip"], ["ctx","get","obj"]]` and the input is `"  a  "`
- **THEN** the result SHALL be `"a"`, because `obj` names the value the second stage received — the
  stripped text, not the chain's input

#### Scenario: a path on the stage's value

- **WHEN** the chain is `["ctx","get","obj.x"]` and it is compiled
- **THEN** compilation SHALL fail with `UP2-E1005`, because `obj` names the whole value and a field is
  read with `["py","getitem","x"]` after `ctx.get "obj"`

### Requirement: A query that matches nothing is a value, not an error

When a query action finds nothing it SHALL return `Ok` carrying the empty value of the shape that
action produces, and SHALL NOT raise. `css exists` / `css1 exists` answer `False` for a selector that
matches nothing; that is a boolean and is unchanged.

#### Scenario: a text accessor that matched nothing

- **WHEN** the chain is `[["css1","text","h1"]]` and the document has no `h1`
- **THEN** the outcome SHALL be `Ok("")`

#### Scenario: a regex that matched nothing

- **WHEN** the chain is `[["re","search","\\d+"]]` and the input has no digits
- **THEN** the outcome SHALL be `Ok("")`

#### Scenario: a JSON query that matched nothing

- **WHEN** the chain is `[["json","data.nope"]]`
- **THEN** the outcome SHALL be `Ok(None)`

### Requirement: The no-match value follows the action's shape

The empty value SHALL be decided by the action family:

| Action family | No-match result |
|---|---|
| text accessors (`css` / `css1` `text`, `@<attribute>`, `html`, `outer`) | `""` |
| list accessors (`css` / `css1` `nodes`, `xpath` `text` / `nodes`, `re` `findall`) | `[]` |
| element-handle accessors (`css` / `css1` / `xpath` `self`) | `None` |
| `json` query | `None` |
| `re` `search` | `""` |
| `py.first` / `py.last` over an empty list | `None` |

#### Scenario: a list accessor that matched nothing

- **WHEN** the chain is `[["css","nodes","li"]]` and the document has no `li`
- **THEN** the outcome SHALL be `Ok([])`

#### Scenario: an element handle that matched nothing

- **WHEN** the chain is `[["css1","self","div.missing"]]`
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

- **WHEN** the chain is `[["py","const",{"a":1,"b":2}], ["py","items"]]`
- **THEN** the outcome SHALL be `Ok([["a",1],["b",2]])`

#### Scenario: The pairs feed each

- **WHEN** the chain is `[["py","const",{"a":1}], ["py","items"], ["each",{"k":[["py","getitem",0]],"v":[["py","getitem",1]]}]]`
- **THEN** the outcome SHALL be `Ok([{"k":"a","v":1}])`

#### Scenario: A non-mapping is refused

- **WHEN** the chain is `[["py","const",[1,2]], ["py","items"]]`
- **THEN** the outcome SHALL be `Failed` with the operator's input-type code

### Requirement: A conversion failure describes its input, not a fallback

When a `py` conversion action (`str`, `int`, `float`, `bool`, `list`, `from_json`) fails, its `fix` text
SHALL state the input the action expects and point at the upstream stage that produced the value. It
SHALL NOT recommend another operator, and in particular SHALL NOT present a fallback as the remedy for a
failure.

#### Scenario: A conversion failure names what was expected

- **WHEN** the chain is `[["py","int"]]` and the input is `"not-a-number"`
- **THEN** the `fix` SHALL describe the accepted input and the upstream stage, and SHALL NOT name another
  operator as a fallback

### Requirement: A literal that starts with `$` is quoted at any depth

In a parameter whose kind is `ref_or_literal`, an object with exactly one `$`-prefixed key MUST be
read as a directive at every depth, not only at the parameter slot. `{"$lit": value}` MUST produce
`value` verbatim. Any other such directive MUST be rejected at compile time with `UP2-E1005`,
naming the escape.

#### Scenario: The escape at the parameter slot

- **WHEN** the chain is `["py", "default", {"$lit": "$100"}]` and it is evaluated on `null`
- **THEN** compilation succeeds and the result is the string `"$100"`

#### Scenario: The escape inside a positional array

- **WHEN** the chain is `["py", "or", [{"$lit": "$a"}, "fallback"]]` and it is evaluated
- **THEN** compilation succeeds and the result is the string `"$a"` — not the object
  `{"$lit": "$a"}`, and not a reference read

#### Scenario: The escape inside a nested object

- **WHEN** the chain is `["py", "or", [{"a": {"$lit": "$k"}}, "fallback"]]` and the input is `null`
- **THEN** compilation succeeds and the result is the object `{"a": "$k"}`, not
  `{"a": {"$lit": "$k"}}`

#### Scenario: An unsupported directive at depth

- **WHEN** the chain is `["py", "or", [{"$price": 1}, "fallback"]]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` and the fix line shows `{"$lit": …}`

#### Scenario: A literal parameter keeps the dollar sign

- **WHEN** the chain is `["py", "replace", ["$locals.old", "X"]]` and it is evaluated on
  `"$locals.old"` repeated
- **THEN** the literal text `$locals.old` is replaced, because both of `replace`'s parameters are
  `literal`

### Requirement: The escape respects each parameter kind

The directive rule MUST apply only where a value may be either a reference or a literal. A parameter
whose kind is `literal` MUST keep a leading `$` as text, and a parameter whose kind is `ref` MUST
NOT accept a directive.

#### Scenario: A ref-only parameter refuses the escape

- **WHEN** a parameter declared `ref` receives `{"$lit": "x"}` and the chain is compiled
- **THEN** compilation fails with `UP2-E1007`, because a parameter that must be a reference has no
  literal branch

### Requirement: A `$`-prefixed mistake reports the way out

A diagnostic raised because a value was read as a reference or a path when it was meant as text MUST
state how to write the text instead. An unknown reference root (`UP2-E1006`) MUST name
`{"$lit": …}`. A `ctx` path rejected at compile time (`UP2-E1005` for a read, `UP2-E1015` for a
write) MUST say, when the path starts with `$`, that a `ctx` path is written bare.

#### Scenario: An unknown root names the escape

- **WHEN** the chain is `["py", "default", "$100"]` and it is compiled
- **THEN** compilation fails with `UP2-E1006`, and the fix line names `{"$lit": …}` alongside the
  reserved roots

#### Scenario: A `$`-prefixed ctx read path names the bare spelling

- **WHEN** the chain is `["ctx", "get", "$locals.k"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005`, and the fix line says to drop the leading `$`

#### Scenario: A `$`-prefixed ctx write path names the bare spelling

- **WHEN** the chain is `["ctx", "set", "$locals.k"]` and it is compiled
- **THEN** compilation fails with `UP2-E1015`, and the fix line says to drop the leading `$`

### Requirement: `py.sleep` blocks for a number of seconds and returns its input

`["py","sleep", seconds]` SHALL wait `seconds` seconds with `time.sleep` and answer the upstream value
unchanged. `seconds` MUST be a non-negative finite number written as a literal or a reference; a
negative or non-finite number, or a non-number, MUST fail with `UP2-E2002`. The action is the
allowlist's only blocking side effect; the engine stays synchronous and the host owns concurrency.

#### Scenario: Sleep returns the same value

- **WHEN** the chain is `[["py","const",7], ["py","sleep",0]]` and it is evaluated
- **THEN** the result is `7`

#### Scenario: A negative number is refused

- **WHEN** the stage is `["py","sleep",-1]` and it is evaluated
- **THEN** the outcome is `UP2-E2002`

#### Scenario: A non-number is refused

- **WHEN** the stage is `["py","sleep","2"]` and it is evaluated
- **THEN** the outcome is `UP2-E2002`

### Requirement: `py.filter` keeps truthy or falsy list elements

`["py","filter"]` SHALL keep the elements that are truthy; `["py","filter", true]` SHALL do the same,
and `["py","filter", false]` SHALL keep the falsy elements. The input MUST be a list; the answer MUST
be a new list in input order. The action takes no callable: complex predicates belong to a sub-chain.

#### Scenario: Truthy elements are kept

- **WHEN** the chain is `[["py","filter"]]` and the value is `[0, 1, "", "a", None]`
- **THEN** the answer is `[1, "a"]`

#### Scenario: Falsy elements are kept

- **WHEN** the chain is `[["py","filter",false]]` and the value is `[0, 1, "", "a", None]`
- **THEN** the answer is `[0, "", null]`

#### Scenario: A non-list is refused

- **WHEN** the chain is `[["py","filter"]]` and the value is `"abc"`
- **THEN** the outcome is `UP2-E2002`

### Requirement: The `node` stage calls a story node

A chain SHALL support `["node","name"]`. The operator SHALL pass the current value to the named node
as its `$in` and answer the node's product. The name MUST be a literal naming a node of the same
story, otherwise `UP2-E1016` names the available nodes. The stage MUST take exactly two slots.

#### Scenario: A node call

- **WHEN** a story has `b` and a chain stage `["node","b"]` with value `"x"`
- **THEN** `b` runs with `$in = "x"` and its product is the stage value

#### Scenario: A three-slot node stage is malformed

- **WHEN** the stage is `["node","b","extra"]` and it is compiled
- **THEN** compilation fails with `UP2-E1004`

#### Scenario: An unknown node name

- **WHEN** the stage is `["node","gone"]` and no node has that name
- **THEN** compilation fails with `UP2-E1016`

### Requirement: The `type` stage validates a chain's product

A chain MAY end with `["type","name"]`. The operator SHALL build the host-registered type from the
current value, answer the validated JSON, and reject an unregistered name with `UP2-E1011` or a raising
constructor with `UP2-E2019`. The stage MUST take exactly two slots and MUST be the last stage of its
chain; a later stage is `UP2-E1005`. A non-JSON value is `UP2-E2003`.

#### Scenario: A valid product

- **WHEN** `Article` is registered and the chain ends with `["type","Article"]`
- **THEN** the answer is the JSON the constructor approved

#### Scenario: A missing required field

- **WHEN** the registered constructor raises on the value
- **THEN** the outcome is `UP2-E2019` with the constructor's message

#### Scenario: A type stage is not last

- **WHEN** the chain is `[["type","Article"], ["py","strip"]]`
- **THEN** compilation fails with `UP2-E1005`

### Requirement: `udf` binds its argument in four forms

The third slot of a `udf` stage SHALL select the call: omitted = `f(value)`; the literal `"*"` =
`f(*value)` with a list upstream; the literal `"**"` = `f(**value)` with a mapping upstream; any other
value = `f(argument)`. The name MUST resolve from the run's udf table, otherwise `UP2-E1010`. A udf MAY
answer any value; an awaitable answer is `UP2-E2009`.

#### Scenario: The DTO form

- **WHEN** the stage is `["udf","f"]` and the value is `{"a": 1}`
- **THEN** `f` receives one argument, `{"a": 1}`

#### Scenario: The spread forms

- **WHEN** the stage is `["udf","f","*"]` and the value is `[1, 2]`
- **THEN** `f` receives two positional arguments
- **AND** when the stage is `["udf","f","**"]` and the value is `{"a": 1}`, `f` receives `a=1`

#### Scenario: The explicit argument

- **WHEN** the stage is `["udf","f","x"]`
- **THEN** `f` receives the literal `"x"`

#### Scenario: A missing function

- **WHEN** the story uses `["udf","gone"]` and the run registers no such function
- **THEN** the run fails with `UP2-E1010` naming `gone`

#### Scenario: An awaitable answer

- **WHEN** the udf answers a coroutine
- **THEN** the outcome is `UP2-E2009`
