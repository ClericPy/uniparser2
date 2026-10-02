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
chain (specs & orchestration)   │  story/    step model · the run loop · lint                 │
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
| I6 | control flow **may only appear in the form of fields** (`each` / the policy), and branching **never appears inside a story** — the host picks the story and dispatches on the product's type name (`03` §1); there are no reserved keys in the result namespace | the old v3's protocol-like keys such as `__object__` (R2) |
| I7 | third-party engines may only be **lazily imported**; at import time only `find_spec` probing is allowed | a missing dependency makes the import fail and the whole package unusable (R7) |
| I8 | any chain that reaches the runtime has **already passed every lint**; the runtime performs no structural validation | `N3` fails and a bad chain blows up halfway |

### 1.2 Package layout

```
src/uniparser2/
  core/
    values.py     value-domain types + Opaque handles + type decisions + canonicalize
    errors.py     tri-state (Ok/Missing/Failed) + error codes + exception hierarchy
    limits.py     resource limit constants (the single source)
    ast.py        the normalized model of stages / fields / steps / stories (compile-time input)
    registry.py   operator registry (@op decorator + optional dependency probing)
    compile.py    chain → CompiledGraph: lint + Schema validation + expression pre-compile + fingerprint
    evaluator.py  stage evaluation + field-chain evaluation + step advance
    export.py     export packing (the single product point) + built-in schema validation
    refs.py       reference syntax parsing and evaluation (`$<scope|step>.<path>`)
    types.py      the host's type registry (name → constructor) + the step-boundary construction (`03` §3)
    story.py      the story layer: compile a bundle, then run it to its next suspension (`03` §2-§5)
    udfs.py       the host's user-defined function registry (name → callable)
    conformance.py the pure half of the conformance audit (declaration × coverage)
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
    model.py      step TypedDict / dataclass
    executor.py   sequential executor (no DAG, no join)
    lint.py       the lint checklist (`03` §10)
  store/
    model.py      Status/Source/Graph, Template, TemplateMeta, AuditRow, PublishResult, new_chain_id
    fingerprint.py the graph fingerprint (blake2s over the canonicalised graph)
    base.py       the TemplateStore Protocol + the shared publish algorithm (`04` §5)
    gates.py      the publish gates G2/G3 that live above the store (`04` §6)
    file.py       FileStore (one file per chain + audit.jsonl)
    sqlite.py     SqliteStore (two tables + one transaction per publish)
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
Opaque    = DOMNode | JsonNodeHandle | BytesHandle        # may flow, never exits
HostObject = <anything the host hands over: a response, a udf result>
Value     = JsonValue | Opaque | HostObject
```

