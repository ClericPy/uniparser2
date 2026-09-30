# uniparser2 Design · 07 Source-Material Adjudication and Roadmap

> **Status**: design draft v0.1, now located in `docs/specs/` and committed. **Upstream**: `00`–`06`.
> **What this document answers**: which parts of each of the five source materials are adopted, which are changed, which are discarded; how each of the 18 blockers listed when draft `02` first ran end to end is ruled on; what to build first and what later; and which items still need a human to decide.

---

## 1. Rulings on each source material

### 1.1 The `04` parser-syntax draft (the new template engine's DSL finalization) — the internal source material, not shipped in this repository

**Overall ruling**: **the main trunk is adopted**. The triples, the full operator set, the action-slot encoding, `callback` iteration, and the division of labour between `time`/`ctx` are all kept.

| Disposition | Items |
|---|---|
| Adopt | positional triples `[parser, slot 2, slot 3]` as the **external source of truth** (slot order unified as `[operator, mode, argument]`, see D-02-13); the value-mode set of `css`/`css1` (`text`/`html`/`outer`/`self`/`@attr`/`remove`/`nodes`); the value-mode set of `xpath` (`text`/`nodes`/`self`, used for XML); `json` uses jmespath; the three modes of `re`; time parsing; the `get/set/del/map` of `ctx`; the two states of `callback`, "iterate / whole"; `presets` (formerly `parsers`) sharing the syntax of `fields`; the convention that a `_` prefix means locals; the prohibition on building strings with `:` (this item comes from `01` §6-h, the same origin as the triples) |
| Modify | exact arity matching (D-02-1); multiple arguments become an array/object, comma string-building is abolished (D-02-2); `remove` becomes a pure function (D-02-3); the `callback` selector takes the object form and the container is renamed `presets` (D-02-4); the `ctx` write surface is hard-limited to `locals` and `call` is deleted (D-02-5); the reference syntax converges to one rule and the `$get` reference is abolished (D-02-6); `datetime` is dropped from type conversion (D-02-7); `const`/`getattr` are dropped from the `py` table (D-02-8); `re` capture groups use named objects (D-02-9); allowlist functions are added (D-02-10); `css1` was once deleted and later restored (D-02-11); the bs4 fallback and `any_requires` are deleted (D-02-12); **the slot order is unified as `[operator, mode, argument]`** (D-02-13); **`time`/`cast` are merged into `py`, all `$` are removed, and `re` is renamed `search`/`findall`** (D-02-14) |
| Discard | treating `remove` as a side effect; translating css/xpath into "selector first" (an intermediate form, later **revoked** — the dispute between the two slot orders was closed by unifying the slot order, see D-02-13) |

