# Spec Delta

## MODIFIED Requirements

### Requirement: Stage shape of the `code` operator

The `code` operator SHALL be a **2-slot** stage (it declares a single action, so slot 2 is the
parameter), shaped as `["code", <non-empty source string>]`. The source text itself SHALL be the only
parameter: `inputs` is retired and MUST be rejected as an unknown parameter. The stage length MUST be
exactly 2; writing an extra slot MUST raise `UP2-E1004`.

#### Scenario: A valid chain compiles

- **WHEN** given `["code", "len(obj)"]`
- **THEN** `compile_field` returns an evaluable field chain without error

#### Scenario: Missing `src` is a parameter error

- **WHEN** given `["code"]`
- **THEN** compile time raises `UP2-E1005`, and the JSON Pointer points at the parameter slot `/0/1`
  (consistent with the whole repo: pointers go to the parameter slot, not to each leaf)

#### Scenario: An extra slot is an arity error

- **WHEN** given `["code", "1", "extra"]`
- **THEN** compile time raises `UP2-E1004`, indicating that the operator needs 2 slots

#### Scenario: The retired `inputs` object is rejected

- **WHEN** given `["code", {"src": "x + 1", "inputs": {"x": 1}}]`
- **THEN** compile time raises `UP2-E1005` at `/0/1`, and the fix line shows the accepted writing
  `["code", "x + 1"]`

### Requirement: Input binding: `obj` and `ctx`

The `code` operator SHALL **bind two fixed names**, usable with no configuration at all: `obj` = the upstream value; `ctx` = the **scope object**
(which MUST NOT be treated as a JSON dict), and MUST support attribute access `ctx.locals.<name>` and
`ctx.globals.<name>`. `ctx.locals` MUST contain **all temporary variables produced by parsing behavior in the current node**; `ctx.globals`
MUST be the story/environment-level environment (identical across nodes). A nonexistent attribute MUST raise an observable failure such as
`AttributeError`, and MUST NOT silently return an empty value.

Values in `ctx` MUST fall in the JSON value domain: `Opaque` handles (DOM/XPath nodes) and non-JSON values MUST NOT appear in
`ctx`, and excluding handles MUST NOT cause evaluation to fail (same principle as `UP2-E2003`, "handles cannot leave the chain").

There SHALL be no `inputs` parameter and no configured binding: `obj` is the upstream value, and every
other value is already reachable through `ctx.locals` / `ctx.globals` / `ctx.public`, so naming it
again would only rename an existing read. The trade is explicit: a reference was resolved at compile
time, while `ctx.locals.<name>` is a runtime attribute read that fails when the key is missing.

#### Scenario: Minimal shape (no configuration at all)

- **WHEN** the chain is `["code", "ctx.locals.n + 1"]` and `locals.n = 41`
- **THEN** the result is `42`, with no `inputs` written

#### Scenario: The upstream value is bound as `obj`

- **WHEN** the chain is `["code", "len(obj)"]` and the upstream value is `"abcd"`
- **THEN** the result is `4`

#### Scenario: `ctx.globals` reads environment-level configuration

- **WHEN** the chain is `["code", "ctx.globals.base_url"]` and `globals.base_url = "https://x/"`
- **THEN** the result is `"https://x/"`

#### Scenario: A nonexistent attribute is an observable failure

- **WHEN** the chain is `["code", "ctx.locals.nope"]`
- **THEN** evaluation fails (an `AttributeError` class of failure) rather than returning `None` or an empty string

#### Scenario: Handles do not appear in `ctx`

- **WHEN** `locals` contains a DOM/XPath node handle and the chain is `["code", "'ok'"]`
- **THEN** evaluation succeeds (the handle is excluded rather than raising)

#### Scenario: The named entry point keeps compile-time validation

- **WHEN** the chain is `["code", {"src": "x + 1", "inputs": {"x": "$locals.n"}}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at `/0/1`, because the named entry point is retired: the
  source is the parameter itself, and the value it held is read as `ctx.locals.n` inside the source

#### Scenario: An upstream handle is rejected

- **WHEN** the upstream value is a DOM/XPath node handle
- **THEN** evaluation returns `Failed` with code `UP2-E2003` (handles do not enter the sandbox)

### Requirement: In-chain code and host functions share one parameter convention

The `code` operator and the `udf` operator SHALL add no new shape to the chain syntax: both are called
with the upstream value as the only positional argument, and the sandbox mounts the `py` allowlist
functions so a snippet calls them positionally with no `import`. `udf` SHALL take no chain parameter
and SHALL NOT inject `ctx`: the host function receives the upstream value as its only positional
argument (`f(value)`), or no argument when it declares none (`f()`), and a function that requires a
second argument MUST be a compile error (`UP2-E1005`) whose fix says to bind it at registration or to
take a payload object. Configuration a host function needs SHALL travel in a payload the chain builds
with `ctx` (`["ctx","dict",…]` followed by `["udf",name]`), so a host function stays a pure value
transformation and writing the scope remains the chain's job through `ctx.set`.

Inside the sandbox, `ctx` SHALL remain readable and **read-only** with respect to the scope in v1
(assignments inside the sandbox do not propagate back), so writing to the scope MUST go through
explicit operators such as the chain's `ctx.set`.

#### Scenario: A `udf` that declares `ctx` receives the scope

- **WHEN** the host-registered function's only parameter is named `ctx` and the chain is `["udf", "f"]`
  with the upstream value `"a"`
- **THEN** it receives `"a"`: `ctx` is an ordinary parameter name now, so the engine scope is not
  injected and the stage stays a unary value transformation

#### Scenario: Existing functions that do not declare `ctx` keep working

- **WHEN** the host-registered function looks like `def f(value)` or `lambda value: …` and the chain is
  `["udf", "f"]`
- **THEN** the call succeeds as before, with `value` bound to the upstream value and no parameter written
  in the stage

#### Scenario: A configured call is a payload plus a call

- **WHEN** the chain is `[["ctx","dict",{"value":"obj","lang":"globals.lang"}], ["udf","translate"]]`
- **THEN** the host function receives one object holding the stage's value and the language, because
  configuration is a payload and the call stays unary

#### Scenario: A function that needs a second argument

- **WHEN** the registered function requires a second positional parameter and the chain is `["udf","f"]`
- **THEN** compilation fails with `UP2-E1005`, whose fix says to bind the argument at registration or to
  take a payload object

#### Scenario: Assignments to `ctx` inside the sandbox do not propagate back

- **WHEN** the snippet executes `ctx.locals.added = 7` and then ends, and the chain's next stage reads `$locals.added`
- **THEN** that name does not exist (in-sandbox assignment only affects the copy inside the snippet); writing into the scope MUST use the chain's `ctx.set`

#### Scenario: `ctx` is a reserved name

- **WHEN** the chain writes `["udf", "f", {"ctx": 1}]` and it is compiled
- **THEN** compilation fails with `UP2-E1004`, because `udf` takes two slots: the name is not a reserved
  parameter but an ordinary one, and the stage has no parameter slot to pass it in
