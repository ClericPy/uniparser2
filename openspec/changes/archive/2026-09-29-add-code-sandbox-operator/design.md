# Design

## Context

Motivation is in `proposal.md`. Existing constraints that shape this design:

- **The chain is data**: `core/` has no third-party dependencies, no IO, no `eval`/`exec`/`__import__`; `py` is a closed allowlist of 31 pure functions; `udf` can only reference functions the host **previously registered** (the chain holds only function names). This is this repo's replacement for the old v3 "`udf` arbitrary source + `__class__.__mro__` escape".
- **Fully synchronous, pure-function kernel**: there is no `async`; `compile_field` touches no IO; IO and optional dependencies appear only in `ops/` (precedent: `htmldom`'s module-level lazy engine).
- **Bad chains fail at compile time**: unknown operators/actions, mismatched parameters, and dangling references all error during `compile_field`, with `UP2-E*` and a JSON Pointer.
- **Freezing and replay**: chains get persisted and replayed across machines, so "same chain, same input, same result" is one of the product goals.
- **This repo's spike measurements** (a throwaway spike script, not shipped; Windows + CPython 3.13): pool creation 0.8 ms; `checkout+run` median 0.72–0.84 ms; a 120,000-character string round-trips fine; three runs are byte-identical under frozen clock + fixed timezone + seeded random; `open`/`os.getenv`/`import socket`/`__import__` all fail, and `''.__class__` raises `AttributeError`; a 0.1 second feed time limit triggers at 100.038 ms, and a 64 MB memory limit triggers at 209758175 bytes; `ctx.locals.args1` attribute access works through the prelude namespace; mounting an engine pure function makes it directly callable, and `max_suspensions=0` interrupts it.

> **One deliberate deviation from the source material**: the source material Q42 settled on "keep UDF, **do not execute arbitrary code inside templates** (site-registered functions)". This change introduces a **restricted sandbox code** path, a deliberate loosening of Q42. The limits are hard-coded as: absent by default (optional extra), language-level sandbox (no file/environment/network/process operations in the VM), JSON only, limits configured explicitly item by item, and the chain itself visible (operator names are greppable). Q42's UDF shape coexists with this change's unified parameter convention; the two do not conflict.

## Goals / Non-Goals

**Goals:**

- Let a chain author write "a piece of processing logic" **without** changing host code and redeploying.
- Keep the hard promise that "a default installation has no code execution capability": the capability must **be explicitly installed and configured** by the host in order to exist.
- Make such chains **auditable** (the chain itself is visible) and **replayable** (deterministic by default).

**Non-Goals:**

- No host `eval`/`exec` API, and no folding of sandbox capability into `py`.
- Mount no host capability into the sandbox (filesystem, network, environment variables, host functions, host objects).
- No persistence/loading of sandbox snapshots (snapshot bytes are untrusted; see decision D9).
- No long-running sandbox service, remote worker, or WASM backend; no pool tuning.
- No chain-level limit configuration, and no in-UI code editor.

## Decisions

### D1. Backend is `pydantic-monty`, not a hand-written evaluator

It is a **language-level sandbox**: `import socket` / `import subprocess` **do not exist** in its VM, `open` and `os.getenv` **exist and are blocked** (measured; the rejection is Monty's own default, not a policy of this repository), and the worker subprocess only handles crash isolation — the two together are what makes this work. In the spike the classic escape chain raises `AttributeError` directly at the language level. See `docs/specs/004` §11.3 for the per-surface table.

Alternatives and trade-offs: (a) **bare `eval`** — measured that `{"__builtins__": {}}` cannot stop attribute access (`obj.__class__.__mro__[1].__subclasses__()` still reaches 231 classes), and a single Python function mixed into the allowlist is enough to recover full builtins via `__globals__` and then `import os`; rejected. (b) **a hand-written AST allowlist evaluator** — it could have the same "no attribute access" property, but that is a piece of **security-critical code we would have to audit and fuzz ourselves**, whereas Monty has a threat model document, a bounty program, and an 8.3k-star community. (c) **host registration only (A′)** — zero new dependencies, but every added piece of logic requires changing host code, which is exactly the friction this change removes (A′ remains available; it is just no longer needed as a fallback).

### D2. A standalone `code` operator, not folded into `py`

`pyops`'s docs and the design draft both state "there is no `eval`/`exec`/`import` capability here". Stuffing code capability into `py` would turn that sentence into **a conditional promise** (it stops holding under a different configuration), and an auditor could no longer judge `py` safe with one sentence. A standalone operator makes the risk surface separately greppable, separately disablable, and separately documentable.

### D3. A 2-slot stage; the parameters are just `obj` and `ctx`, and `ctx` is an object

Per the unified slot order, an operator with a single behavior writes no action slot (same shape as `json`/`const`): `["code", {"src": …}]`.
**Two fixed parameter names, usable with zero configuration**:

- `obj` = the upstream value
- `ctx` = the **scope object** (not a JSON dict): accessed by attribute as `ctx.locals.args1` / `ctx.globals.base`.
  Consistent with the source material (the source material Q40): `ctx.globals` = story-level environment (identical across nodes), `ctx.locals` = every
  local that is not persisted; this repo automatically puts "all temporary variables produced by parsing behavior in the current node" into `locals`, and the chain can additionally
  `ctx.set` / `ctx.get` / `ctx.del` manually (Q41's three verbs: get / assign / call function).

**Implementation (measured)**: the sandbox-side `ctx` is built by a **prelude** (sandbox-side code) — define a namespace class, recursively convert dicts to objects; `setattr` is available inside the sandbox. Measured: `ctx.locals.args1 + 1` → `42`, iterating `ctx.locals.tags` ✓, accessing a nonexistent attribute → `AttributeError` (loud). The prelude is **sandbox-side code**, with zero host round-trips.

**Write semantics (v1 is read-only, determined by measurement)**: the sandbox can write `ctx.locals.x = 1` (it is just a copy inside the snippet), but that **does not propagate back** to the engine scope. The reason is that it is technically infeasible plus non-silent: Monty does not dispatch `__setattr__`, and `dir` / `vars` / `__dict__` **do not exist** (measured: all three error), so keys added inside the sandbox cannot be enumerated back, and writing back could only overwrite old keys — half a feature is worse than none. To write to the scope, use the chain's `ctx.set` / `ctx.del` (ready-made operators, visible on the chain); the `ctx.set(scope, name, val)` channel from Q41 is left as a later route, to be built when there is real demand. **This MUST be written into the operator docs**, otherwise users will think assignments in the snippet propagate out.

**Allowlist functions are directly available** (Q41's `call` verb): mount the engine's own pure functions into the sandbox namespace (`external_lookup`) so a snippet can write `normalize_space(obj)`, `strip_tags(obj)` directly, **with no import needed**. Measured: works. What is mounted is **engine-owned, already-audited, JSON-in JSON-out, no-IO** functions, not user callbacks, so Monty's threat model line "your own callbacks are the weak point" still does not apply. The cost: **each call = one host round-trip**, bounded by `max_suspensions` — measured, setting it to `0` makes mounted functions raise `suspension limit 0 exceeded` directly, so the default MUST be a sufficient positive number (see D7). When `json` / `re` / `math` / `base64` / `datetime` / `collections` / `itertools` / `functools` / `unicodedata` are needed, the sandbox can `import` them directly (Monty ships these standard-library subsets).

**Values in `ctx` are still in the JSON value domain**: handles (DOM/XPath nodes) do not appear in `ctx`, and this **does not raise an error** (same principle as `UP2-E2003`, "handles cannot leave the chain"). This too MUST be written into the docs, so that users do not think "cannot read it" is a bug.

`inputs` is an **optional** named entry point; its only reason to exist is "compile-time reference validation + shorter names in the code": `$nope.x` errors at compile time with `UP2-E1006`, while `ctx.locals.typo` can only raise a runtime `AttributeError`.

**Return value convention**: `src` is **a statement snippet**, executed with REPL semantics — **the value of the last expression is the return value**. Measured: `x = 1 + 1; x * 3` → `6`; ending on an assignment, `print(...)`, a bare comment, or an empty string → `None` (`print` output goes to the output channel, not the return value). This MUST be written into the operator docs, otherwise users will treat `print` as the return value.

### D4. The dependency gate reuses `UP2-E1107`; no new "capability not granted" code

Not installing the extra is identical to "optional dependency missing", so the existing mechanism works as-is (compile-time error + install command + `up2 ops` marking it unavailable). No environment variable switch: a process-level switch mismatches the granularity of chain-level risk, and environment variables do not enter the chain and would break cross-machine replay consistency. `uniparser2[all]` does **not** include `code`: installing everything should not incidentally grant code execution.

### D5. Mount no host capability

`feed_run` receives only `inputs` (JSON values): no `external_lookup`, no directory mounts, no `os` callback, no `ClassInstance`/`ClassType`. Monty's threat model says "your own callbacks are the weak point"; we keep that section irrelevant to this project.

### D6. Deterministic by default; the host may explicitly opt out

Default policy: frozen clock (fixed instant), fixed timezone, `sleep='zero'`, seeded random. Rationale: chains must be frozen and replayed, and once `datetime.now()`/`random` follow the host, the same chain produces different results on two machines. The cost is that `datetime.now()` is no longer "the real current time"; therefore this trade-off MUST be prominently declared in the operator docs and in `02`, and the host is allowed to explicitly switch back to following the host (switching back forfeits the replay guarantee).

### D7. Limits live only on the host side; the chain cannot loosen them

Limits are part of the host's security policy; if chain data could set them, they would not exist. **Key point: Monty's local pool sets no memory budget by default and `request_timeout` has no deadline by default** — measured, without `max_memory` an allocation of `'a' * (500 * 1024 * 1024)` **succeeds** (returns 524288000), and only with 64 MB does it raise `MemoryError: 524330797 bytes > 67108864 bytes`. So "safe" is not obtained automatically by installing the library: the implementation MUST **pin every limit explicitly** when creating the pool and on every checkout, and MUST NOT rely on upstream defaults. Conservative defaults: `max_memory` 64 MB, `max_feed_duration_secs` 0.5, `request_timeout` 5 s, `max_recursion_depth` at the runtime default; **`max_suspensions` must not be 0** — each call of a mounted allowlist function consumes one host round-trip, and measured `max_suspensions=0` makes `normalize_space(obj)` raise `suspension limit 0 exceeded` directly, so the default is a sufficient positive number (e.g. 1000), with the docs explaining the cost of "host round-trips"; the host can override via public configuration items (build the minimal API first, no config center). Passing any limit name in a chain is merely an unknown parameter ⇒ compile-time `UP2-E1005`.

### D8. Pin the worker binary path explicitly

Monty resolves the worker binary by default as "explicit path → `MONTY_BIN` → in-package runtime → `PATH`". The default implementation MUST use only the **in-package runtime** (passing the path explicitly), and allow overriding it in host configuration; it must not rely on `PATH`, avoiding "whoever is in PATH is the sandbox".

### D9. Do not use snapshots

Monty is explicit: `load_snapshot` bytes must come from a trusted producer; corrupted/forged snapshots may execute, panic, or terminate the process. Our usage is "run a short snippet to completion" and needs no pause/resume, so no snapshot capability is provided.

### D10. Do not validate sandbox code syntax at compile time

`compile_field` must stay IO-free (kernel invariant), and syntax validation can only be delegated to the sandbox runtime. Substituting CPython's `ast.parse` would produce false positives (Monty rejects `class Foo(Bar)`, generators, `match`, `del`, `async with`, and other constructs that are legal CPython at parse time). So syntax errors land at runtime: `UP2-E2017`, with reason carrying the exception's first line. This is a **deliberate narrowing** of "bad chains fail at compile time", recorded here; the mitigation is a later optional type-checking switch (Monty ships `ty`).

### D11. Error code mapping

Sandbox code raising ⇒ `UP2-E2017` (`Failed`); limit triggered ⇒ `UP2-E2016`; worker crash ⇒ `UP2-E2099`; return value outside the JSON value domain ⇒ `UP2-E2009` (that code's wording is generalized from "udf returned…" to "operator returned…"). The two new codes go into `CODES` in `core/errors.py`, and per repo rules are covered in tests.

### D12. Pool lifecycle

The sandbox pool is an IO resource and can only live in `ops/code.py`: a module-level lazy singleton (same shape as `htmldom._ENGINE`), created on first evaluation and reclaimed by the interpreter on process exit; `core/` is entirely unaware of it. Each evaluation checks out once and returns it when done (measured median ~0.8 ms).

### D13. `py` / `udf` / `code` are not merged

The three have similar mechanisms (all call a Python callable with "upstream value + named parameters"); the difference concentrates in one column of load-bearing properties:

| Operator | Where the code is | Action space | Auditable property |
|---|---|---|---|
| `py` | In the engine, already audited | **Closed** (31 named) | "This chain can do at most these 31 things" — statically checkable, portable across deployments |
| `udf` | In the host, invisible to the chain | **Open** (whatever the host registers) | "This chain depends on which functions this deployment registered" — deployment-bound |
| `code` | **In the chain** | Single behavior | "This chain contains a snippet of sandbox code" — the chain itself is visible |

**Do not fold `udf` into `py`**: `py`'s "closed allowlist" is a **statically enumerable** guarantee (conformance has 31 named pairs). After merging, `py`'s action space becomes "allowlist ∪ everything this deployment registered", so **every chain that uses `py` could become deployment-bound** (raising `UP2-E1010` on another deployment), and those 31 named pairs could only degrade to a `("*")` contract coverage. That saves under 100 lines of code and trades away a static guarantee.

**Do not fold `udf` into `code`**: they are opposite ends of the trust tier — `udf`'s code lives in the host and runs with full host privilege; `code`'s code lives in the chain and runs in a sandbox with no host capability at all. Merging would erase the core distinction of the four-layer trust model that `04` has to teach.

**But parameter shape does not follow the trust tier** (the previous design version got this wrong): the two use **one and the same** calling convention — upstream value as the first parameter, named configuration through a named object, a shared read-only `ctx` snapshot. What differs is only "where the code is and whose privilege it runs with", not "what the function looks like". This way the chain syntax gains nothing new, and the docs need only one explanation.

Alternative (rejected): collapse the three into one operator. The trust tiers must stay separate (the first two points above), and only the convention itself can be unified — and a unified convention is not the same as a merged operator.

**`code` and `udf` SHALL use exactly the same parameter convention** (`obj` + `ctx` + named configuration). The earlier conclusion is corrected on this point: `udf` already runs with full host privilege, so giving it a scope object **adds no capability**; and "what it read out" is a question that has to be answered by auditing that function itself anyway (registration implies trust). Building a second convention and one more DSL explanation for a bit of on-chain visibility is not worth it.

The same-named `ctx` **reads identically** in both places (`ctx.locals.x` / `ctx.globals.y`); the difference is only in writing: `udf` is host CPython and receives the engine's real scope object, so reads and writes both work naturally; `code` runs in the sandbox and receives an isomorphic sandbox-side object, **read-only** in v1 (the technical reason for write-back is in D3), and writing to the scope must use the chain's `ctx.set`. This difference is a direct consequence of "where the code runs"; the docs state it truthfully and do not pretend the two are the same.

Alternative (rejected): give `udf` a "declare at registration whether it wants ctx" switch — that is one more API surface; injecting `ctx` by function signature (not passing it when undeclared) keeps existing single-parameter functions usable and needs no addition to chain syntax or the registration API.

## Risks / Trade-offs

- **[New platform binary dependency (about 12 MB) and supply-chain surface]** → optional extra only; `uv.lock` pins the version; `uv export` + `pip-audit` join the dependency audit axis; CI installs it in a single job only.
- **[Young project, 1.0.0]** → pin the version; upgrades go through a separate change and must regression-test the isolation/limit cases; `docs/monty`'s limitations are the authoritative source for dialect differences.
- **[A third Python dialect (host UDFs are real CPython, the in-chain one is a subset)]** → parse-time rejection (loud rather than silent) + docs pointing at the limitations list + diagnostics carrying a traceback; optional type checking later.
- **[A frozen clock is counter-intuitive]** → prominently documented + host-overridable + trade-off recorded in the design draft.
- **[Cost of one checkout per field]** → the docs recommend "for wide documents, write the whole-page processing as a single snippet"; no batch API (YAGNI).
- **[A language-level sandbox is not OS-level isolation]** → we mount no host capability and pass only JSON, so the attack surface narrows to the interpreter itself; we do not promise resistance to vulnerabilities in other host-side components — this sentence must go into `04`.
- **[Limits do not take effect by default; security must be configured explicitly]** → the implementation **pins memory/duration/timeout/suspension count item by item** on the pool and on checkout, and a test pins it with the counterexample "without limits, 500 MB is allowed" (if someone deletes a limit later, the case must go red).
- **[Deviation from the source material's Q42 "do not execute arbitrary code inside templates"]** → the limits are written out item by item in `04`'s trust boundary and `02` §6.12; the presence of code in a chain is greppable in frozen artifacts; the UDF shape stays unchanged.
- **[Code in the chain changes the audit semantics]** → the chain itself is visible (operator names greppable) + `04`'s four-layer trust model + the conformance pair count visibly going from 58 to 59.

## Migration Plan

1. Add the optional extra `code` to `pyproject.toml` (`all` excludes it), and lock the version.
2. Implement `ops/code.py` + the new error codes + `up2 ops` display.
3. Tests: isolation boundary / limits / determinism / tri-state / parameter shapes / missing-dependency gate; conformance pairs 58 → 59.
4. Docs: `02` §6.12 + slot table, `04` four-layer trust boundary, `05` dependencies and CI, `README` security section, `CHANGELOG`.
5. Rollback: remove the extra and the operator registration (unavailable by default, no data migration; an already-frozen chain containing `code` fails at compile time with `UP2-E1107` for the missing dependency, with predictable behavior).

## Open Questions

- Whether the specific default limit values (0.5 s / 64 MB / 5 s) are appropriate needs adjustment after load-testing with real documents.
- Whether to make "type checking" an operator parameter (`type_check: true`) — not now; wait for real misuse samples.
- The public API shape for host overrides (function / environment variable / config file): this change builds only a minimal in-process API; the rest is left to the application side.
