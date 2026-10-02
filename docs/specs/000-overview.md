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
def start(story: Story, value: JsonValue, *, env: Env | None = None) -> Run: ...
# Story      = a compiled story (the compilation product of the story JSON, `03` §2)
# value      = the first step's input, handed in by the caller; the input is not a role (`03` §2)
# Run        = a resumable run: .next() yields an effect or the final product, .send(answer) resumes
# effect     = {"request": …} | {"call": …}   only these suspend the run (`03` §4)
# product    = JsonValue whose type a step's `type` names (`03` §3); `exit` names the step whose
#              products leave the run
```

| No. | Contract | Description |
|---|---|---|
| **N1** | **Pure function** | same input, same chain → same output; no network, no files, no global mutable state, no implicit input source |
| **N2** | **A chain survives a lossless JSON round trip** | a chain is data, and `dumps(loads(x)) == dumps(x)` holds character for character (absorbing the old design's "tests are the contract") |
| **N3** | **A bad chain fails at compile time** | unknown operator, unknown action, mismatched argument type, dangling reference, cycle, reserved-name collision — all error during `compile()` and never reach runtime |
| **N4** | **A single missing value does not blow up the whole chain** | missing (`Missing`) and failed (`Failed`) are two different meanings, and each has one fixed outcome: missing is "not there" (the key is absent, the item is skipped) rather than a settled empty value, and failed always fails the run with the code of the stage that failed. The settlement policy that made both configurable is retired (`01` §4.2, `D-01-1`) |
| **N5** | **The export is packed by a single function** | any export value must pass through the `export` layer; non-serialisable values such as DOM handles never appear in the export |
| **N6** | **No code capability inside a rule** | a chain cannot reach a host capability: no `import` of third-party code, no file, no network and no process, and custom logic enters through a host-registered named function (`udf`). The **single opt-in exception** is the `code` sandbox (`02` §6.12, `04` §11.3): absent by default, language-level only, and measured to expose no host capability — it is NOT a promise about the words `eval`/`exec` (per-surface table in `04` §11.3) |
| **N7** | **Sequential execution, no DAG scheduling** | a story is a **linear sequence of steps**; a reference can only point at an **earlier** step; there is no join, no in-degree counting and no graph to schedule (`03` §1–§2) |
| **N8** | **Fully synchronous** | no `async`/`await`; a run suspends only by yielding an **effect** back to its caller (`03` §5), which is still synchronous code, and concurrency (if ever wanted) is wrapped around whole runs by the host |

`N1 + N2 + N3` decide the essence of the thing: **zero AI, zero IO, zero nondeterminism at runtime**; AI appears only in the chain-generation phase (see the SOP in `04`).

### 2.1 Deviations from the old design's C1–C3 (confirmed)

The hard contracts C1/C2/C3 of the old `dsl-design` are "the export must be `dict[str, str]`, with every key and every value a `str`". **This design does not adopt them**, for these reasons:

- One of the target products is precisely a **request-specific dict** (`{"url":…, "method":…, "headers":{}, "timeout":30, "body":null}`), which naturally contains dict / int / null / bool and cannot simultaneously satisfy "flat, all str".
- A product is a JSON value whose **type is named** (`03` §3), so a structured export is the norm rather than an exception.
- What is genuinely valuable in the "all str" discipline is **"the export has a single packing point"** and **"the export type is asserted"**, and those two are inherited here in the form of `N5` + the step-boundary type validation.

**Conclusion**: the export is **the product of the step `exit` names**, of the type its `type` names; a collection is a named field of that product. The old "flat `dict[str,str]`" fallback (`produces: "flat"`) is gone with the node model (`03` §12.1).

---

## 3. Four root goals → where they land in the design

| Goal | Where it lands | Carrier document |
|---|---|---|
| **1a Low-code** | chain = JSON data; the compact triple notation; table-driven operators with a unified slot order `[operator, mode, argument]` (enumeration strength increasing across the three positions); an LLM/person only has to remember the two-dimensional "operator × action" table | `02` |
| **1b Safety** | no code capability inside a rule (`N6`), except the opt-in `code` sandbox; an allowlisted function table; registration-based `udf`; references only backwards; resource-limit constants | `01` §8–§9, `02` §6.4/§6.10/§6.12, `04` §11 |
| **1c Stability** | pure functions (`N1`) + full compile-time validation (`N3`) + tri-state errors with fixed outcomes (`N4`) + snapshot regression | `01` §4–§6, `05` §4 |
| **2 An LLM-friendly SOP for persisting parse chains** | the persistence data model for chains (one row per chain + fingerprint auditing) + the Store abstraction + the step-by-step `S0–S7` SOP + deterministic error codes + the counter-example list | `04` |
| **3 Test/OpenSpec/document-driven + uv** | uv manages dependencies and releases; layered pytest (an operator-behaviour dictionary / chain snapshots / end to end); `docs/specs` is the source of truth; OpenSpec takes over changes | `05` |
| **4 No coroutines + an in-place trial page** | fully synchronous (`N8`); `up2 studio` (pywebview three columns + single-step trace + the "save as snapshot" loop), degrading to TUI/CLI when unavailable | `01` §2, `06` |

### 3.1 The order of landing: operators → structure → binding

**First let the parse chain stand on its own, then let it assemble complex structures, and only then bind it to a business identity.**

| Layer | What it does | What it explicitly does not do |
|---|---|---|
| **L1 operator layer** | the value domain / tri-state / references / compile-time validation / export packing; **11 operators** (`css`/`css1`/`xpath`/`json`/`re`/`py`/`udf`/`ctx`/`const`/`each`/`code`, where `time`/`cast` have been merged into `py` and `code` is in `02` §6.12) with all their actions; **the globals/locals design of `ctx`**; **the conformance test set** (every `(operator, action)` has a case) | no multi-field orchestration, no list/nested structures, **no domain names or business keys** |
| **L2 structure layer** | a **story**: a sequence of named typed steps (`parse` = a chain or a field map, `call` = a host function, plus `type` / `next` / `exit`); multi-field orchestration; `each` iteration (a list → one dictionary per element) → arbitrarily nested `list`/`dict`; the two effects (`Request` / `call`) and the suspend/resume run loop; the run-scoped materialization cache; lint; the trial UI | **still no domain names or business keys**; no network requests of its own (it hands a `Request` to the host) |
| **L3 binding layer** | binding a chain to a business identity and freezing it: `root_domain` / `tpl_key`, the Store, fingerprints and auditing, the `publish` gates, the `S0–S7` SOP; a seam example of a host consuming the request dict | — |

**Criterion**: item 5 of the L3 acceptance criteria in `07` §3 requires that "after deleting every concept of `04` from the code, all L1/L2 tests still pass" — that is the mechanically checkable form of "the first two layers have zero business coupling".

**The break in the request part**: a step whose `type` is `Request` only guarantees that "the story can describe the request"; who sends it, how many times, and with which site credentials is entirely up to the host that answers the effect (`03` §4.1). This isolates the request capability and the business binding **simultaneously**, in two directions.

---

## 4. Scope

### 4.1 What is in (the kernel)

1. **The value domain and the evaluation kernel**: the value tree, the tri-state, the operator registry, chain evaluation, export packing (`01`, `02`).
2. **The story specification**: a sequence of steps (`parse` / `call` + `type` / `next` / `exit`), products and type names, the two effects, the suspend/resume run loop, the compile-time lint checklist (`03`).
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
| **chain** | chain / **story** | one complete parsing process, serialisable as JSON; this note calls it a **story** because it is a linear sequence of steps (`03` §1); once persisted, one row = one chain |
| **chain key** | `tpl_key` | the human-readable business name of a chain, unique within a `root_domain`; the caller uses it to reference the chain |
| **step** | step | one unit of execution inside a story: `parse` (a chain or a field map) **or** `call` (a host function), plus `name` / `type`, and `next` on a request step (`03` §2.1) |
| **stage** | stage | one stage of a field chain, i.e. the triple `[operator, slot 2, slot 3]` (a 2-ary operator is written with two positions) |
| **operator** | operator / op | the provider of one evaluation action, such as `css` / `re` / `py`; each operator declares its own argument schema |
| **action** | action | the concrete behaviour of an operator (`css`'s `text` / `@href`, `re`'s `search`); written in **slot 2 (the mode position)** and validated at compile time |
| **value mode** | value mode | the role of **slot 2** for the selector family (`css` / `css1` / `xpath`): `text` / `html` / `outer` / `@<attribute name>` / `nodes` / `self` / `remove`; slot 2 of every other operator is its own behaviour enum, and the argument position is always slot 3 |
| **field chain** | field chain | the ordered list of stages belonging to one output field |
| **field** | field | a key of a step's field-map product; without the `_` prefix it propagates to later steps, with the `_` prefix it is local to this step |
| **product** | product | the value a step produced, referencable by later steps as `$<step key>.<path>` |
| **product type** | `type` | the declared type name of a step's product: a JSON basic name, the built-in `Request` / `RequestBatch`, or a host-registered type (`03` §3) |
| **effect** | request / call | the two things only the host can perform; a run suspends on an effect and resumes with the answer (`03` §4) |
| **scope** | scope | `globals` (the chain-level read-only environment) / `locals` (local to this step) / the products of earlier steps (visible downwards automatically) (`03` §8) |
| **exit** | `exit` | the products of the step `exit` names, collected in order as a list (`03` §9) |
| **freezing** | publish | writing a validated chain into the Store and leaving an audit row |
| **snapshot** | snapshot | the expected product of a chain on a fixed sample input, placed under `tests/snapshots/`; the behaviour contract of the chain |
| **in-place trial** | trial | running a chain locally on a sample input and inspecting intermediate values stage by stage, without writing the store and without network |

---

## 6. Document map

| Document | Role |
|---|---|
| `000-overview.md` (this document) | positioning, the end-state acceptance criteria, goal mapping, scope, glossary, map |
| `001-architecture-and-value-model.md` | layering and invariants, package structure, the value tree, tri-state and policy, export packing, security and resource limits |
| `002-dsl-spec-triples-and-operators.md` | the canonicalisation of the chain stage `[operator, mode, argument]` and the increasing enumeration strength of the slots, reference syntax, the full operator set, allowlisted functions, compile-time error codes |
| `003-parse-chain-spec.md` | the **story** model: named steps (`parse` / `call` + `type` / `next` / `exit`), products and type names, the effects and the run loop, `each` and the field map, materialization and the run-scoped cache, scope, the lint checklist, a complete walkthrough |
| `004-persistence-and-sop.md` | the `Template`/`TemplateAudit` data model, fingerprints, the Store abstraction and its implementations, the `S0–S7` SOP, the counter-example list |
| `005-engineering-workflow.md` | uv dependencies and releases, directory structure, TDD and test layering, documentation-driven development, OpenSpec integration, change-linter, CI |
| `006-trial-ui-design.md` | the pywebview three-column trial UI, single-step trace, the save-as-snapshot loop, TUI/CLI degradation |
| `007-source-decisions-and-roadmap.md` | adoption/modification/discarding of each source material; the 18 blockers of draft `02` ruled on one by one; the `L1–L4` layered roadmap and acceptance criteria; the open-questions list |

**Reading order**: to learn "what it should look like" read `00`; to learn "how to build it" read `01`; to write chains read `02`+`03`; to freeze chains read `04`; to start writing code read `05`; to see the trial UI read `06`; to learn "why not something else" read `07`.

---

## 7. Open-questions list

**The single source is §4 of `007-source-decisions-and-roadmap.md`** (8 items in total, none of them blocking this stage). Those directly related to this document are four: the package name / CLI name, the minimum Python version, the shape of the trial UI, and when to initialise OpenSpec.
