# uniparser2 Design · 01 Architecture and Value Model

> **Status**: design draft v0.1, now located in `docs/specs/` and committed. **Upstream**: `00`.
> **What this document answers**: which layers the engine consists of, which way dependencies are allowed to point, what values look like inside a chain, what to do when something fails, where the export is narrowed down, and where the security boundary is drawn.

---

## 1. Layering and dependency direction

```
                                ┌──────────────────────────────────────────────────────────────┐
callers (host / CLI)            │  cli/      command entry (lint / trial / …)                  │
                                │  ui/       pywebview trial bench / TUI                       │
                                │  store/    FileStore · SqliteStore                           │  ← the only layer allowed to touch disk
                                └────────────────────────┬─────────────────────────────────────┘
                                                         │ depends only on the public interface of core / chain
                                ┌────────────────────────▼─────────────────────────────────────┐
chain (specs & orchestration)   │  graph/    node model · sequential executor · lint           │
                                │  sop/      SOP orchestration (validate, trial run, publish)  │
                                └────────────────────────┬─────────────────────────────────────┘
                                                         │ depends only on the public interface of core
                                ┌────────────────────────▼─────────────────────────────────────┐
core (zero third-party deps)    │  values · ast · compile · registry                           │
                                │  evaluator · export · errors · limits                        │
                                └────────────────────────┬─────────────────────────────────────┘
                                                         │ one-way calls + reverse injection through the registry
                                ┌────────────────────────▼─────────────────────────────────────┐
ops (each lazy-imports)         │  html(css/css1) · xml(xpath) · json · re                     │
                                │  const · text(py) · ctx · each · udf                      │
                                └──────────────────────────────────────────────────────────────┘
```

### 1.1 Invariants (checked one by one during review)

| # | Invariant | Consequence of violation |
|---|---|---|
| I1 | `core/` **imports no third-party library at all**, and imports neither `ops/` / `graph/` / `store/` / `ui/` / `cli/` | the kernel stays unit-testable and portable; the kernel is still usable when an engine is missing |
| I2 | dependencies may only point **downward** (`cli → graph → core`), `ops` is injected in reverse by `core.registry`, and `ops` depends only on `core.values` / `core.errors` / `core.limits` | a cycle is a design error |
| I3 | **exactly one function** may produce the final product (`core.export.pack`); `N5` is guaranteed in exactly one place | the export type guarantee fails (R5 of the old v3) |
| I4 | **the compile product and the chain data are separate**: `compile()` returns a standalone object, and never hangs the compile result on a `str` subclass or on the chain dict | the dual payload of the old v3's `CompiledString` (R3) |
| I5 | operators are **without side effects, without IO, without global state**; the write surface of `ctx` is limited to `locals` | `N1` fails and the chain is not replayable |
| I6 | control flow **may only appear in the form of fields** (`each` / `routes` / `on_missing`), and there are no reserved keys in the result namespace | the old v3's protocol-like keys such as `__object__` (R2) |
| I7 | third-party engines may only be **lazily imported**; at import time only `find_spec` probing is allowed | a missing dependency makes the import fail and the whole package unusable (R7) |
| I8 | any chain that reaches the runtime has **already passed every lint**; the runtime performs no structural validation | `N3` fails and a bad chain blows up halfway |

### 1.2 Package layout

