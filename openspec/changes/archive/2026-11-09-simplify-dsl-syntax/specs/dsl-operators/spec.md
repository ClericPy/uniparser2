# Spec Delta

## MODIFIED Requirements

### Requirement: A scalar action parameter is validated at compile time

When an action declares a parameter that only accepts a scalar (a string or an integer), a chain that
gives that parameter a JSON container MUST be rejected at compile time with `UP2-E1005`, reporting the
position of that parameter and a fix line that shows the accepted writing. An action that declares
**two or more fixed parameters** SHALL take one **positional array** whose length is exactly the
declared arity — `["py", "replace", ["old", "new"]]` — and never a named object: a parameter that is
missing, unknown or of the wrong length MUST be reported with `UP2-E1005` at `/0/2`, or at the array
index `/0/2/<index>` the offending parameter occupies. A **literal of another type** MUST be rejected
the same way, and a string whose content the runtime parses MUST be parsed at compile time, so a value
the run would deterministically reject is never deferred to evaluation. This applies to every operator,
`py`'s function table included: the selector family's selector, `re`'s pattern, `ctx`'s path and
`json`'s expression already behave this way, and `py`'s scalar parameters MUST behave the same way
instead of failing during evaluation.

A parameter that accepts any JSON value MUST keep accepting containers: a container written for such a
parameter is a value, not a malformed parameter binding. An array that is itself a value stays a value
(`["py", "in", [200, 301]]`), because the action's declaration decides whether the slot holds a
parameter list or a value, never the shape alone. An **object** is reserved for a data map (`each`'s
field map, `ctx.dict`, `xpath`'s namespace map), so an object written where a scalar or a positional
parameter is expected MUST be rejected, naming the key. A parameter whose value the runtime **coerces**
rather than rejects MUST keep accepting that value.

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

#### Scenario: A maxsplit that is not an integer

- **WHEN** the chain is `["py", "split", {"sep": ",", "maxsplit": "x"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at `/0/2`, because `split` takes its separator bare and a
  named object is not a positional array

#### Scenario: The no-limit spellings of maxsplit keep working

- **WHEN** the chain is `["py", "split", ","]` and it is evaluated on `a,b,c`
- **THEN** the result is `["a", "b", "c"]`, because a split without a limit is now the only spelling

#### Scenario: A value the runtime coerces is not rejected

- **WHEN** the chain is `["py", "join", 42]` and it is evaluated on `["a", "b"]`
- **THEN** compilation succeeds and the result is `"a42b"`, because the separator is coerced

#### Scenario: The same mistake on an operator that already validates it

- **WHEN** the chain is `["css1", "text", {"selector": "h1"}]` and it is compiled
- **THEN** compilation still fails with `UP2-E1005` at `/0/2`

#### Scenario: A container value for a parameter that accepts any type

- **WHEN** the chain is `[["py", "or", [{"a": 1}, "fallback"]]]` and the value is `""`
- **THEN** compilation succeeds and the result is the container `{"a": 1}`

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

### Requirement: The operator self-description states the parameter-slot shape

For every action, the capability self-description printed by `up2 ops` MUST state which writing the
action's parameter slot takes — the value itself (`value`), one positional array holding the action's
fixed parameters in declaration order (`array`), or no parameter at all (`none`) — and the
machine-readable and human views MUST use the same three tokens and agree on the value. `array` means
the slot holds exactly one array whose length is the action's declared arity, never a named object. The
shape is decided by the number of parameters the action still has to fill, so a parameter that the
action slot itself already provides does not count towards it. The reported shape MUST agree with what
compilation accepts for that action.

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

### Requirement: The ctx surface names its readable and writable roots

The `ctx` operator's readable roots SHALL be `globals`, `locals`, `public` and `obj`, and its writable
roots SHALL be `locals` and `public`. A `ctx.get` / `ctx.dict` / `ctx.list` path whose root is none of
them SHALL be `UP2-E1005` naming the accepted roots, and a `ctx.set` / `ctx.del` path outside `locals`
and `public` SHALL be `UP2-E1015`. `globals` is read-only because a chain's constants must not change
mid-run (`01` §4); `public` is writable because it is the run's own notes, not chain data
(`chain-iteration`, "A run carries a `public` scope"). `obj` is the whole value the stage received,
read-only, and it is a value rather than a scope: it takes no path, so `ctx.get "obj.x"` SHALL be
`UP2-E1005` and `ctx.set obj` / `ctx.del obj` SHALL be `UP2-E1015`. Reading a field of the stage's
value is `["py","getitem",…]` after `ctx.get "obj"`. `fields` SHALL NOT be accepted by either: it was a
second name for `locals` and is retired (`chain-iteration`, "A reference path may walk an object").

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

#### Scenario: the value the stage received

- **WHEN** the chain is `[["py","strip"], ["ctx","get","obj"]]` and the input is `"  a  "`
- **THEN** the result SHALL be `"a"`, because `obj` names the value the second stage received — the
  stripped text, not the chain's input

#### Scenario: a path on the stage's value

- **WHEN** the chain is `["ctx","get","obj.x"]` and it is compiled
- **THEN** compilation SHALL fail with `UP2-E1005`, because `obj` names the whole value and a field is
  read with `["py","getitem","x"]` after `ctx.get "obj"`

### Requirement: A query that matches nothing yields the empty value of its shape

When a query action finds nothing it SHALL return `Ok` carrying the empty value of the shape that action
produces, and SHALL NOT raise. The mapping SHALL be:

| Action family | No-match result |
|---|---|
| text accessors (`css` / `css1` `text`, `@<attribute>`, `html`, `outer`) | `""` |
| list accessors (`css` / `css1` `nodes`, `xpath` `text` / `nodes`, `re` `findall`) | `[]` |
| element-handle accessors (`css` / `css1` / `xpath` `self`) | `None` |
| `json` query | `None` |
| `re` `search` | `""` |
| `py.first` / `py.last` over an empty list | `None` |

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

## REMOVED Requirements

### Requirement: The `py` allowlist has no identity action

**Reason**: `py.const` is now the identity/literal stage (`["py","const",x]`), so the old prohibition is
reversed: a constant is written as an action of the `py` table rather than as a separate operator.

**Migration**: use `["py","const",x]` for a literal, and a whole-chain reference for identity
(`chain-iteration`, "A chain may be a whole-chain reference").