**Key judgment**: the value of the `04` draft lies in **the enumeration of operators and actions** (it is the normalized checklist of the old v3's 14 parsers), while its **encoding details** (comma string-building, stuffing `|each` into a string, three undefined reference forms) are exactly the root of the R1 disease diagnosed by the old `dsl-design`. Therefore: "keep the semantics, replace the encoding".

### 1.2 The `01` data-structure draft (the new template engine's data structures and chain) — the internal source material, not shipped in this repository

**Overall ruling**: **the main trunk is adopted, with the production coupling stripped off**. The table structure, the auditing, one row per chain, four node types → three, the lint skeleton, and the problem awareness of Q40–Q46 are all inherited.

| Disposition | Items |
|---|---|
| Adopt | the column semantics and invariants of `template` / `template_audit`; `UNIQUE(root_domain, tpl_key)` (Q1); a mutable single version + an audit fingerprint, with no version rows and no pinning (Q1'); audits store only fingerprints and are kept forever (Q18); the initial `dsl_version` of 1; the `status` tri-state; sequential advance, no DAG, no join (Q7); one executor for both kinds of story (Q10); the problem awareness of `parser` prefix dispatch (Q11–Q13); the UDF registry (Q42); field types must be kept under control (Q43); the two-level distinction between `globals` and locals (Q40); the `result` template layer (Q36, Q38); node metadata as embedded JSON only (Q2) |
| Modify | four node types → three (`request` is demoted to an export form, `doc` degenerates into caller input, `03` §1.1); the `referer_info` container → deleted (fields without a `_` prefix are propagated down automatically, `03` §8); `channel/source/region` move from the seed to `const` in `fields` (`03` §8.1); `outputs` deleted (`03` §4.5); `producers=items/three_piece` deleted (the number of products is decided structurally by `select`); `parsers` → `presets`; the `source` enumeration `java/agent/ops` → `human/agent/import` (D-04-2); `id` → `chain_id` (D-04-1); the `actor` source → passed explicitly by the caller (D-04-6); the `:` rule of `tpl_key` → a unified character set (D-04-8) |
| Discard | `task` / `doc` / EOS / Kafka / `tpl_spider` / `resolve_parser_name` — all host-side contracts; `template_run` (Q32, never built in the first place); `request ≤ 2` and its lint; "globals crossing the river by borrowing `doc`" (Q45) — `doc` does not exist, and the act of "crossing the river" disappears with it |
| Not implemented (placeholders) | `variants` (designed first, implemented later, `03` §12); `page` / the pagination cursor (Q31 already settled that there is no pagination write-back) |

### 1.3 The `02` walkthrough example (ah.gov.cn) — the internal source material, not shipped in this repository

**Overall ruling**: **kept as an acceptance case; as a design input it has been fully digested**. Its value is not in the conclusions (it gave none) but in the **blocker list** — ruled on item by item in §2.

**Disposition**: the two `ah.gov.cn` flows are rewritten under the new spec as the two chains of `03` §11 (the collection chain with `on_missing: drop` + the parse chain with `schema: $article`), and are built in **L2** as the **first end-to-end snapshot case**. The ⚠ markers of the original are kept in §2 of this document for comparison.

### 1.4 The `dsl-design` draft (the old project's forward-looking DSL design) — the internal source material, not shipped in this repository

**Overall ruling**: **the discipline is adopted, the surface layer is not adopted, and part of the conclusions are overturned**.

| Disposition | Items |
|---|---|
| Adopt | the D1-c value Tree model; D2 "every operator declares its own argument Schema + compile-time validation + pre-compilation"; D3 "control flow appears only in the form of data" and "conditional branching is left for later"; D4 the tri-state `Ok/Missing/Failed` and the `on_missing`/`on_error` policies; the key/value rules of export packing; the kernel invariants of §3.3 (`core/` has zero third-party code, the export has a single implementation point, the compile product is standalone, operators have no side effects, the result namespace has no reserved keys); the operator behavior migration checklist of §3.4; the staged roadmap of §4 and its discipline that "after P0 is complete you must stop and review once" (its P0 corresponds to **L1** of this design) |
| Modify | the surface syntax: `dsl-design` recommends "named operators as the single source of truth", while this design switches to **triples as the external source of truth + compilation to a named AST** (already decided by the user); the top-level `vars` mechanism → converges into the two levels `globals` + the `seed` product; `iterate`/`NestedRule` → `select` (fan-out) + `callback`/`$map` (explicit expansion) |
| **Overturn** | **C1/C2/C3 "the export must be `dict[str,str]`"**: it directly conflicts with "a dedicated dict for request", and it would force values such as `headers`/`timeout` to be JSON-ified into strings. Changed to "the export is assembled by `result`/`schema` + a single packing point + a serializability assertion" (`00` §2.1) |
| Discard | of the ten surface candidates of §2, only the **spirit** of B (a named AST) and the **shape** of A (triples) are kept; C/D/F/G/H/I/J are no longer independent options (they are encodings of the same AST and can be layered on as sugar in **L4** if needed) |

### 1.5 The `essence` draft (distilled essence of the old implementation) — the internal source material, not shipped in this repository

**Overall ruling**: **the mechanisms are largely adopted, the process is adopted in small part, and the forms are all replaced**. This is the **most actionable** of the five source materials (it carries `file:line` references and measured markers).

| Disposition | Items |
|---|---|
| Adopt | A1 rules as data + a lossless JSON round-trip (**but unknown-field passthrough becomes "an unknown key is a compile error"**, see below); A2 `loads` tri-state idempotence; A4 the shape of a rule == the shape of the output; A9 ambiguity is an error; A10 transactional rule injection; B1 pre-compilation at construction time and idempotence; B3 input normalization unbinds the download layer; B4 the ability to short-circuit a non-http URL (→ the kernel has no network, restated as "input may come from a file / a string"); C the `NotSet` tri-state sentinel; C "tests are contracts" character-by-character assertions; C the library logging conventions; C a missing optional dependency fails early (→ changed to "that operator does not enter the registry"); C batch writes hit disk only once; C configuration from a single point; C rules assembled with zero arguments |
| Modify | A5 protocol-key-driven control flow → explicit fields (`select`/`routes`/`policy`); A7 `__subclasses__` implicit registration → the `@op` explicit registry; B1 `CompiledString` with attached attributes → a standalone compile product (I4); B2 a global mutable `context` → explicit scopes (globals/seed/locals); B5 an error is a value → the tri-state; B6 `return_self` silent fallback → a compile-time unknown-operator error; A6 table-driven → kept, but built on the **class** and exposed through the registry (not through an instance dict) |
| **Must be fixed (the R list)** | R1 ambiguous operator signatures → triples + a named AST (**note**: R1 refers to the three-way ambiguity of v3's `(input,param,value)`; this design's triples are constrained by operator Schemas and are not a reproduction of R1); R3 the compile product hidden in the value domain; R4 an implicit second input source; R5 no type guarantee at the export (→ a single packing point + a serializability assertion); R6 `assert` used for runtime validation → an explicit `raise` + a compile-time Schema; R7 a hard dependency at import time; R8 `startswith('http')` as the protocol test (→ the kernel has no network); R9 retries without backoff (→ the kernel has no network); R10 UDFs are not sandboxed → **a registry, with no code execution inside a rule** |
| Not migrated | every download / rate-limiting / storage / Web UI implementation (the adapter system of `utils.py`, `webui.py`); the `_RECURSION_LIST` boolean flag; the `context` parser; the `curl` interface escaping trick |

**One deliberate divergence from A1 of the `essence` draft**: the `essence` draft says "unknown-field passthrough must be kept (`extra=allow`), otherwise every optional field that v3 carried through `**kwargs` is lost". This design **does not keep unknown-key passthrough** — an unknown key is `UP2-E1005`. Reasons: (a) there is now an explicit Schema, so optional fields should have names; (b) `N3` requires a bad chain to fail at compile time, and silently swallowing a misspelled key (`"on_mising": "drop"`) is exactly the pit the LLM falls into most easily; (c) when extensibility is needed, use `udf` / named schema registration rather than key passthrough.

---

## 2. Item-by-item rulings on the 18 blockers of draft `02`

| Blocker | Original problem | Ruling | Lands in |
|---|---|---|---|
| **A** | `parse` lacks the semantics of "node splitting", so the old `nodes`+`[:20]` has nowhere to live | **valid, fixed**: splitting is promoted to a first-class field `select` (including a continuation stage for truncation) | `03` §4.1, §11.1 |
| **B** | can a chain argument position reference `$node.slot` (affects the task override) | **valid, fixed**: an argument position is judged by the kind in the operator Schema; a `ref_or_literal` position may hold a reference | `02` §3.2, `03` §11.1 |
| **C** | a non-empty `headers` has no place in the collection story | **partially valid, re-attributed**: request headers belong to the **host**; when needed they are assembled by `emit.produces="request"`. The chain itself no longer carries download configuration | `03` §5.2, §11.1 |
| **D** | are `channel/source/region` seed constants or products of list parsing (Q44 and §2.3 contradict each other) | **valid, decided as an either/or**: they are always produced in `fields` as `["const", …]`; `seed` only does injection and materialization | `03` §8.1 |
| **E** | the name of the propagated container was undefined, so `list_title` and `region` landed in different places | **valid, dissolved**: the container concept is deleted — a field without a `_` prefix is propagated down automatically, and there is only one path | `03` §8, §8.2 |
| **F** | a single-route story still had to write `routes` + `default_route` (boilerplate noise) | **valid, fixed**: `routes` may be omitted, and a single target goes straight to `next` | `03` §4.4 |
| **G** | the per-item semantics of `parse` and the origin of `route` were not explicit | **valid, fixed**: the presence of `select` means per-item; `route_field` defaults to `route`; lint checks this statically | `03` §4.1, §4.4, L14 |
| **M** | the old "2 detail + `url_patterns`" has no place (and the two patterns are identical) | **valid, in two steps**: in `L1/L2` split into multiple chains and let the caller choose by URL (an explicit signal); in `L4` reconsider `variants` (a restricted-signal allowlist) | `03` §12, §11.2 |
| **N** | `cast datetime` conflicts with `ArticleItem.pub_time: str` / the encoding contract | **valid, fixed**: `datetime` is removed from the `cast` vocabulary; time belongs to `time` (output `str`); the export type is declared by `schema` | `02` §6.6, §6.7 |
| **O** | the terminal state `parser="none"` conflicts with the dispatch semantics of `resolve_parser_name` | **valid, dissolved**: `emit` is the chain's terminal, and "no further dispatch" is a structural fact; the `parser` field is removed along with the `doc` concept | `03` §1.1 |
| **P** | `inject` read `list_title`, but `ArticleItem` had nowhere to put it | **valid, dissolved**: `list_title` becomes an ordinary field (`$seed-0001.meta.title`); it exists only if declared in the schema, so "read but nowhere to write" cannot happen | `03` §11.2, §7 |
| **Q** | `ctx.globals` spun empty the whole time, so Q45's "borrow `doc` to cross the river" fell through | **valid, fixed**: `globals` (chain-level statics) and the `seed` product (the input of each run) are strictly separated | `03` §3, §8 |
| **R** | the `result` syntax was undefined (three reference forms + an undefined `$get`) | **valid, fixed**: one rule (starting with `$` ⇒ a reference / `{"$lit":…}` escapes / everything else is a literal) + the `$map` directive; `$get` is deleted | `03` §6, `02` §3 |
| **S** | the boundary between `outputs` and `produces`/`result` was unclear | **valid, dissolved**: `outputs` is deleted, and the product contract is derived from the key set of `fields` | `03` §4.5, L11/L14 |
| **T** | `referer_info` is empty during collection; the two propagation paths are mutually exclusive | **valid, dissolved**: a single path (fields without a `_` prefix) | `03` §8.2 |
| **U** | the ctx write-permission boundary and the timing of write-back were undefined | **valid, decided**: the write surface is hard-limited to `locals.*`; there is no concept of "write-back" (the export is assembled by `emit`) | `02` §6.8 |
| **V** | the article row's `list_title` was already lost at `doc_register` | **valid, dissolved**: there is no `doc`/`doc_register`; a field is either in the chain or in `inputs` | `03` §8.3 |
| **W** | the relation between field error policies and the two business gates was undefined | **partially valid, re-attributed**: the kernel produces only the tri-state (`02` §5); "is the trio complete" is a **host** gate, not part of the kernel | `02` §5, `03` §11.2 |

**Summary**: of the 18, **16 are dissolved or corrected at the chain-spec level**, 1 (**M**) is left to `variants` in **L4**, and 1 (**W**) is judged a host concern and explicitly demarcated.

**One further finding beyond the 18**: in §5 of draft `02` the first row of the table is "walkthrough placeholder: all three sections are filled, this row does not exist", and rows 16–19 are **repeated three times** — the blocker summary table of the original has copy-paste residue. This design takes the 18 blockers marked with ⚠ in the body text as authoritative (A–G, M–S, T–W) and ignores the row numbers of the summary table.

---

## 3. Roadmap: operators → structure → binding

**Layering principle (the most important scheduling constraint of this design)**: first make **the parse chain stand on its own**, then let it assemble complex structures, and only then bind it to a business identity.
**L1 and L2 have zero business coupling throughout**: no domain name, no site name and no business key appears in these two layers; `root_domain` / `tpl_key` are not introduced until L3 (`04` §1).

| Layer | In one sentence | Key criterion |
|---|---|---|
| **L1 operator layer** | evaluation and validation at the single-stage / single-field level are complete, consistent and mechanically auditable | every `(operator, action)` in the registry has a case; `up2 conformance --check` exits 0 |
| **L2 structure layer** | chains can be assembled into complex structures producing a `list` / a nested `dict` | the two `ah.gov.cn` chains run end to end and produce 20 nested items |
| **L3 binding layer** | chains are bound to a business identity (domain + key) and frozen | the whole `S0–S7` flow can be followed |

> The original cut the work as "skeleton → semantics", which would make the storage concepts of L3 appear early in both the documents and the code; after switching to "operators → structure → binding", the first two layers can be released and tested independently, and **the chain format never contains a business key** (`03` §2).

---

### L1 · DSL operator layer (build this first)

| Deliverable | Content |
|---|---|
| Engineering scaffold | `pyproject.toml` (`dependencies = []`), `uv.lock`, `src` layout, dev group, ruff/mypy/pytest configuration |
| Kernel | `values` (value domain + `Opaque` + `canonicalize`), `errors` (tri-state + error codes), `limits`, `ast`, `registry` (`@op` + `find_spec` probing), `compile` (stage Schema + action slots + argument kind validation + selector/regex pre-compilation), `evaluator` (single-stage evaluation + tri-state short-circuit), `refs` (reference parsing and evaluation), `export` (the single packing point) |
| **11 operators** (the original was written before `code`; there were 10 before `each`, see "L1 acceptance item status" below) | §2.1–§2.7 of the `04` parser-syntax draft: `css` / `css1` / `json` / `re` / `py` (allowlist functions) / `udf` / time parsing, **the complete behavior of every operator**; plus `xpath` needed for XML, the `ctx` scope operator, the literal `const` and the `each` iteration operator (`time`/`cast` were later merged into `py`, see D-02-14) |
| **The ctx operator** | `globals` read-only + `locals` writable + `get`/`set`/`del`/`map`; a write outside the surface is a compile-time error |
| Error codes | `02` §7 (compile-time `E1xxx`) + §7.1 (runtime `E2xxx`) fully implemented in code |
| **Conformance test suite** | see `05` §4.1: full `(operator, action)` coverage + positive and negative argument-kind cases + engine contract assertions + all error codes |
| CLI | `up2 --version` / `up2 ops --json` / `up2 conformance --check` / `up2 lint` / `up2 trial` (single field, without `--trace`) |
| OpenSpec | `openspec init` + `add-project-scaffold` / `add-core-evaluator` / `add-dsl-triples` / `add-conformance-suite` |

**Acceptance (all of them required, all mechanically checkable)**

1. **`up2 conformance --check` exits 0**: every `(operator, action)` combination declared in the registry has ≥1 case, with no orphan case and no uncovered combination (the mechanism is in `05` §4.1).
2. Each of the three argument kinds (`ref` / `literal` / `ref_or_literal`) has a positive and a negative case; the escaping of a literal starting with `$` (`{"$lit": …}`) has a dedicated case.
3. `ctx`'s `globals` read-only, `locals` writable, and a write outside the surface reporting `UP2-E1015` each have a case; `globals` and `locals` with the same name not overwriting each other has a case.
4. Every error code of `02` §7/§7.1 has a case that triggers it (**an error code without a case equals no error code**).
5. `dumps(loads(x)) == dumps(x)` holds character by character; fingerprints are stable.
6. The runtime dependencies of `pip show uniparser2` are **empty**; no third-party import can be found by `grep` under `core/`; no `async`/`await`.
7. All `css` actions pass semantic assertions on the **real selectolax**, and `xpath` passes namespace/CDATA/case assertions on the **real lxml**.
8. When an optional dependency is not installed, that operator does not enter the registry, `up2 ops` lists the install command, and the package can still be `import`ed.
9. `uv run pytest --cov` is fully green, with `core/` coverage ≥ 95%.

> **After L1 is complete you must stop and review once** (following the discipline of the old `dsl-design` §4): once the operator semantics and the argument Schemas are frozen, assembling structures on top of them costs an order of magnitude more to rework.

### L1 progress (landed this round, measured)

This round started from "build the scaffold + the conformance mechanism first, and run a closed loop with a small number of operators". Completed:

| Item | Status | Measured |
|---|---|---|
| uv scaffold (`pyproject.toml` / `uv.lock` / src layout / dev group) | yes | `uv sync` installs 14 packages; uv picked the managed **CPython 3.13.12** (not this machine's 3.14.3) |
| `core/` (values / limits / errors / ast / refs / registry / compile / evaluator / export / conformance / udfs) | yes | the runtime dependencies are **empty**; `core/` has no third-party import, no IO, no `async` |
| **all 10 operators implemented** | yes | `css` / `css1` / `xpath` / `json` / `re` / `py` (**31 functions**) / `udf` / `ctx` / `const` / `code` (optional sandbox) → **59 `(operator, action)` pairs** (`time` and `cast` were merged into `py` per D-02-14) |
| the `up2` command | yes | `ops --json` / `conformance --check` / `lint` / `trial` (including `--global` / `--product` / `--on-missing`) |
| conformance audit | yes | **59 declared pairs = 59 covered pairs**; **all 25 implemented error codes have cases**; `up2 conformance --check` exits **0** |
| tests | yes | `uv run pytest` → **306 passed, 3 skipped** |
| static gates | yes | ruff format/lint pass, C901 complexity pass, ty pass, pyrefly pass, pyright pass, `mypy --strict` pass (51 files), bandit pass |
| dependency vulnerability audit | yes | `uv export` (with hashes) + `pip-audit --disable-pip` → **No known vulnerabilities found**. The script's own `--locked` route does not recognize `uv.lock`, and this is written into CI using the former command |

**The optional dependencies are installed, and every verification gap is closed**:

| # | Item | Result |
|---|---|---|
| 1 | `css` engine contract assertions | yes — all green on the real selectolax. Two real API facts were caught along the way: selectolax 0.4.12's `Node` **has neither `clone()` nor `outer_html`** (`node.html` is the outer HTML); inner HTML can only be assembled from the direct children of `iter(include_text=True)` |
| 2 | real jmespath integration | yes — the `data.list[*].url` projection and "not found ⇒ `Missing`" both pass |
| 3 | real dateparser (natural language) | yes — branches such as `2026\u5e749\u670826\u65e5` pass |
| 4 | `core/` coverage ≥ 95% | yes — **98.3%** (`compile`/`registry`/`values`/`udfs`/`conformance`/`export` are all 100%); the gate is frozen as `uv run pytest --cov=uniparser2.core --cov-fail-under=95` |
| 5 | XML support | yes — the `xpath` operator (lxml) was added. Measurement confirmed that selectolax cannot serve as an XML parser, while lxml alone has no CSS selector (`lxml.cssselect` needs an extra `cssselect`) — XPath is a native lxml capability, so XML goes through XPath, without adding `cssselect` and without needing bs4 |
| 6 | the necessity of `css1` | yes — **once deleted, restored after measurement**: making both cardinalities explicit is safer (defaulting to the first + an `all` switch would silently truncate); in L1 `nodes` cannot take on "fetch all values" (it has only handles, and getting text waits for the L2 fan-out); `css_first` is not a fast path, its gain is skipping the extraction of N-1 copies. See `02` D-02-11 |
| 7 | the slot-order dispute over triples | yes — closed as **D-02-13**: the slot order is unified with zero exceptions as `[operator, mode, argument]` (the css/xpath selector lands in slot 3, the `re`/`ctx`/`py` mode is in slot 2, `json`/`const` are written with two entries); the intermediate flip to "selector first" has been **revoked** |
| 8 | whether `time` / `cast` deserve standalone operators | yes — closed as **D-02-14**: both are merged into `py` (`parse_time` / `str`·`int`·`float`·`bool`·`list`·`from_json`), all `$` prefixes are removed, and `re`'s `$match`/`$all` are renamed `search`/`findall`. The operator count went from 11 down to **9** |

**Cross-engine semantic difference (found only after installing the packages, already normalized)**: under selectolax, `text` **includes** the text of `<script>`/`<style>`, while under bs4 it does not. Since engine-independent behavior is promised, this is unified in the adapter layer: first cut `script`/`style`/`noscript` on a **copy**, then take the text (consistent with the noise set of `remove` in the `04` parser-syntax draft), and write this semantics into `02` §6.1. **Note**: after deleting bs4 this normalization is **still necessary** — selectolax brings those texts along itself, and we do not want them.

**The `md` extra switched packages**: the original wrote `markdownify`, and measurement switched it to **`html-to-markdown`** (`convert(html).content`, no base_url), so `py.html_to_markdown` accepts no arguments — both the argument table and the install hint were updated accordingly.


**Spec items added/converged while implementing this round** (already back-filled into `02`): the cardinality split between `css`/`css1` (`css` yields a `list`, `css1` yields a scalar; the job of `nodes` is to hand off to the L2 fan-out rather than to fetch all values), nodes are always wrapped as `DomNode(Opaque)`, and a list input reports `E2002`; the `xpath` action set (no `@attribute` value mode, diagnostics for the silent pit of default namespaces, a compile-time trial run on an empty document, no `xpath1` for now); the dynamic action space of `udf` declares contract coverage with `("*")`, and its argument names are not Schema-validated; `py.parse_time` has no required dependency, `format` is validated at compile time, `tz` is deleted; the exact semantics of the `""` placeholder (it means "pass no argument" only when there is no required argument); **the slot order is unified as `[operator, mode, argument]`** (D-02-13) and **`time`/`cast` are merged into `py`, with `$` removed** (D-02-14).


**L1 acceptance items, item by item, current status**:

1. `up2 conformance --check` exits 0 — yes, **59 declared pairs = 59 covered pairs** (all 10 operators included).
2. every `(operator, action)` has a case — yes (`udf` declares contract coverage with `("*")`).
3. positive and negative argument-kind cases — yes (`ref` is covered by a patch that "temporarily changes `urljoin.base` to `Kind.REF`", because L1 has no ref-only argument).
4. `globals` read-only / `locals` writable / a write outside the surface reports `E1015` — yes.
5. every implemented error code has a case — yes (23/23).
6. `dumps(loads(x))` is a character-by-character fixed point — yes.
7. zero runtime dependencies / `core` has no third party / no `async` — yes.
8. when a dependency is missing the operator is unavailable and the install command is given — yes (with selectolax / lxml not installed, `up2 ops` shows `[unavailable]`, and compile time reports `E1107`).
9. **`css`/`css1` engine contract assertions** — yes, all green on the real selectolax (`text` excludes the noise tags, inner/outer HTML, `remove` works on a copy, first vs all).
10. `core/` coverage ≥ 95% — yes, **98.3%**, and the gate command is frozen (`--cov=uniparser2.core --cov-fail-under=95`).

---

### L2 · Structure layer (assembling complex structures)

| Deliverable | Content |
|---|---|
| Field-chain orchestration | multi-field sequential evaluation, cross-field `locals` references, chain-level/node-level/field-level overrides of `on_missing`/`on_error` |
| **Lists and nesting** | `each` iteration (one dictionary per element, with the per-element scope), `result` templates, `$lit` escaping, arbitrarily deep nested `dict`/`list` |
| Chains and the export | the three node types, the executor, `routes` dispatch, `emit`'s `flat` / `record` and **per-item products**, the built-in `$request` structure (assembled only, never sent) |
| schema | the own restricted Schema validator + `register_schema` |
| lint | every live rule of `03` §10, each with at least one test (L20 is retired with `presets`) |
| trace | `up2 trial --trace --json` (the data structure of `06` §5.1) |
| trial bench | `up2 studio` (pywebview three-column + trace + save as a snapshot), with TUI/CLI fallback |
| cases | the two `ah.gov.cn` chains (`03` §11) + samples + snapshots; a set of "pure structure" chains (multi-level nesting, a list of lists, a list turned into a dict) |

> **Iteration redesign (change `l2-chain-structure-and-each`, landed in the operator layer)**: the `select` fan-out, the `callback` operator with its `presets` container, the `$map` template directive and the `item` scope root were **retired in favour of one operator, `each`** (`02` §6.9, `03` §4.1). It takes the list the stage above produced plus an **inline field map** (`field name → chain`, the same shape a node's `fields` has) and yields one dictionary per element; a `_`-prefixed field name is a local of that element, and every element is evaluated in its own child scope. `$item` is gone because the element is simply the input value of each field chain, and lint L20 is retired with the container. Implemented in the operator layer: 61 `(operator, action)` pairs, 26 error codes, `MAX_EACH_DEPTH` / `MAX_EACH_ITER` (`01` §9).

**Acceptance**

1. It can produce and snapshot: `list[dict]` (a list page with 20 items), a `dict` containing a `list[dict]` (two or more levels of nesting), a list turned into a `dict` (`ctx.map`), and the `request` structure (`produces:"request"`).
2. The `ah.gov.cn` collection chain produces 20 items on a real page fragment; the parse chain produces a single record conforming to `$article`.
3. Each "fixed" blocker among the 18 of draft `02` has a corresponding test (**named item by item**, see §2).
4. All 22 behavior tests of the old v3's `test_parsers.py` pass in the form of a "behavior dictionary" (API compatibility is not required).
5. Each live lint rule of `03` §10 has a positive and a negative case (L20 is retired).
6. All 7 UI acceptance items of `06` §10 pass, among which "works with the network down" must be tested under a real network disconnection.
7. A chain of 500 items × 20 fields finishes within 3 s (`05` §4.4).
8. **Disproof**: no domain name or business key appears as an **engine concept** in any L1/L2 case (it appears only as an ordinary value of the caller's `inputs`).

---

### L3 · Binding layer (build this last)

| Deliverable | Content |
|---|---|
| Store | the `TemplateStore` protocol + `FileStore` + `SqliteStore` + fingerprints + auditing; `root_domain` / `tpl_key` are introduced for the first time |
| publish gate | G1 mandatory lint, G2 snapshot regression, G3 coverage confirmation, no-op detection, `--skip-tests` leaving a trace |
| SOP | `up2 snapshot` / `up2 test` / `up2 get` / `up2 list` / `up2 audit` / `up2 doctor`; `04` §7 written as an executable document |
| host seam | a "consume the request dict" example (`emit.produces="request"` → the host HTTP layer); a "host implements TemplateStore (MySQL) + dispatches by key" example |

**Acceptance**

1. The whole `S0–S7` flow can be followed from the document, and every step's command passes when actually run.
2. Re-publishing the same `graph` produces no audit row; a bad chain is refused and leaves no residue (tested once for each of the SQLite and the file Store).
3. `up2 doctor` can detect "a chain without an audit" and fix it with `--fix`.
4. The audit chain can answer "who changed which chain to which fingerprint and when".
5. **Regression assertion**: after deleting every concept of `04` from the code, the L1/L2 tests **still all pass** (proving that the first two layers really have zero business coupling).

---

### L4 · Extensions (on demand, not presupposed)

| Item | Trigger condition |
|---|---|
| `variants` (multi-shape field variants) | the maintenance cost of "splitting into multiple chains" on real sites proves too high |
| the full TUI form | the real usage frequency of the trial bench proves it worth the investment |
| the surface sugar of `dsl-design` (text pipeline / output template) | the input cost of hand-written JSON becomes a bottleneck; and it must be a 1:1 compilation of triples that introduces no second semantics |
| batch trial runs (a thread pool wrapping `run()`) | N samples need to be validated in one go |
| an adapter layer that issues requests itself | when the user explicitly wants `uniparser2` to issue requests itself (currently a deliberate break point, see `03` §5.2) |

---

## 4. Open-questions list

| # | Open question | Impact | Recommendation |
|---|---|---|---|
| **a** | whether the PyPI package name `uniparser2` is available; whether the CLI name `up2` is acceptable | `05` §7 packaging and release | check PyPI once before release; if it is unavailable, change the distribution name to something like `uniparser2x` but keep the import name if possible |
| **b** | the Python lower bound is set to `3.12` (this machine has 3.14.3) | `pyproject.toml` and the CI matrix | 3.12 is recommended; supporting 3.10/3.11 would mean giving up `type` statements and some `match` forms, which is not worth it |
| **c** | whether the trial bench also implements a TUI | `06` §7, `L2` effort | it is recommended to build only pywebview + CLI first and leave the TUI until a real need appears |
| **d** | when to initialize OpenSpec | `05` §5.2 | it is recommended to **init at the very start of `L1`** (changes and capabilities aligned from the operator layer on) rather than waiting for the scaffold to be complete |
| **e** | whether the import name and the old `uniparser` need to coexist in the same environment | `01` §1.2 | coexistence is not recommended; if it is unavoidable, `uniparser2` and `uniparser` have no naming conflict (different top-level packages), so no special handling is needed |
| **f** | whether an integrated orchestration of "collection chain → parse chain" (`run_pipeline`) is needed | `03` §8.3 currently loops in the caller | not recommended: the kernel keeps "one `run`, one chain"; integrated orchestration belongs to the host |
| **g** | whether `variants` should be brought forward | `03` §12 | keep it at `L4`; first validate the cost of "splitting chains" on real sites |
| **h** | the own restricted Schema language vs adopting JSON Schema directly | `01` §6.1 | the own vocabulary is recommended (both the LLM generation cost and the error-message quality are better); if integration with external tooling is needed later, add a JSON Schema converter |

**Resolutions** (settled with the project owner; this list is what allowed the design notes to be
migrated into `docs/specs/`, per `05` §5.4):

| # | Resolution |
|---|---|
| **a** | **settled** — the PyPI name `uniparser2` is available, and the CLI name `up2` is accepted. |
| **b** | **settled** — the Python floor stays `3.12`. |
| **c** | **settled** — no TUI for now; the pywebview trial bench stays a preliminary plan (`06` keeps its draft status). |
| **d** | **settled** — OpenSpec is initialized in this repository (`openspec/config.yaml`); the change `add-code-sandbox-operator` has been archived (`openspec/changes/archive/2026-09-29-add-code-sandbox-operator/`) and its `code-execution` capability merged into `openspec/specs/code-execution/spec.md`. |
| **e** | **settled** — coexistence with the old `uniparser` is not needed (the two projects are essentially unrelated). |
| **f** | **settled** — no integrated orchestration for now; keeping "one `run`, one chain` stands, and turning a chain's output into a `request` structure before sending it remains a host concern to be thought through later. |
| **g** | **settled** — `variants` stays reserved at `L4`; revisit once real sites show that splitting chains costs too much. |
| **h** | **deferred by choice** — the parameter Schema language will be reconsidered later (candidates named: `pydantic` / `msgspec`); until then the own restricted vocabulary stands. |

---

## 5. Completion criteria for this stage (design)

| # | Criterion | Status |
|---|---|---|
| 1 | each of the five source materials is given its adopt/modify/discard decision and the reasons | yes — §1 of this document |
| 2 | each of the 18 blockers of draft `02` is ruled on with its landing place named | yes — §2 of this document |
| 3 | each of the four root goals has an explicit carrier document | yes — `00` §3 |
| 4 | the three conflicts — the export contract, the DSL source-of-truth syntax and the kernel scope — are ruled on | yes — `00` §2.1, `02` §8, `03` §1 |
| 5 | every layer has a mechanically checkable acceptance standard | yes — `05` §9, §3 of this document, `06` §10 |
| 6 | the open-questions list converges to 8 items or fewer and none of them blocks | yes — §4 of this document |
| 7 | **L1/L2 zero business coupling has a mechanically checkable criterion** | yes — §3 of this document (the L1 criterion + L3 acceptance item 5, "after deleting `04` the first two layers' tests are still all green") |
| 8 | "all syntax is complete and consistent" has a mechanically checkable criterion | yes — `05` §4.1 (`up2 conformance --check`) |
| 9 | after finalization it can be migrated into `docs/specs/` + `openspec/changes/` without ambiguity | **done** — all 8 notes live in `docs/specs/`, §4 is resolved (see the resolutions table above), and both changes have been archived and merged: `openspec/specs/code-execution` (10 requirements) and `openspec/specs/time-parsing` (3), each passing `openspec validate --specs` |
