# code-execution Specification

## Purpose

Let a chain author (a human or an LLM agent) write a small piece of processing logic inside a chain, without handing the "execute arbitrary code" capability to chain data: the code runs inside a language-level sandbox, can only see the JSON values we explicitly pass in, and by default exists only when the host explicitly installs and configures it. This capability also specifies the **unified parameter convention between in-chain code and host functions** — both take the upstream value as the first parameter, both pass configuration through optional named parameters, and both receive the same read-only scope snapshot; the only difference is "where the code is and whose privilege it runs with".

## Requirements

### Requirement: Stage shape of the `code` operator

The `code` operator SHALL be a **2-slot** stage (it has a single behavior, so per the unified slot order it writes no action slot), shaped as
`["code", {"src": <non-empty string>, "inputs": <optional named object>}]`. `src` MUST be required and a non-empty string;
`inputs` MUST be a "name → value" named object whose values may be literals or references. The stage length MUST be exactly 2;
writing an extra slot MUST raise `UP2-E1004`.

#### Scenario: A valid chain compiles

- **WHEN** given `["code", {"src": "len(obj)"}]`
- **THEN** `compile_field` returns an evaluable field chain without error

#### Scenario: Missing `src` is a parameter error

- **WHEN** given `["code", {"inputs": {"x": 1}}]`
- **THEN** compile time raises `UP2-E1005`, and the JSON Pointer points at the parameter slot `/0/1` (consistent with the whole repo: pointers go to the parameter slot, not to each leaf)

#### Scenario: An extra slot is an arity error

- **WHEN** given `["code", {"src": "1"}, "extra"]`
- **THEN** compile time raises `UP2-E1004`, indicating that the operator needs 2 slots

### Requirement: Input binding: `obj` and `ctx`

The `code` operator SHALL **bind two fixed parameters**, usable with no configuration at all: `obj` = the upstream value; `ctx` = the **scope object**
(which MUST NOT be treated as a JSON dict), and MUST support attribute access `ctx.locals.<name>` and
`ctx.globals.<name>`. `ctx.locals` MUST contain **all temporary variables produced by parsing behavior in the current node**; `ctx.globals`
MUST be the story/environment-level environment (identical across nodes). A nonexistent attribute MUST raise an observable failure such as
`AttributeError`, and MUST NOT silently return an empty value.

Values in `ctx` MUST fall in the JSON value domain: `Opaque` handles (DOM/XPath nodes) and non-JSON values MUST NOT appear in
`ctx`, and excluding handles MUST NOT cause evaluation to fail (same principle as `UP2-E2003`, "handles cannot leave the chain").

The operator MAY accept an optional `inputs` named object whose values may be literals or references; the point of `inputs` is **naming plus compile-time
reference validation**: references inside it MUST be resolved at compile time, and a dangling reference MUST fail at compile time.

#### Scenario: Minimal shape (no configuration at all)

- **WHEN** the chain is `["code", {"src": "ctx.locals.n + 1"}]` and `locals.n = 41`
- **THEN** the result is `42`, with no `inputs` written

#### Scenario: The upstream value is bound as `obj`

- **WHEN** the chain is `["code", {"src": "len(obj)"}]` and the upstream value is `"abcd"`
- **THEN** the result is `4`

#### Scenario: `ctx.globals` reads environment-level configuration

- **WHEN** the chain is `["code", {"src": "ctx.globals.base_url"}]` and `globals.base_url = "https://x/"`
- **THEN** the result is `"https://x/"`

#### Scenario: A nonexistent attribute is an observable failure

- **WHEN** the chain is `["code", {"src": "ctx.locals.nope"}]`
- **THEN** evaluation fails (an `AttributeError` class of failure) rather than returning `None` or an empty string

#### Scenario: Handles do not appear in `ctx`

- **WHEN** `locals` contains a DOM/XPath node handle and the chain is `["code", {"src": "'ok'"}]`
- **THEN** evaluation succeeds (the handle is excluded rather than raising)

#### Scenario: The named entry point keeps compile-time validation

- **WHEN** the chain is `["code", {"src": "x + 1", "inputs": {"x": "$locals.n"}}]` and `locals.n = 41`
- **THEN** the result is `42`; and when the reference is written `$nope.n`, **compile time** raises `UP2-E1006` with the Pointer at parameter slot `/0/1`

#### Scenario: An upstream handle is rejected

- **WHEN** the upstream value is a DOM/XPath node handle
- **THEN** evaluation returns `Failed` with code `UP2-E2003` (handles do not enter the sandbox)

### Requirement: Allowlist functions directly available inside the sandbox