| Decision | Content |
|---|---|
| **Adopt the Tree model** (D1-c of the old `dsl-design`) | the HTML/XML/JSON inputs are all trees, and the export is one projection of the tree; "multiple values" are opened up by explicit operators (`nodes` hands out a list, `each` expands it), not by an implicit boolean flag |
| **Do not adopt the D1-b Row model** | it would promote the special case of "a list page" to a global model, wrapping scalar scenarios in containers |
| **Do not adopt the D1-d stream model** | the export needs a fold to finish, the mental burden is permanent, and low-code users cannot follow it |
| **`Opaque` is an explicit type** | `self` / `nodes` produce node handles; **the export packing layer rejects `Opaque`** (`N5`), so a value must pass through a serializing action such as `text` / `html` / `@attr` before it can leave the chain |
| **A value that flows may be a host object; a product must be JSON** | a response object, a library node and anything a `udf` returns travel by reference (read with `py.getattr`), but **a step product must be JSON**: after the step's type constructor runs, the product re-enters `JsonValue`, and the single exit (`UP2-E2003`) still holds |
| **`bytes` never enters the value domain** | the caller decodes (`start(story, value)` and the CLI's `--input K=@file` hand over text); a tree is built on demand by the operator that consumes the value, under a run-scoped cache (`03` §6) |

**Lessons from v3**: the `_RECURSION_LIST` boolean flag let every operator decide on its own "whether to expand a list element by element", scattering the behavior across 14 classes (the internal source material, not shipped in this repository, `uniparser-essence.md` §5-R). This design **does not have that flag**: a list is produced by an ordinary operator (`css nodes` / `xpath nodes` / `re findall` / `json`) and expanded in exactly one place — an explicit `each` stage whose field map says what one element becomes — and the behavior of any operator on a `list` input must be written down explicitly in its own Schema.

### 3.2 Value equality and normalization

- `canonicalize(value) -> str`: used for fingerprints and snapshot comparison. Rules: JSON encoding, `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, `float` keeps `repr` semantics, `None` gets no special marker.
- Fingerprint: `blake2s(canonicalize(graph).encode("utf-8"), digest_size=16).hexdigest()` (the chain fingerprint, see `04` §3).
- Snapshot comparison: **structural comparison** (not string comparison), with differences emitted as a list of JSON Pointer paths; `canonicalize` is used only for fingerprints and diagnostic display.

---

## 4. Tri-state and error handling

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
| **Stage semantics** | see `02` §5. In one sentence: `Ok` → keep evaluating; `Missing` → short-circuit this field and stay missing; `Failed` → stop the chain and report the code of the stage that failed |
| **A missing value is not a value** | the engine does not settle `Missing` into `""` or `null`: in a field map the key is absent from the product, in a batch the item is skipped. A fallback for one field is written where it applies, at the action level (`py.default` / `py.or`) |
| **A failed stage always fails the run** | bad rules surface early, with the code of the stage that failed; no configuration turns a failure into a value |

### 4.2 Missing and failed have fixed outcomes

The tri-state settles in exactly two ways, and there is nothing to configure:

| State | Outcome |
|---|---|
| `Missing` | **not there**: in a field map the key is **absent** from the product; in a batch the item is **skipped**; at a step boundary the step is **skipped** (no product, and nothing in the exit list) — never `""`, never `null` |
| `Failed` | **always fails the run**, carrying the code of the stage that failed (its JSON Pointer in the trace); nothing degrades it |

A field that must exist is enforced by the **host-registered type constructor** at the step boundary
(`03` §3): it reports the missing key at the step that produced it (`UP2-E2019`, the constructor's own
exception text in `reason`), which is where the author can see it. A value that may be absent is made
present by the action that knows how — `py.default` and `py.or` catch a missing value
(`accepts_missing`, `02` §5) instead of reconfiguring the whole run.

> **The settlement policy is retired** (change `retire-settlement-policy`): the `Policy` type, the four
> `on_missing` / `on_error` strategies, the `policy=` parameter of `eval_field`, the `policy` block of a
> story (`03` §2) and the CLI's `--on-missing` / `--on-error` are all gone, and `UP2-E2015` is retired
> without reusing its number. The deviation record is `D-01-1` in §11.

### 4.3 Error codes

Error codes are **the LLM's handle for self-correction**: every code must be **unique, stable, carry a one-sentence fix, and enumerate the allowed values**.

| Segment | Meaning | Example |
|---|---|---|
| `UP2-E1xxx` | compile time (lint / Schema) | `UP2-E1001` unknown operator |
| `UP2-E2xxx` | runtime (evaluation / packing) | `UP2-E2001` the reference path does not exist |
| `UP2-E3xxx` | storage (the template store / auditing) | `UP2-E3001` chain fingerprint conflict |

Full code table: **compile time** see `02` §7, **runtime** see `02` §7.1, **storage** see `04` §5.1 (implemented: `UP2-E3001`–`UP2-E3005`). A bare `except:` is **forbidden**; the only fallback allowed is `except Exception:`, and it must be turned into a `Failed` carrying a code — the store layer is the one place where such a fallback raises `Up2Error` with `UP2-E3004` instead, because a store failure has no `Failed` channel (`04` §5).

---

## 5. Compile-time / runtime separation

Absorbing B1 (pre-compilation at construction time) and R3 (the compile product must be standalone) of the old v3:

```python
def compile(chain: Chain) -> CompiledGraph: ...
```

| Phase | What it does | What it must not do |
|---|---|---|
| **Compile time** | full lint (`03` §10); Schema validation of every operator's arguments; action legality validation; reference resolution and the "may only point backward" check; pre-compilation of CSS selectors / regexes / jmespath expressions; `type` resolution; fingerprint computation | any IO, any evaluation, any network |
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

Two stages, in a fixed order:

1. **Reject `Opaque`**: hitting a DOM handle yields `UP2-E2003` and points out which field it is (with the hint "serialize it through `text`/`html`/`@attr` first").
2. **Schema validation** (if declared): type, optionality, list elements, nested objects; a failure yields `Failed` with a JSON Pointer path.

There is **no empty-value settlement step**: a `Missing` field is not a value at all, so it never reaches
packing — its key is simply absent from the product (§4.2).

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
| built-in types | `Request` / `RequestBatch` (the effect types; the `Request` structure is in `03` §4.1), plus host-registered types (`Article`, `NoticeList`, …; `03` §3). There is no `Response`: an answer is the host's own object and has no declared type (`03` §4.1) |

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
| **SSRF / fetching surface** | the kernel issues no requests, so this surface does not exist; the request dict is consumed by the host, and the host does its own URL allowlisting (this design only declares the structure, in `03` §4.1) |
| **Regex backtracking (ReDoS)** | at compile time a **nested-quantifier check** is run on regexes and reports `UP2-E1013`. **Measured correction**: Python 3.13/3.14 `re` **has no `timeout` argument**, so **there is no timeout backstop at runtime** — static detection catches only the most classic shape (`(a+)+`), and missed shapes such as overlapping alternations are a recorded gap (`02` §6.3) |
| **Resource exhaustion** | see §9 limits: the shape of a chain is validated entirely at compile time, and the iteration count is validated at runtime |
| **Reference out of bounds** | a reference may only point at a **declared** scope and the **declared product keys** of preceding steps; a `_`-prefixed key referenced **across steps** is rejected (`UP2-E1014`), while within its own step it is legal |
| **Cycles** | a story is a linear sequence, so a cycle cannot be expressed at all (the v0.1 graph and its `UP2-E1104` check are retired, `03` §12.1); `each` field-map nesting depth is limited; the path list of `ctx.map` cannot reference itself |
| **Deserialization** | chains are read from JSON only, never with `pickle`/`yaml.load` (unsafe loaders are never used); after a Store reads a chain back it **must `compile()` again**, and the compile product in storage is never trusted |

---

## 9. Resource limits (`core/limits.py`, the single source)

The limit constants are centralized in one place, taken from there by both compile time and runtime; **chain data cannot override limits** (otherwise an LLM could unlock itself).

**Only declare the constants that the current layer actually uses** (L1 only needs the per-field stage cap); add the rest as layers land — do not lay out a row of constants that nobody reads.

| Constant | Value | Applied at | Landing layer |
|---|---|---|---|
| `MAX_STEPS_PER_FIELD` | 32 | cap on the number of stages per field (compile time, exceeding it gives `UP2-E1012`) | **L1 (implemented)** |
| `MAX_NODES` | 64 | cap on the number of **steps** in a story (compile time) | L2 |
| `MAX_FIELDS_PER_NODE` | 128 | cap on the number of fields per **step** (compile time) | L2 |
| `MAX_EACH_DEPTH` | 3 | `each` field-map nesting depth (compile time, exceeding it gives `UP2-E1012`) | **L1 (implemented)** |
| `MAX_EACH_ITER` | 10_000 | number of elements a single `each` iterates (turned into `Failed` at runtime, `UP2-E2012`) | **L1 (implemented)** |
| `MAX_FIELDS_PER_MAP` | 256 | cap on the fields of **one field map** (compile time, exceeding it gives `UP2-E1012`) | **L1 (implemented)** |
| `MAX_TEXT_BYTES` | 16 MiB | byte cap on an accepted input (turned into `Failed` when the input is accepted, before any operator sees it) | L2 |
| `MAX_MATERIALIZE_BYTES` | 64 MiB | cap on the run-scoped materialization cache, accounted in **materialized** bytes (`03` §6); LRU, and one artifact may exceed it while it is in use | **L2 (implemented)** |
| `MAX_MATERIALIZE_ITEMS` | 8 | how many materialized artifacts one run keeps (`03` §6) | **L2 (implemented)** |

> **`MAX_FIELDS_PER_MAP` and `MAX_FIELDS_PER_NODE`**: a field map is the shape both `each` and a step's field map use, so the per-map cap is checked on every map, and the compilation cost it guards is per map. When the story layer lands, `MAX_FIELDS_PER_NODE` (128) becomes the tighter per-step cap on top of it.

> **Deleted constant**: `REGEX_TIMEOUT_S`. It originally corresponded to `UP2-E2006` "regex execution timeout", but Python's `re` has no `timeout` argument (measured), so this constant has no real point of application. The constant and its error code are removed rather than leaving a false promise.

**Reason**: an LLM-generated chain may have an out-of-control shape (hundreds of stages, deep nesting, N² iteration over a whole page); hard-coding the caps in the kernel so that "out of control" is rejected at compile time is the cheapest gate for stability (goal 1c).

---

## 10. Logging and observability

Absorbing the old v3's "library logging conventions": in `__init__.py`, `logger = logging.getLogger("uniparser2")` + `logger.addHandler(logging.NullHandler())`, **without seizing the host's logging configuration**. The public API is fully enumerated in `__all__`.

| Event | Level | Payload |
|---|---|---|
| compile ok | `DEBUG` | `chain_id` / `tpl_key` / fingerprint / step count / elapsed time |
| stage evaluation | `DEBUG` | step key / field name / stage index / action / elapsed time / tri-state (**off by default**; the trial bench's trace does not depend on logs) |
| a tri-state of `Failed` | `WARNING` | error code + one-sentence reason + step/field location |
| export packing failure | `WARNING` | error code + JSON Pointer + expected type vs actual type |
| missing operator dependency | `INFO` (on the first `up2 ops`) | operator name + missing dependency + install command |

**Deviation record from the upstream material**: the old v3 achieved "does not blow up" with "an error is a value + a `SYSTEM_ERRORS` allowlist re-raise" (the internal source material, not shipped in this repository, `uniparser-essence.md` §B5). This design replaces that with the tri-state, but **keeps the allowlist idea**: `KeyboardInterrupt` / `SystemExit` / `MemoryError` / `OSError` are **never swallowed** and propagate directly upward (implementation site: the fallback `except Exception:` in `evaluator`, never a bare `except:`).

---

## 11. Deviation records

### 11.1 `D-01-1` — the settlement policy is retired

The tri-state originally settled through a chain-level policy (`{on_missing, on_error}`, four strategies
each), threaded through `eval_field`, the story JSON and the CLI. Change `retire-settlement-policy`
deletes it:

| Removed | Where it was |
|---|---|
| `Policy` / `DEFAULT_POLICY` / `MISSING_STRATEGIES` / `ERROR_STRATEGIES` | `core/evaluator.py` |
| the `policy` parameter of `eval_field` | `core/evaluator.py`, `core/__init__.py` |
| `--on-missing` / `--on-error` | `up2 trial` (`cli/main.py`) |
| the `policy` block | the story JSON (`03` §2) |

`on_missing="empty"` — the old default — is the reason for the retirement: it wrote `""` into a record
whenever a selector never matched, which is a lie in the data. Missing now means "not there" and a failed
stage always fails the run (§4.2), so "tolerate one absence" is expressed at the action level
(`py.default` / `py.or`) and "this field must exist" by the host-registered type constructor.

The tri-state itself, `accepts_missing` and the actions that catch a missing value are **unchanged**: only
the configurable settlement went. `UP2-E2015` ("value is missing and the effective policy is raise") is
**retired, not reused** (`02` §7.1), so an older reference still points at the same meaning.