```
src/uniparser2/
  core/
    values.py     value-domain types + Opaque handles + type decisions + canonicalize
    errors.py     tri-state (Ok/Missing/Failed) + error codes + exception hierarchy
    limits.py     resource limit constants (the single source)
    ast.py        the normalized model of stages / fields / nodes / chains (compile-time input)
    registry.py   operator registry (@op decorator + optional dependency probing)
    compile.py    chain → CompiledGraph: lint + Schema validation + expression pre-compile + fingerprint
    evaluator.py  stage evaluation + field-chain evaluation + node advance
    export.py     export packing (the single product point) + built-in schema validation
    refs.py       reference syntax parsing and evaluation (`$<scope|node>.<path>`)
  ops/
    htmldom.py    css / css1 (one shared action table + the first_only flag, engine selectolax)
    xmlxpath.py   xpath (lxml)
    json.py       json (jmespath)
    re.py         re (standard library)
    text.py       py allowlist functions (plain text / collections / encoding / type conversion / time parsing)
    basic.py      const (literal, 2-ary) · each (one dictionary per element of a list, 2-ary)
    ctx.py        ctx (get/set/del/map)
    udf.py        udf (host-registered functions)
  graph/
    model.py      node TypedDict / dataclass
    executor.py   sequential executor (no DAG, no join)
    lint.py       the lint checklist (`03` §10)
  store/
    base.py       TemplateStore Protocol
    file.py       FileStore (one file per chain + audit.jsonl)
    sqlite.py     SqliteStore (two tables + transactions)
  sop/
    pipeline.py   SOP orchestration (the callable form of S1–S7)
  ui/
    webview.py    pywebview trial bench entry
    tui.py        TUI fallback entry
    assets/index.html  single-file front end (no build chain)
  cli/
    main.py       the up2 command entry
  __init__.py     public API (fully enumerated in `__all__`) + named logger + NullHandler
tests/
  conformance/    conformance audit: registry declarations × case coverage (`05` §4.1)
  ops/            operator behavior dictionary (per-operator input→output assertions)
  compile/        compile-time error codes, table-driven (`UP2-E1xxx`)
  runtime/        runtime error codes, table-driven (`UP2-E2xxx`)
  store/          storage-time error codes and the SOP (`UP2-E3xxx`)
  chains/         chain-level unit tests
  snapshots/      the expected product of chain × sample (the behavior contract)
  samples/        sample inputs (real page fragments)
```

**Reason (name and package name)**: `import uniparser2`, CLI `up2`. The old `uniparser` is already taken, and the old package is not changed (see `07` §4-a).

---

## 2. Fully synchronous (N8)

- The code **contains no** `async def` / `await` / `asyncio` / event loop.
- The trial bench uses pywebview: its `js_api` calls are themselves synchronously blocking, which matches exactly.
- If concurrency is ever needed (trial-running N samples in a batch), the caller wraps `run()` at the outermost level with `concurrent.futures.ThreadPoolExecutor`; the engine is unaware of it.
- Therefore no public function of the kernel **needs** to consider "am I inside an event loop", and starting threads internally is **forbidden**.

---

## 3. Value model (Tree)

### 3.1 Types

```python
JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
Opaque    = DOMNode | JsonNodeHandle | BytesHandle        # may only flow inside a chain
Value     = JsonValue | Opaque
```

