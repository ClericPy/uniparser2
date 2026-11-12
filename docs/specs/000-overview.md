# uniparser2 Design · 00 Overview and Scope

> **Status**: design draft v0.1 (under discussion; now located in `docs/specs/` and committed).
> **Source material**: the internal source material, not shipped in this repository: the old design drafts `dsl-design.md` and `uniparser-essence.md`,
> plus the template-engine data drafts `01-\u6570\u636e\u7ed3\u6784\u8349\u7a3f.md`, `02-\u8d70\u901a\u4f8b\u5b50-ah.gov.cn.md`, `04-\u89e3\u6790\u5668\u8bed\u6cd5-\u6700\u7ec8.md`.
> **Basis for the rulings**: the adoption/modification/discarding of each source material is in `007-source-decisions-and-roadmap.md`; this document gives conclusions only.

---

## 1. Positioning in one sentence

uniparser2 is a **fully synchronous, IO-free, serialisable** deterministic parsing engine: it writes the parsing process of "input text → a specified structure" as JSON data (**a parse chain**), generated offline by an LLM or a person, with runtime doing nothing but deterministic evaluation; a chain can be persisted, linted, trialled in place and snapshot-regressed.

The boundary of its complexity is written into the name: **it is an evaluator + a specification for chains + an SOP + an in-place trial UI**, not a crawler framework and not a scheduling system.

---

## 2. The end-state acceptance criteria

The end state is pinned down before the design starts, so that every later trade-off aligns with it.

```python
def run(story: Story, node: str | None = None, input: JsonValue = None, *, globals=None,
        udfs: Mapping[str, UdfFn] | None = None, trace: Trace | None = None) -> JsonValue: ...
# Story      = a compiled story: `globals` + `nodes` (`03` §2)
# node       = the node to run; the first node when omitted
# input      = that node's `$in`
# udfs       = the run's host functions (`fetch` is the conventional downloader)
# product    = JsonValue; every node is an entry point, so there is no `collect`
```

