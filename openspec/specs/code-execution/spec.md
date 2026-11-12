# code-execution Specification

## Purpose

Let a chain author (a human or an LLM agent) write a small piece of processing logic inside a chain, without handing the "execute arbitrary code" capability to chain data: the code runs inside a language-level sandbox, can only see the JSON values we explicitly pass in, and by default exists only when the host explicitly installs and configures it. This capability also specifies the **unified parameter convention between in-chain code and host functions** — both take the upstream value as the first parameter, both pass configuration through optional named parameters, and both receive the same read-only scope snapshot; the only difference is "where the code is and whose privilege it runs with".

## Requirements

### Requirement: Stage shape of the `code` operator

The `code` operator SHALL be a **2-slot** stage (it declares a single action, so slot 2 is the
parameter), shaped as `["code", <non-empty source string>]`. The source text itself SHALL be the only
parameter: `inputs` is retired, and a parameter object MUST be rejected because the parameter is the
source string. The stage length MUST be exactly 2; writing an extra slot MUST raise `UP2-E1004`.

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
- **THEN** compile time raises `UP2-E1005` at `/0/1/src`, and the fix line shows the accepted writing
  `["code", "x + 1"]`

### Requirement: The sandbox binds `obj` and `ctx`

The `code` operator SHALL bind two fixed names with no configuration: `obj` is the upstream value and `ctx` is the scope object, which MUST NOT be treated as a JSON dict and MUST support attribute reads `ctx.locals.<name>` and `ctx.globals.<name>`. `ctx.locals` MUST hold the current node's field values and `ctx.globals` the story-level environment. A missing attribute MUST raise an observable `AttributeError`, never return an empty value.

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

### Requirement: Values in `ctx` are JSON-only, and `inputs` is retired

Values in `ctx` MUST fall in the JSON value domain: `Opaque` handles (DOM/XPath nodes) and non-JSON values MUST NOT appear, and excluding a handle MUST NOT cause evaluation to fail (same principle as `UP2-E2003`). There SHALL be no `inputs` parameter and no configured binding: a value is read as `ctx.locals.<name>` at runtime, and naming it again would only rename an existing read.

#### Scenario: Handles do not appear in `ctx`

- **WHEN** `locals` contains a DOM/XPath node handle and the chain is `["code", "'ok'"]`
- **THEN** evaluation succeeds (the handle is excluded rather than raising)

#### Scenario: The named entry point keeps compile-time validation