| Decision | Content |
|---|---|
| **Adopt the Tree model** (D1-c of the old `dsl-design`) | the HTML/XML/JSON inputs are all trees, and the export is one projection of the tree; "multiple values" are opened up by explicit operators (`nodes` hands out a list, `each` expands it), not by an implicit boolean flag |
| **Do not adopt the D1-b Row model** | it would promote the special case of "a list page" to a global model, wrapping scalar scenarios in containers |
| **Do not adopt the D1-d stream model** | the export needs a fold to finish, the mental burden is permanent, and low-code users cannot follow it |
| **`Opaque` is an explicit type** | `self` / `nodes` produce node handles; **the export packing layer rejects `Opaque`** (`N5`), so a value must pass through a serializing action such as `text` / `html` / `@attr` before it can leave the chain |
| **`bytes` never enters the value domain** | the caller decodes (`run(chain, inputs)` and the CLI's `--input K=@file` hand over text); a tree is built on demand by the operator that consumes the value, under a run-scoped cache (`03` §3.1) |

**Lessons from v3**: the `_RECURSION_LIST` boolean flag let every operator decide on its own "whether to expand a list element by element", scattering the behavior across 14 classes (the internal source material, not shipped in this repository, `uniparser-essence.md` §5-R). This design **does not have that flag**: a list is produced by an ordinary operator (`css nodes` / `xpath nodes` / `re findall` / `json`) and expanded in exactly one place — an explicit `each` stage whose field map says what one element becomes — and the behavior of any operator on a `list` input must be written down explicitly in its own Schema.

### 3.2 Value equality and normalization

- `canonicalize(value) -> str`: used for fingerprints and snapshot comparison. Rules: JSON encoding, `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, `float` keeps `repr` semantics, `None` gets no special marker.
- Fingerprint: `blake2s(canonicalize(graph).encode("utf-8"), digest_size=16).hexdigest()` (the chain fingerprint, see `04` §3).
- Snapshot comparison: **structural comparison** (not string comparison), with differences emitted as a list of JSON Pointer paths; `canonicalize` is used only for fingerprints and diagnostic display.

---

## 4. Tri-state and error policy

### 4.1 Tri-state

```python
@dataclass(frozen=True, slots=True)
class Ok:      value: Value
@dataclass(frozen=True, slots=True)
class Missing: reason: str          # not matched: the selector did not match, the regex did not match, the key does not exist
@dataclass(frozen=True, slots=True)
class Failed:  code: str; reason: str; exc: Exception | None   # evaluation failed: type mismatch, conversion failure, exception inside an operator
```

| Rule | Content |
|---|---|
| **Missing ≠ error** | `Missing` is a normal result (the page simply does not have this field); `Failed` is an exception that requires a decision. The two must be separated, otherwise it is impossible to be both "bad data does not interrupt" and "bad rules surface early" |
| **An error is not a value** | never pass an exception object down as a result (this is the direct cause of the old v3 breaking "the export is all str", R5); `Failed` is a control signal, not a value |
| **Stage semantics** | see `02` §5. In one sentence: `Ok` → keep evaluating; `Missing` → short-circuit this field (settle a value according to the policy); `Failed` → `on_error` decides whether to interrupt or to degrade |
| **`on_error` defaults to `raise`** | bad rules should surface early; degradation is allowed only when it is explicitly declared (the recommendation of the old `dsl-design` §5.5) |
| **`on_missing` defaults to `empty`** | in scraping, "this news item has no publish time" is the norm and must not interrupt the whole chain |

### 4.2 Policy scope

A policy may be declared at **three levels**, with the nearest one overriding:

| Level | Where it is declared | Default |
|---|---|---|
| chain level | `graph.policy.on_missing` / `graph.policy.on_error` | `empty` / `raise` |
| field level | the object form of a field definition `{"chain": [...], "on_missing": "drop"}` | inherits the chain level |
| node level | `node.config.policy` | inherits the chain level |

> L1 implements only the **chain level**: the caller passes one `Policy` to `eval_field` (the CLI exposes
> it as `--on-missing` / `--on-error`). Field- and node-level declarations belong to the L2 chain format
> (`03` §4.2); L2 merges the three levels into that single `Policy`, so the kernel API stays unchanged.

Policy vocabulary (the tri-state × policy settlement table):

| Policy | Applied to `Missing` | Applied to `Failed` |
|---|---|---|
| `empty` | settles `""` (which is just the empty string in the value domain) | settles `""` |
| `none` | settles `null` | settles `null` |
| `drop` | the field does not appear | the field does not appear |
| `raise` | raises `ChainMissingError` | raises `ChainFailedError` (the default) |

> Whether to settle `""` or `null` is a **field contract** question, declared by the chain author; the engine does not guess on behalf of the business.

### 4.3 Error codes

Error codes are **the LLM's handle for self-correction**: every code must be **unique, stable, carry a one-sentence fix, and enumerate the allowed values**.

| Segment | Meaning | Example |
|---|---|---|
| `UP2-E1xxx` | compile time (lint / Schema) | `UP2-E1001` unknown operator |
| `UP2-E2xxx` | runtime (evaluation / packing) | `UP2-E2001` the reference path does not exist |
| `UP2-E3xxx` | storage (SOP / auditing) | `UP2-E3001` chain fingerprint conflict |

Full code table: **compile time** see `02` §7, **runtime** see `02` §7.1, **storage** see `04` §5.1. A bare `except:` is **forbidden**; the only fallback allowed is `except Exception:`, and it must be turned into a `Failed` carrying a code.

---

## 5. Compile-time / runtime separation

Absorbing B1 (pre-compilation at construction time) and R3 (the compile product must be standalone) of the old v3:

```python
def compile(chain: Chain) -> CompiledGraph: ...
```

| Phase | What it does | What it must not do |
|---|---|---|
| **Compile time** | full lint (`03` §10); Schema validation of every operator's arguments; action legality validation; reference resolution and the "may only point backward" check; pre-compilation of CSS selectors / regexes / jmespath expressions; `result` template validation; schema name resolution; fingerprint computation | any IO, any evaluation, any network |
| **Runtime** | pure evaluation: execute the stages according to the compile product, produce the value-domain tree, pack the export | structural validation, string parsing, any reflection other than looking an operator up by name |

Key points:

1. **`compile()` is idempotent**: passing an existing `CompiledGraph` returns it unchanged (the old v3 did this by checking `CompiledString`; this design does it by type check).
2. **`loads()` is tri-state idempotent**: it accepts "an instance / a JSON string / a dict", and `loads(loads(x))` is an identity (absorbing A2 of the old v3, so the caller need not decide the input form).
3. Pre-compiled products live in `CompiledGraph.steps[i].compiled` and do not pollute the chain data.

---

## 6. Export packing (the single implementation point of N5)

```python
def pack(value: Value, schema: SchemaSpec | None) -> Ok | Failed: ...
```

Three stages, in a fixed order:

1. **Reject `Opaque`**: hitting a DOM handle yields `UP2-E2003` and points out which field it is (with the hint "serialize it through `text`/`html`/`@attr` first").
2. **Schema validation** (if declared): type, optionality, list elements, nested objects; a failure yields `Failed` with a JSON Pointer path.
3. **Settle empty values**: according to the effective policy, settle `Missing` into `""` / `null` / omission.

### 6.1 Own Schema description (JSON Schema is not adopted)

The export structure is limited and must be friendly to LLM generation, so a **restricted type vocabulary** is defined (an order of magnitude shorter than JSON Schema, with zero third-party dependencies):

```jsonc
{
  "title":    "str",                 // required str
  "pub_time": "str?",                // optional str
  "word_cnt": "int?",
  "files":    [{"name": "str", "url": "str"}],   // a list whose elements are objects
  "meta":     "json"                 // any serializable value
}
```

| Word | Meaning |
|---|---|
| `str` / `int` / `float` / `bool` / `json` | scalar types; `json` = any JSON value |
| the `?` suffix | optional (`null` and a missing key are both legal) |
| `[...]` | a list whose elements are described by the inner description |
| `{...}` | a nested object |
| built-in named schemas | `$request` (structure in `03` §5.2), `$article`, `$file` (host-registered, `04` §7) |

**Reason**: JSON Schema's expressive power is excessive for this scenario, and an LLM's error rate and token cost when generating JSON Schema are both significantly higher; the restricted vocabulary covers 100% of this engine's export shapes, and error messages can be precise down to "which key of which list element".

---

## 7. Operator registry and optional dependencies

```python
@op("css", requires=("selectolax",))          # operator-level dependency
class CssOp: ...
# action-level dependency: ActionSpec(..., requires=("html_to_markdown",)), e.g. py.html_to_markdown
```

| Rule | Content |
|---|---|
| **Explicit registration** | register explicitly with the `@op(...)` decorator; **no** implicit discovery through `__subclasses__()` (a subclass that is never imported silently drops an operator — the same root cause as R7). Registration has **two phases**: validate all names first, then commit to the table, avoiding the half-registration left behind by "the name was taken and an alias conflict raised" |
| **Optional-dependency probing** | at import time only `importlib.util.find_spec(name)`, which **does not trigger an import**. When a dependency is missing, the **declaration is kept** but marked unavailable — that is how a reference to it can give `UP2-E1107` plus the install command (more diagnostic value than letting it disappear from the registry). `up2 ops` lists the unavailable entries |
| **Dependency granularity** | dependencies can be declared per **action** (`ActionSpec.requires`), not only per operator: a missing `html-to-markdown` for `py.html_to_markdown` does not affect `py.strip`. There is also `any_requires`, meaning "installing any one of them is enough" (selectolax / beautifulsoup4 for `css`) |
| **Lazy import** | the actual use of third-party code happens inside the operator through `importlib.import_module` (optional dependencies are always imported dynamically, so that four type checkers do not each report "module does not exist"); a failure turns into `UP2-E2004` and hints at the install name |
| **Capability self-description** | `up2 ops --json` outputs, per operator: name, aliases, arity (`arity`), slot roles (`action_slot` / `slots`), the action enumeration (`actions`, each with `name` / `summary` / `available` / `accepts_missing`), the argument Schema (`params`: `name` / `kind` / `required` / `default`), **the writing slot 3 takes (`param_form`: `none` / `value` / `named`, see `02` §4)**, dependencies (`requires` / `missing`) and the install command of a missing dependency — an LLM drafting a chain reads this first (`04` §7-S0, §8) |
| **Aliases** | `py` ↔ `python`, `json` ↔ `jmespath`; aliases resolve to the same operator inside the registry, and **the chain data keeps the original spelling** (stable fingerprints) |
| **The evaluation signature of an operator** | `evaluate(call) -> Outcome`, where `call` is a `Call` context object (`value` / `action` / `params` / `payload` / `scope`). A context object instead of a long argument list: adding a field does not break every operator's signature |

---

## 8. Security model (goal 1b)

| Surface | Measure |
|---|---|
| **Code execution** | `core/` contains no `eval`/`exec`/`compile`/`__import__`, and a rule cannot reach host code: `udf` only looks a name up in the host registry, and an unregistered name is a compile-time error (`UP2-E1010`). The **one exception** is the opt-in `code` sandbox (`02` §6.12): measured there, `compile`/`__import__` do not exist and file/environment/network/process reach **fails** (absent or blocked, per surface), while the language features `eval`/`exec` do exist and grant no capability of their own (`04` §11.3) |
| **IO** | the kernel does no network or file work; `store/` is the only layer that touches disk, and it stores only chains and audits (it does not store input or output content unless `--save-sample` is explicit) |
| **SSRF / fetching surface** | the kernel issues no requests, so this surface does not exist; the request dict is consumed by the host, and the host does its own URL allowlisting (this design only declares the structure, in `03` §5.2) |
| **Regex backtracking (ReDoS)** | at compile time a **nested-quantifier check** is run on regexes and reports `UP2-E1013`. **Measured correction**: Python 3.13/3.14 `re` **has no `timeout` argument**, so **there is no timeout backstop at runtime** — static detection catches only the most classic shape (`(a+)+`), and missed shapes such as overlapping alternations are a recorded gap (`02` §6.3) |
| **Resource exhaustion** | see §9 limits: the shape of a chain is validated entirely at compile time, and the iteration count is validated at runtime |
| **Reference out of bounds** | a reference may only point at a **declared** scope and the **declared product keys** of preceding nodes; a `_`-prefixed key referenced **across nodes** is rejected (`UP2-E1014`), while within its own node it is legal |
| **Cycles** | chains are acyclic (`UP2-E1104`); `each` field-map nesting depth is limited; the path list of `ctx.map` cannot reference itself |
| **Deserialization** | chains are read from JSON only, never with `pickle`/`yaml.load` (unsafe loaders are never used); after a Store reads a chain back it **must `compile()` again**, and the compile product in storage is never trusted |

---

## 9. Resource limits (`core/limits.py`, the single source)

The limit constants are centralized in one place, taken from there by both compile time and runtime; **chain data cannot override limits** (otherwise an LLM could unlock itself).

**Only declare the constants that the current layer actually uses** (L1 only needs the per-field stage cap); add the rest as layers land — do not lay out a row of constants that nobody reads.

| Constant | Value | Applied at | Landing layer |
|---|---|---|---|
| `MAX_STEPS_PER_FIELD` | 32 | cap on the number of stages per field (compile time, exceeding it gives `UP2-E1012`) | **L1 (implemented)** |
| `MAX_NODES` | 64 | cap on the number of nodes in a chain (compile time) | L2 |
| `MAX_FIELDS_PER_NODE` | 128 | cap on the number of fields per node (compile time) | L2 |
| `MAX_EACH_DEPTH` | 3 | `each` field-map nesting depth (compile time, exceeding it gives `UP2-E1012`) | **L1 (implemented)** |
| `MAX_EACH_ITER` | 10_000 | number of elements a single `each` iterates (turned into `Failed` at runtime, `UP2-E2012`) | **L1 (implemented)** |
| `MAX_TEXT_BYTES` | 16 MiB | byte cap on an accepted input (turned into `Failed` when the input is accepted, before any operator sees it) | L2 |
| `MAX_MATERIALIZE_BYTES` | 64 MiB | cap on the run-scoped materialization cache, accounted in **materialized** bytes (`03` §3.1); LRU, and one artifact may exceed it while it is in use | L2 |
| `MAX_MATERIALIZE_ITEMS` | 8 | how many materialized artifacts one run keeps (`03` §3.1) | L2 |

> **Deleted constant**: `REGEX_TIMEOUT_S`. It originally corresponded to `UP2-E2006` "regex execution timeout", but Python's `re` has no `timeout` argument (measured), so this constant has no real point of application. The constant and its error code are removed rather than leaving a false promise.

**Reason**: an LLM-generated chain may have an out-of-control shape (hundreds of stages, deep nesting, N² iteration over a whole page); hard-coding the caps in the kernel so that "out of control" is rejected at compile time is the cheapest gate for stability (goal 1c).

---

## 10. Logging and observability

Absorbing the old v3's "library logging conventions": in `__init__.py`, `logger = logging.getLogger("uniparser2")` + `logger.addHandler(logging.NullHandler())`, **without seizing the host's logging configuration**. The public API is fully enumerated in `__all__`.

| Event | Level | Payload |
|---|---|---|
| compile ok | `DEBUG` | `chain_id` / `tpl_key` / fingerprint / node count / elapsed time |
| stage evaluation | `DEBUG` | node key / field name / stage index / action / elapsed time / tri-state (**off by default**; the trial bench's trace does not depend on logs) |
| a tri-state of `Failed` | `WARNING` | error code + one-sentence reason + node/field location |
| export packing failure | `WARNING` | error code + JSON Pointer + expected type vs actual type |
| missing operator dependency | `INFO` (on the first `up2 ops`) | operator name + missing dependency + install command |

**Deviation record from the upstream material**: the old v3 achieved "does not blow up" with "an error is a value + a `SYSTEM_ERRORS` allowlist re-raise" (the internal source material, not shipped in this repository, `uniparser-essence.md` §B5). This design replaces that with the tri-state, but **keeps the allowlist idea**: `KeyboardInterrupt` / `SystemExit` / `MemoryError` / `OSError` are **never swallowed** and propagate directly upward (implementation site: the fallback `except Exception:` in `evaluator`, never a bare `except:`).