The `code` sandbox namespace SHALL preload a set of **engine-owned pure functions** (same source as the `py` allowlist, JSON in JSON out,
no IO), so that a snippet can call them directly with no `import` (e.g. `normalize_space(obj)`, `strip_tags(obj)`). The preloaded
functions MUST NOT include any function with file/environment/network/process capability. Every call of these functions MUST count against the host
round-trip allowance, and the implementation MUST NOT configure that allowance as `0` (otherwise no preloaded function could ever be called).

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

Sandbox execution SHALL be constrained by host-configured limits: memory ceiling, per-feed execution duration, per-request timeout, suspension count,
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

### Requirement: Tri-state and error code mapping

An exception raised by sandbox code itself SHALL map to `Failed` (`UP2-E2017`, reason containing the exception's first line); a triggered limit SHALL map to
`UP2-E2016`; a worker crash SHALL map to `UP2-E2099`; the return value MUST fall in the JSON value domain, otherwise it MUST map to
`UP2-E2009` (that code's wording SHALL be generalized from "udf returned…" to "operator returned…").

#### Scenario: Sandbox code raises

- **WHEN** sandbox code executes `1 / 0`
- **THEN** evaluation returns `Failed` with code `UP2-E2017` and the reason contains `ZeroDivisionError`

#### Scenario: The return value is not serializable

- **WHEN** sandbox code returns `{1, 2}` (a set)
- **THEN** evaluation returns `Failed` with code `UP2-E2009`

### Requirement: In-chain code and host functions share one parameter convention

The `code` operator and the `udf` operator SHALL adopt the same parameter convention, adding no new shape to the chain syntax:

- The upstream value SHALL be the **first parameter** (`obj` in `code`, the first positional parameter in `udf`);
- The **named configuration** of one call SHALL be passed as a named object (`code` uses the optional `inputs`, `udf` uses kwargs);
- Both SHALL receive the **scope object** `ctx` with **identical read semantics** (`ctx.locals.<name>` /
  `ctx.globals.<name>`): in `code` it is preloaded by the sandbox namespace; in `udf` it is obtained by the function declaring a `ctx` parameter
  (the implementation injects by function signature, and does not inject when undeclared, keeping existing single-parameter functions usable);
- Write capability differs by "where the code runs" and can be stated in the docs: `udf` is host code, receives the engine scope object, and reads and writes naturally;
  `code` runs inside the sandbox, receives an isomorphic sandbox-side object, and is **read-only** with respect to the scope in v1 (assignments inside the sandbox do not propagate back), so writing to the scope MUST go
  through explicit operators such as the chain's `ctx.set`;
- `ctx` SHALL be a reserved parameter name: passing it as a named parameter in a chain MUST fail at compile time.

#### Scenario: A `udf` that declares `ctx` receives the scope

- **WHEN** the host-registered function's signature contains a `ctx` parameter and the chain is `["udf", "my_fn", {"k": 1}]`
- **THEN** the function can be called, and the `ctx` it receives is isomorphic to the `ctx` in `code` (the same `ctx.locals` /
  `ctx.globals` read pattern)

#### Scenario: Existing functions that do not declare `ctx` keep working

- **WHEN** the host-registered function looks like `def f(value)` or `lambda value: …` and the chain is `["udf", "f", ""]`
- **THEN** the call succeeds as before (the implementation neither injects nor errors because the function does not declare `ctx`)

#### Scenario: Assignments to `ctx` inside the sandbox do not propagate back

- **WHEN** the snippet executes `ctx.locals.added = 7` and then ends, and the chain's next stage reads `$locals.added`
- **THEN** that name does not exist (in-sandbox assignment only affects the copy inside the snippet); writing into the scope MUST use the chain's `ctx.set`

#### Scenario: `ctx` is a reserved name

- **WHEN** the chain writes `["udf", "f", {"ctx": 1}]`
- **THEN** compile time raises an error (reserved parameter name) rather than passing it as an ordinary parameter

### Requirement: Conformance audit and conformance declaration

The operator SHALL declare the `(code, run)` pair in the registry and have a visible coverage declaration in the test source;
`up2 conformance --check` MUST exit 0, and the declared `(operator, action)` total MUST be equal to the number the registry declares.

#### Scenario: The audit passes with the right pair count

- **WHEN** running `up2 conformance --check`
- **THEN** the exit code is 0 and the output shows the declared pair count equal to the covered pair count

#### Scenario: Capability self-description exposes dependencies

- **WHEN** running `up2 ops --json`
- **THEN** the `requires` of the `code` entry contains the sandbox runtime dependency and `available` reflects the actual installation state