- **WHEN** the chain is `["code", {"src": "x + 1", "inputs": {"x": "$locals.n"}}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at `/0/1/src`, because the named entry point is retired:
  the source is the parameter itself, and the value it held is read as `ctx.locals.n` inside the source

#### Scenario: An upstream handle is rejected

- **WHEN** the upstream value is a DOM/XPath node handle
- **THEN** evaluation returns `Failed` with code `UP2-E2003` (handles do not enter the sandbox)

### Requirement: Allowlist functions directly available inside the sandbox

The `code` sandbox namespace SHALL preload the engine-owned pure functions of the `py` allowlist (JSON in, JSON out, no IO), so a snippet calls `normalize_space(obj)` with no `import`. It MUST NOT preload any function with file, environment, network or process capability. A preloaded call MUST count against the host round-trip allowance, which MUST NOT be configured as `0` (otherwise no preloaded function could run).

#### Scenario: Allowlist functions need no import

- **WHEN** the chain is `["code", {"src": "normalize_space(obj)"}]` and the upstream value is `"  a   b  "`
- **THEN** the result is `"a b"`

#### Scenario: Preloaded functions are unusable when the round-trip allowance is 0 (counterexample pinning the default)

- **WHEN** the implementation configures the host round-trip allowance as `0` and the snippet calls any preloaded function
- **THEN** evaluation fails with a limit-exceeded class of error (so the default MUST be a positive number)

#### Scenario: A standard-library subset inside the sandbox can be imported directly

- **WHEN** the chain is `["code", {"src": "import json, re\njson.dumps(re.findall(r'\\d+', obj))"}]`
- **THEN** the result is the JSON text of that regex result (no extra engine preloading needed)

### Requirement: Dependency gate and unavailable by default

The `code` operator SHALL depend on the optional extra `uniparser2[code]`. When that extra is not installed, the operator MUST be unavailable at compile time and raise
`UP2-E1107`, and the diagnostic MUST give the install command; `up2 ops` MUST mark the operator as unavailable. A default installation
(including `uniparser2[all]`) MUST NOT include that extra.

#### Scenario: A missing dependency is blocked at compile time

- **WHEN** compiling `["code", {"src": "1"}]` while the extra is not installed
- **THEN** `UP2-E1107` is raised and the hint contains `uniparser2[code]`

#### Scenario: Capability self-description marks it unavailable

- **WHEN** running `up2 ops` while the extra is not installed
- **THEN** the output marks `code` as "unavailable" and lists the missing dependency

### Requirement: Sandbox isolation boundary

Code inside the sandbox MUST NOT be able to read or write the host filesystem, read environment variables, access the network, or create subprocesses; the implementation SHALL NOT
mount any host capability into the sandbox (no external functions, no directory mounts, no os callback, no host object wrapping), passing only JSON values.
These prohibitions MUST surface as **observable failures** (exception/non-zero exit), and MUST NOT silently return an empty value.

#### Scenario: The filesystem is unreachable

- **WHEN** sandbox code executes `open('C:/Windows/win.ini').read()`
- **THEN** evaluation fails, and the reason indicates a permission/absent class of rejection rather than returning an empty string

#### Scenario: Environment variables are unreachable

- **WHEN** sandbox code executes `import os; os.getenv('USERNAME')`
- **THEN** evaluation fails (the operation is not supported inside the sandbox)

#### Scenario: Network and imports are restricted

- **WHEN** sandbox code executes `import socket`
- **THEN** evaluation fails with a module-not-found error

#### Scenario: The classic escape chain does not work

- **WHEN** sandbox code executes `''.__class__.__mro__[1].__subclasses__()`
- **THEN** evaluation fails (that attribute does not exist in the sandbox language)

### Requirement: Resource limits are decided by the host

Sandbox execution SHALL be constrained by host-configured limits: memory ceiling, per-feed execution duration, per-request timeout, host round-trip count,
and recursion depth. Chain data MUST NOT be able to override or loosen any limit. The host SHALL be able to specify the worker binary path explicitly, and the default implementation
MUST NOT resolve that binary via `PATH` alone.

#### Scenario: An infinite loop is terminated by the feed time limit

- **WHEN** sandbox code executes `while True: pass` with a feed time limit of 0.1 seconds
- **THEN** evaluation returns `Failed` with code `UP2-E2016`

#### Scenario: Over-allocation is terminated by the memory limit

- **WHEN** sandbox code allocates an object far beyond the memory limit
- **THEN** evaluation returns `Failed` with code `UP2-E2016`

#### Scenario: The chain cannot loosen limits

- **WHEN** the chain passes `code` a parameter named after a limit (e.g. `{"src": "1", "max_memory": 1 << 40}`)
- **THEN** compile time raises `UP2-E1005` (unknown parameter) rather than taking effect

### Requirement: Deterministic execution

Under the default configuration the sandbox SHALL freeze the clock, fix the timezone, disable sleep, and seed the random number generator. The same chain plus the same input, executed repeatedly,
MUST produce a **byte-identical** JSON result. When the host explicitly switches back to following host clock/entropy, the docs MUST declare that this configuration forfeits the
cross-machine replay guarantee.

#### Scenario: Repeated execution gives identical results

- **WHEN** in-chain code uses `datetime.now()`, `random.random()`, and `time.monotonic()` in sequence and the same chain runs twice
- **THEN** both outputs are byte-identical

#### Scenario: The host can explicitly give up determinism

- **WHEN** the host configures the clock policy to follow the host
- **THEN** two runs of the same chain may differ, and that trade-off has been declared in the design draft and the operator docs

### Requirement: Outcomes and error code mapping

An exception raised by sandbox code itself SHALL map to `Failed` (`UP2-E2017`, reason containing the exception's first line); a triggered limit SHALL map to
`UP2-E2016`; a worker crash SHALL map to `UP2-E2099`; the return value MUST fall in the JSON value domain, otherwise it MUST map to
`UP2-E2009` (that code's wording SHALL be generalized from "udf returned…" to "operator returned…").

#### Scenario: Sandbox code raises

- **WHEN** sandbox code executes `1 / 0`
- **THEN** evaluation returns `Failed` with code `UP2-E2017` and the reason contains `ZeroDivisionError`

#### Scenario: The return value is not serializable

- **WHEN** sandbox code returns `{1, 2}` (a set)
- **THEN** evaluation returns `Failed` with code `UP2-E2009`

### Requirement: In-chain code and host functions add no new chain shape

The `code` and `udf` operators SHALL add no new chain shape. `code` is `["code", <source>]`. `udf` is `["udf", <name>]`, passing the upstream value as one argument, or `["udf", <name>, <form>]`, where `*` spreads a list, `**` spreads a mapping and any other value is one explicit argument. A signature the form cannot call MUST fail with `UP2-E1005`. Neither operator SHALL inject `ctx`; configuration travels in a `["ctx","dict",…]` payload.

#### Scenario: A `udf` that declares `ctx` receives the upstream value

- **WHEN** the host-registered function's only parameter is named `ctx` and the chain is `["udf", "f"]`
  with the upstream value `"a"`
- **THEN** it receives `"a"`: `ctx` is an ordinary parameter name, so the engine scope is not
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

#### Scenario: The call forms are explicit

- **WHEN** the chain is `["udf","f","*"]` with the upstream value `[1, 2]`, or `["udf","f","**"]` with
  `{"a": 1}`, or `["udf","f",42]`
- **THEN** the calls are `f(1, 2)`, `f(a=1)` and `f(42)` respectively

#### Scenario: A function that needs a second argument

- **WHEN** the registered function requires a second positional parameter and the chain is `["udf","f"]`
- **THEN** compilation fails with `UP2-E1005`, whose fix says to bind the argument at registration or to
  use the `*` or `**` form

### Requirement: The sandbox scope is read-only

Inside the sandbox, `ctx` SHALL stay readable and read-only with respect to the run's scope: an assignment such as `ctx.locals.added = 7` affects only the snippet's copy and MUST NOT propagate back. Writing the scope SHALL go through `ctx.set` in the chain.

#### Scenario: Assignments to `ctx` inside the sandbox do not propagate back

- **WHEN** the snippet executes `ctx.locals.added = 7` and then ends, and the chain's next stage reads `$locals.added`
- **THEN** that name does not exist (in-sandbox assignment only affects the copy inside the snippet); writing into the scope MUST use the chain's `ctx.set`

### Requirement: Conformance audit and conformance declaration

The operator SHALL declare the `(code, run)` pair in the registry and have a visible coverage declaration in the test source;
`up2 conformance --check` MUST exit 0, and the declared `(operator, action)` total MUST be equal to the number the registry declares.

#### Scenario: The audit passes with the right pair count

- **WHEN** running `up2 conformance --check`
- **THEN** the exit code is 0 and the output shows the declared pair count equal to the covered pair count

#### Scenario: Capability self-description exposes dependencies

- **WHEN** running `up2 ops --json`
- **THEN** the `requires` of the `code` entry contains the sandbox runtime dependency and `available` reflects the actual installation state