| No. | Contract | Description |
|---|---|---|
| **N1** | **Pure function** | same input, same chain → same output; no network, no files, no global mutable state, no implicit input source |
| **N2** | **A chain survives a lossless JSON round trip** | a chain is data, and `dumps(loads(x)) == dumps(x)` holds character for character (absorbing the old design's "tests are the contract") |
| **N3** | **A bad chain fails at compile time** | unknown operator, unknown action, mismatched argument type, dangling reference, cycle, reserved-name collision — all error during `compile()` and never reach runtime |
| **N4** | **A query that matches nothing does not blow up the chain** | "not there" is the shape's empty value (`""` / `[]` / `None`), not an error and not a settled `null`; a failed stage always fails the run with the code of the stage that failed. The empty-value rule replaced the third outcome in `empty-value-semantics` (`01` §4.2, `D-01-1`) |
| **N5** | **The export is packed by a single function** | any export value must pass through the `export` layer; non-serialisable values such as DOM handles never appear in the export |
| **N6** | **No code capability inside a rule** | a chain cannot reach a host capability: no `import` of third-party code, no file, no network and no process, and custom logic enters through a host-registered named function (`udf`). The **single opt-in exception** is the `code` sandbox (`02` §6.12, `04` §11.3): absent by default, language-level only, and measured to expose no host capability — it is NOT a promise about the words `eval`/`exec` (per-surface table in `04` §11.3) |
| **N7** | **Callable nodes, no DAG scheduling** | a story is a map of **callable nodes**; a node call may name any node, the call graph is acyclic (`03` §5.2), and there is no join, no in-degree counting and no scheduler |
| **N8** | **Fully synchronous** | no `async`/`await`; `run` executes the node and returns its product, and a host `udf` that needs async work resolves it in the host before returning (`03` §4). Concurrency, if wanted, wraps whole runs |

`N1 + N2 + N3` decide the essence of the thing: **zero AI, zero IO, zero nondeterminism at runtime**; AI appears only in the chain-generation phase (see the SOP in `04`).

### 2.1 Deviations from the old design's C1–C3 (confirmed)

The hard contracts C1/C2/C3 of the old `dsl-design` are "the export must be `dict[str, str]`, with every key and every value a `str`". **This design does not adopt them**, for these reasons:

- One of the target products is precisely a **request-specific dict** (`{"url":…, "method":…, "headers":{}, "timeout":30, "body":null}`), which naturally contains dict / int / null / bool and cannot simultaneously satisfy "flat, all str".
- A product is a JSON value; a `["type", name]` stage validates it (`03` §3), so a structured export is the norm rather than an exception.
- What is genuinely valuable in the "all str" discipline is **"the export has a single packing point"** and **"the exit type is asserted"**, and those two are inherited here in the form of `N5` + the `type` stage.

**Conclusion**: the export is **the product of the node `run` names**, validated by a `["type", name]` stage when one is written; a collection is a named field of that product. The old "flat `dict[str,str]`" fallback (`produces: "flat"`) is gone with the node model (`03` §12.1).

---

## 3. Four root goals → where they land in the design

| Goal | Where it lands | Carrier document |
|---|---|---|
| **1a Low-code** | chain = JSON data; the compact triple notation; table-driven operators with a unified slot order `[operator, mode, argument]` (enumeration strength increasing across the three positions); an LLM/person only has to remember the two-dimensional "operator × action" table | `02` |
| **1b Safety** | no code capability inside a rule (`N6`), except the opt-in `code` sandbox; an allowlisted function table; registration-based `udf`; references only backwards; resource-limit constants | `01` §8–§9, `02` §6.4/§6.10/§6.12, `04` §11 |
| **1c Stability** | pure functions (`N1`) + full compile-time validation (`N3`) + two outcomes with fixed meanings (`N4`) + snapshot regression | `01` §4–§6, `05` §4 |
| **2 An LLM-friendly SOP for persisting parse chains** | the persistence data model for chains (one row per chain + fingerprint auditing) + the Store abstraction + the step-by-step `S0–S7` SOP + deterministic error codes + the counter-example list | `04` |
| **3 Test/OpenSpec/document-driven + uv** | uv manages dependencies and releases; layered pytest (an operator-behaviour dictionary / chain snapshots / end to end); `docs/specs` is the source of truth; OpenSpec takes over changes | `05` |
| **4 No coroutines + an in-place trial page** | fully synchronous (`N8`); `up2 studio` (pywebview three columns + single-stage trace + the "save as snapshot" loop), degrading to TUI/CLI when unavailable | `01` §2, `06` |

### 3.1 The order of landing: operators → structure → binding

**First let the parse chain stand on its own, then let it assemble complex structures, and only then bind it to a business identity.**

| Layer | What it does | What it explicitly does not do |
|---|---|---|
| **L1 operator layer** | the value domain / the outcome model / references / compile-time validation / export packing; **12 operators** (`css`/`css1`/`xpath`/`json`/`re`/`py`/`udf`/`ctx`/`each`/`code`/`node`/`type`, where `time`/`cast`/`const` have been merged into `py` and `code` is in `02` §6.12) with all their actions; **the globals/locals design of `ctx`**; **the conformance test set** (every `(operator, action)` has a case) | no multi-field orchestration, no list/nested structures, **no domain names or business keys** |
| **L2 structure layer** | a **story**: `globals` plus a map of **nodes** (a node body is a chain or a field map; `["node", name]` composes, `["type", name]` validates a chain tail); multi-field orchestration; `each` iteration (a list → one value per element) → arbitrarily nested `list`/`dict`; a synchronous `run`; the run-scoped materialization cache; lint | **still no domain names or business keys**; no network requests of its own (`fetch` is a host `udf`) |
| **L3 binding layer** | binding a chain to a business identity and freezing it: `root_domain` / `tpl_key`, the Store, fingerprints and auditing, the `publish` gates, the `S0–S7` SOP; a seam example of a host consuming the request dict | — |

**Criterion**: item 5 of the L3 acceptance criteria in `07` §3 requires that "after deleting every concept of `04` from the code, all L1/L2 tests still pass" — that is the mechanically checkable form of "the first two layers have zero business coupling".

**The break in the request part**: a node that fetches calls the host's `fetch` udf; the story says *what* to request, while who sends it, how many times, and with which site credentials is entirely up to the host (`03` §4). This isolates the request capability and the business binding **simultaneously**, in two directions.

---

## 4. Scope

### 4.1 What is in (the kernel)

1. **The value domain and the evaluation kernel**: the value tree, the outcome model, the operator registry, chain evaluation, export packing (`01`, `02`).
2. **The story specification**: `globals` + `nodes`, node bodies (a chain or a field map), `["node", name]` composition, the chain-tail `["type", name]`, the synchronous `run`, the compile-time lint checklist (`03`).
3. **Chain persistence and the SOP**: the `Template` / `TemplateAudit` data model, the Store abstraction (file + SQLite), the step-by-step LLM SOP (`04`).
4. **The in-place trial UI**: `up2 lint` / `up2 trial` / `up2 studio` / `up2 ops` / `up2 publish` / `up2 audit` (`06`).
5. **Engineering foundations**: uv dependencies and releases, layered pytest, documentation-driven development, OpenSpec integration, change-linter (`05`).

### 4.2 What is out (explicitly excluded, to keep the scope from flowing back)

| Exclusion | Reason |
|---|---|
| **HTTP download, rate limiting, retries, proxies, user agents** | violates `N1`; collection belongs to the host. The kernel only **produces a request dict**, and who sends it is decided by the caller |
| **Scheduling, job tables, doc tables, queues, Kafka** | production-system concerns; the `task` / `doc` / EOS / Java contracts of draft `01` are all left behind |
| **Byte storage (S3/EOS), download pipelines** | same as above; the kernel does not move bytes |
| **`async` / coroutines / event loops** | explicitly out (`N8`); when concurrency is needed, put a thread pool further out |
| **Executing arbitrary Python inside a rule (the `udf` shape of v3)** | violates `N6`; replaced by registration-based named functions. **One deliberate exception** is the `code` operator (`02` §6.12): opt-in through `uniparser2[code]`, absent from a default install and from `[all]`, language-level sandbox only (`04` §11.3–§11.5) |
| **An online rule marketplace, multi-tenancy, a permission system** | beyond the "engine + SOP" positioning |
| **A general expression language / conditional-branch language** | it would let the DSL grow into half a programming language. Branching is **not in the story at all**: the host picks which story to run and dispatches on the product's type name (`03` §1), so no conditional syntax is needed |
| **A front-end build chain (node/vite/npm)** | the trial UI uses a single HTML file plus plain JS, avoiding a second toolchain for the sake of the UI |

---

## 5. Glossary (fixed usage throughout)

| Term | English/identifier | Definition |
|---|---|---|
| **story** | story | one complete parsing process, serialisable as JSON: `globals` + `nodes` (`03` §2); once persisted, one row = one story |
| **chain key** | `tpl_key` | the human-readable business name of a chain, unique within a `root_domain`; the caller uses it to reference the chain |
| **node** | node | one named, callable unit inside a story: a **chain** (array; `[]` is identity) or a **field map** (object) (`03` §2.1) |
| **stage** | stage | one stage of a field chain, i.e. the triple `[operator, slot 2, slot 3]` (a 2-ary operator is written with two positions) |
| **operator** | operator / op | the provider of one evaluation action, such as `css` / `re` / `py`; each operator declares its own argument schema |
| **action** | action | the concrete behaviour of an operator (`css`'s `text` / `@href`, `re`'s `search`); written in **slot 2 (the mode position)** and validated at compile time |
| **value mode** | value mode | the role of **slot 2** for the selector family (`css` / `css1` / `xpath`): `text` / `html` / `outer` / `@<attribute name>` / `nodes` / `self` / `remove`; slot 2 of every other operator is its own behaviour enum, and the argument position is always slot 3 |
| **field chain** | field chain | the ordered list of stages belonging to one output field |
| **field** | field | a key of a field-map product; every result is written into the current `$locals`, and the `_` prefix only keeps it out of the product |
| **product** | product | the value a node produced; a node call returns it as the stage value |
| **product type** | `type` | a chain-tail stage `["type", name]` that validates the value against a host-registered type (`03` §3) |
| **scope** | scope | `globals` (read-only constants) / `locals` (the current scope; a node call shares it) / `public` (the run's shared notes) / `$in` (the node invocation's input) / `$obj` (the stage value) (`03` §8) |
| **freezing** | publish | writing a validated chain into the Store and leaving an audit row |
| **snapshot** | snapshot | the expected product of a chain on a fixed sample input, placed under `tests/snapshots/`; the behaviour contract of the chain |
| **in-place trial** | trial | running a chain locally on a sample input and inspecting intermediate values stage by stage, without writing the store and without network |

---

## 6. Document map

| Document | Role |
|---|---|
| `000-overview.md` (this document) | positioning, the end-state acceptance criteria, goal mapping, scope, glossary, map |
| `001-architecture-and-value-model.md` | layering and invariants, package structure, the value tree, the outcome model and the empty-value rule, export packing, security and resource limits |
| `002-dsl-spec-triples-and-operators.md` | the canonicalisation of the chain stage `[operator, mode, argument]` and the increasing enumeration strength of the slots, reference syntax, the full operator set, allowlisted functions, compile-time error codes |
| `003-parse-chain-spec.md` | the **story** model: `globals` + `nodes`, node bodies (chain / field map), `["node", …]` calls, the chain-tail `["type", …]`, the synchronous `run`, `each` and the field map, materialization and the run-scoped cache, scope, the lint checklist, a complete walkthrough |
| `004-persistence-and-sop.md` | the `Template`/`TemplateAudit` data model, fingerprints, the Store abstraction and its implementations, the `S0–S7` SOP, the counter-example list |
| `005-engineering-workflow.md` | uv dependencies and releases, directory structure, TDD and test layering, documentation-driven development, OpenSpec integration, change-linter, CI |
| `006-trial-ui-design.md` | the pywebview three-column trial UI, single-stage trace, the save-as-snapshot loop, TUI/CLI degradation |
| `007-source-decisions-and-roadmap.md` | adoption/modification/discarding of each source material; the 18 blockers of draft `02` ruled on one by one; the `L1–L4` layered roadmap and acceptance criteria; the open-questions list |

**Reading order**: to learn "what it should look like" read `00`; to learn "how to build it" read `01`; to write chains read `02`+`03`; to freeze chains read `04`; to start writing code read `05`; to see the trial UI read `06`; to learn "why not something else" read `07`.

---

## 7. Open-questions list

**The single source is §4 of `007-source-decisions-and-roadmap.md`** (8 items in total, none of them blocking this stage). Those directly related to this document are four: the package name / CLI name, the minimum Python version, the shape of the trial UI, and when to initialise OpenSpec.
