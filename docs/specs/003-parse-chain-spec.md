# uniparser2 Design · 03 Parse Chain Spec

> **Status**: design draft v0.1, now located in `docs/specs/` and committed. **Upstream**: `00`, `01`, `02`.
> **What this document answers**: which nodes a chain is made of, how data flows, how `each` turns a list into one dictionary per element, how `result` assembles the export, and what counts as a bad chain.
> **Structural changes relative to `docs/specs/001-architecture-and-value-model.md`**: the four node types (`seed`/`request`/`parse`/`doc`) converge into **three** (`seed`/`parse`/`emit`) —
> `request` is demoted from a node type to an export shape (§1.1), and `doc` degrades from a host concept to a caller input (§8.3).

---

## 1. The contracts of the three node types

| Type | Consumes | Produces | Notes |
|---|---|---|---|
| `seed` | the caller's `inputs` | **the injected input dictionary** (the keys declared by `inject`) | the only place that can materialize `bytes`/`str` into structure |
| `parse` | `input` (an explicit reference) | **one** field dictionary; a list becomes one dictionary per element only where a field chain says so with `each` | the only place that runs field chains |
| `emit` | upstream products | **the export value** (`record` / `flat` / `request`) | the chain's terminal; assembled with `result`, validated with `schema` |

"Product types" such as `article` / `file` are **not node types**; they are the names of export `schema`s (§7).

### 1.1 Why `request` is demoted from a node type

In draft `01`, the `request` node carries the semantics of "assembling one HTTP request" and comes with a string of special-case lints (at most 2 of them, only on a linear path after the seed, never on a fan-out path). In the uniparser2 kernel:

- the request **structure** is just a piece of export data (`{"url":…, "method":…, "headers":…}`), and assembling it is the job of `emit`;
- "whether it may be sent, how many times, whether to bypass hotlink protection" is the **host's** concern (the kernel sends no requests; see `01` §1.1-I5 and `00` §4.2);
- treating a structure as a node type would force the executor to branch for it, violating "no special structures".

**Conclusion**: `produces: "request"` is one export shape of `emit`; the `request ≤ 2` lint from draft `01` is deleted along with it (it constrains host behaviour, not the validity of a chain). This is exactly where the requirement "sometimes the output is a request-specific dict" lands.

---

## 2. The JSON structure of a chain

```jsonc
{
  "dsl_version": 1,                        // chain structure version; bumped only on a structural change
  "entry": "seed-0001",                    // entry node key (required, must be of type seed)
  "output": "auto",                        // auto | single | list (§5.3)
  "globals": { "base_url": "https://…" },   // chain-level **static** environment (optional; read-only)
  "policy": { "on_missing": "empty", "on_error": "raise" },   // chain-level default policy (§4)
  "nodes": [ /* seed / parse / emit */ ]   // keys unique, not reserved names
}
```

| Field | Required | Description |
|---|---|---|
| `dsl_version` | yes | an integer, initial value `1`; bumped only when the **node structure** changes (changing fields or selectors does not bump it). Draft `01` considered YYMMDD and settled on an integer because there is no legacy migration requirement |
| `entry` | yes | entry node key; must be of type `seed` (lint L2) |
| `output` | no | the export aggregation shape, `auto` by default |
| `globals` | no | the chain-level **static** environment (such as `base_url`); strictly separate from "the input of each run" (§3) |
| `policy` | no | the chain-level default policy |
| `nodes` | yes | the node array; **the execution order is decided by the graph structure**, and array order affects only how products are concatenated when there are multiple terminals (§5.4) |

> **The chain format holds no business identity**: no domain, no site name, no business key, no `tpl_key`, no `root_domain`. Those are identifiers the **L3 binding layer** (`04` §2) adds on the storage side, and the chain data itself does not know them (the layering principle of `07` §3). Site-specific concrete values (`base_url`, `channel`) appear only as `globals` constants or as ordinary values in the caller's `inputs`.

---

## 3. The `seed` node: the input contract

```jsonc
{
  "key": "seed-0001", "type": "seed",
  "config": {
    "inject": ["text", "meta"],   // allowlist: which keys are taken from the caller's inputs
    "input_format": "html"        // html | xml | json | text; applies only to the primary input key `text`
  },
  "next": "parse-0001"
}
```

| Field | Required | Description |
|---|---|---|
| `inject` | yes | the list of key names in the caller's `inputs` that this chain is allowed to reference. **A key that is not injected cannot be referenced at compile time** (`UP2-E1006`) |
| `input_format` | no (default `text`) | how the primary input is materialized: `html`/`xml` ⇒ an `Opaque` document; `json` ⇒ the parsed value; `text` ⇒ the `str` as it is |

**Product**: one dictionary whose keys are exactly the keys declared by `inject`. Downstream nodes reference them as `$<seed key>.<key>` (`$seed-0001.text` / `$seed-0001.meta.url`).

**`text` is the conventional slot for the primary input**: `input_format` applies only to it. If the caller's primary input goes by another name, it is passed as `{"text": …}` at `run()` time — a conventional slot is cheaper than a new config item, and it leaves exactly one answer to "which input gets materialized".

**The division of labour between `globals` and `seed` (the part of this document most often misread)**:

| | Content | Source | Lifetime |
|---|---|---|---|
| `graph.globals` | chain-level **static** constants (`base_url` and the like) | the chain data itself | permanent |
| the `seed` product | the **input** of each run (`text`, `meta`, and so on) | the caller's `run(chain, inputs)` | one run |

The two are **neither merged nor share a name**. Draft `01` called both globals, which made draft `02` run into "`ctx.globals` idles empty all the way through" while walking the example (blocker Q) — because the injected values were treated as globals while existing only on the doc carrier. This design separates the two completely with "static globals + seed product".

**The input allowlist is a security boundary**: a chain can see only the keys declared by `inject`, which makes "no implicit input source" (`N1`) a statically checkable property (lint L13).

---

## 4. The `parse` node

```jsonc
{
  "key": "parse-0001", "type": "parse",
  "config": {
    "input": "$seed-0001.text",                  // required; references a value that already exists
    "format": "html",                            // optional; materializes a str input once more (the json→html fragment scenario)
    "policy": { "on_missing": "drop" },          // optional; overrides the chain level
    "fields": { /* §4.2; a field chain may end in ["each", {…}] for per-item parsing (§4.1) */ },
    "route_field": "route"                       // optional, defaults to "route"
  },
  "next": "emit-0001"                            // mutually exclusive with routes (§4.4)
}
```

### 4.1 Per-item parsing: `each` (the ruling on blocker A of draft `02`)

Draft `02` points out that draft `01` **dropped the whole layer** of the legacy rule's `nodes` (split the chain first, then extract values per item, with `[:20]` truncation): if the first stage of `fields` is `["python","getattr","attributes"]`, the object being evaluated is the whole document rather than a single `<a>`, so the result is necessarily wrong.

The layer is back as **one operator inside a field chain** (`02` §6.9), not as a node-level field:

```jsonc
"rows": [["css","nodes","li"], ["py","slice",":20"], ["each", {"title": [["css1","text","a"]]}]]
```

| Rule | Content |
|---|---|
| `fields` itself | always evaluated **once** on `input` and always produces **one** dictionary — the node has exactly one product shape |
| `each` in a field chain | its input must be a list (here: the node set the stage above produced); the result is one dictionary per element, so that field holds `list[dict]` |
| Truncation/sorting | ordinary stages **before** `each` (`["py","slice",":20"]` above); limiting how many elements become records is a plain list operation |
| Empty collection | `each` on an empty list yields an empty `list` (not `Missing`) — an empty list page is a normal result |
| Exporting the list | the list is a **named field**, so `emit` names it: `{"produces": "flat", "field": "rows"}` (§5.1) |

The nested `each` (a field map inside a field map) is legal up to `MAX_EACH_DEPTH`, and the whole field-map argument is compiled recursively, so a mistake inside it is reported at compile time with a pointer that reaches the offending stage.

### 4.2 `fields`

Field definitions and evaluation semantics are in `02` §5. The key points restated:

- a key **without a `_` prefix** ⇒ travels down with the node's product and can be referenced by later nodes;
- a key **with a `_` prefix** ⇒ local to this node (`locals`): **referenceable inside this node, while a cross-node reference yields `UP2-E1014`**;
- fields are evaluated in declaration order, and a later field may reference earlier `_` local values — inside an `each` field map the same rule holds **per element** (the two paragraphs below).

**The `_` prefix inside `each`'s field map**: such a key is stored in the element's locals, later fields of the same element read it as `$locals._name`, and it never appears in the element's dictionary. So "compute something for two fields, `each` it once" needs no relay field and no extra container.

**Scope inside `each`**: every element is evaluated in its own child scope; reads fall back outward (the element's locals, then this node's locals, then the chain-level values), writes stay in the element, and the element's locals do not outlive the element. There is no iteration variable to name — the element is the input value of every field chain.

**`$fields` is shorthand for this node** (including this node's `_` keys) and is valid only inside the node that defines `fields`; an `emit` node has no `fields`, so it must write `$parse-0001.<key>`. **A node cannot reference its own key** (`$parse-0001.x` written inside `parse-0001`'s own `fields` ⇒ `UP2-E1006`, whose message should point to `$fields.x`). These two are the mistakes chain authors make most often, and the `UP2-E1006` message must say so explicitly.

### 4.3 `presets`: removed

Preset chains existed only to give `callback` a name to call. With `each` the field map is **inline**, so the container, the name-resolution pass and the "presets cannot reference one another" rule went with it: there is nothing left to name, and the identity "the argument is the same shape as `fields`" is visible at the use site rather than hidden behind a jump.

> **Deviation record D-03-1** (superseded by the L2 iteration redesign, change `l2-chain-structure-and-each`): draft `04` used `parsers` as the container name and this design renamed it `presets`; both names are now retired with the container. If reuse is ever wanted, it belongs to a **callable stage** (a named chain used like any other stage), never to a second argument shape of `each`.

### 4.4 `next` and `routes`

| Field | Description |
|---|---|
| `next` | advance unconditionally to the next node |
| `routes` | dispatch by the `route` value of each product: `{"article": "emit-article", "file": "emit-file"}` |
| `default_route` | **required** when `routes` is present; where a `route` value that matches no key lands |

**The two are mutually exclusive** (`UP2-E1101`).

> **Ruling (on blocker F of draft `02`)**: `routes` **may be omitted**. When there is only one downstream path, write `"next": "emit-0001"` directly; the "single-key `routes` + `default_route`" boilerplate is no longer mandatory. The former lint 5c of draft `01` ("a collection chain's parse must have routes") is void along with it — it has no corresponding constraint in the kernel.

### 4.5 Deleted fields

| Deleted | Reason |
|---|---|
| `outputs` | in a sequential execution model the "consumer-side contract" is **derived automatically from the set of field keys** (the lint just checks the `fields` keys of preceding nodes); an explicit declaration is only a redundant second source of truth. This also dissolves blocker S of draft `02` (the unclear boundary between `outputs`/`produces`/`result`) |
| `produces` (formerly carried by parse) | the shape of each product is decided by `fields`; the chain's product shape is decided by `emit.produces`. parse no longer declares a product shape |
| `input_format` (formerly on parse) | renamed to `format` and made optional: materializing the primary input belongs to `seed`, secondary materialization belongs to `parse.format`. One semantics, no duplicate declaration |

---

## 5. The `emit` node and the export

```jsonc
{
  "key": "emit-0001", "type": "emit",
  "config": {
    "produces": "record",                 // record (default) | flat | request
    "field": "rows",                      // only with produces=flat: which field's value is the export
    "schema": "$article",                 // optional; a named schema or an inline description
    "result": { /* the §6 assembly template */ },  // omitted when produces=flat
    "policy": { "on_missing": "drop" }
  }
}
```

| `produces` | Semantics | `result` |
|---|---|---|
| `record` (default) | assembles one structured product with the `result` template | required |
| `flat` | no assembly; the upstream visible fields are the product directly (the "fall back to flattening the loose fields" of Q36 in draft `01`). With `field`, that one field **is** the export — the shape a per-item list needs, since `each` puts the list under a name (§4.1) | must be omitted |
| `request` | assembles per the built-in request structure and **fills in defaults automatically** | optional (when omitted, keys are taken by name directly) |

### 5.1 The place of `flat`

`flat` is the "default stated plainly": drafts `01`/`04` already settled on "fall back to flattening the loose fields when there is no `result`" (Q36), and this design keeps it as an explicit shape. But it carries **no** `dict[str,str]` typing promise — `int`/`list`/`null` in the value domain leave as they are (see `00` §2.1).

**`flat` + `field` is the export of a list**: `{"produces": "flat", "field": "rows"}` exports the value of `$parse-0001.rows`, which is exactly what `each` produced — one record per item. There is deliberately no "the single key is the export" rule: which field is the product is written down, in the same spirit as `route_field`.

### 5.2 The built-in structure of `request`

With `produces: "request"`, the product is assembled per the built-in schema `$request` with defaults filled in:

| Key | Type | Default |
|---|---|---|
| `url` | `str` (required) | — (missing ⇒ `Failed` `UP2-E2010`) |
| `method` | `str` | `"GET"` |
| `headers` | `json` | `{}` |
| `params` | `json` | `{}` |
| `body` | `json` | `null` |
| `timeout` | `float` | `30.0` |
| `follow_redirects` | `bool` | `true` |

**The kernel only assembles; it never sends.** Once the host holds this dict, it decides for itself which HTTP client to use, whether to add hotlink-protection headers, and whether to go through a proxy.

> **This is a deliberate seam between the kernel and the business**: `produces:"request"` guarantees that "a chain can describe a request", while "who sends it, how many times, and with what site credentials" is left entirely to the caller. L1/L2 therefore only produce this dict and assert its structure, and **neither need nor permit** any network access; L3 is where the seam example "the host consumes a request dict" appears (`07` §3).

### 5.3 `graph.output`: the export aggregation shape

| Value | Semantics |
|---|---|
| `auto` (default) | the terminal evaluates once ⇒ its product is returned directly; fan-out or multiple terminals ⇒ a `list` is returned |
| `single` | there must be exactly one terminal and it must evaluate once, otherwise `Failed` at runtime (`UP2-E2011`) |
| `list` | always returns a `list` (a single item is wrapped in one layer as well, so the caller consumes it without branching) |

**Why it is needed**: a chain's export type differs between "one list page → N items" and "one article → 1 item"; making the chain **declare it explicitly** frees the caller from guessing.

### 5.4 Terminal nodes

- a chain has **at least one** terminal (a node with neither `next` nor `routes`); zero terminals ⇒ `UP2-E1103`.
- with multiple terminals the products are concatenated in **the order in which the nodes appear in the `nodes` array** (the only semantic effect of array order).

---

## 6. The `result` assembly template

A `result` is a tree whose leaves are evaluated by the reference rules of `02` §3, and the shape of the root is the shape of the export.

```jsonc
"result": {
  "item_type": "article",                              // literal
  "url":       "$seed-0001.meta.url",                   // reference (injected by the seed)
  "title":     "$parse-0001.title",                     // reference (a preceding node's product)
  "pub_time":  "$parse-0001.pub_time",
  "channel":   "$parse-0001.channel",
  "tags":      ["$parse-0001.tag1", "\u56fa\u5b9a\u6807\u7b7e"],   // array: evaluated element by element
  "related":   "$parse-0001.rows",                      // a list of records, already built by `each` (§4.1)
  "note": {"$lit": "$\u5f00\u5934\u5c31\u8981\u8f6c\u4e49"}          // directive: literal escaping
}
```

| Form | Behaviour |
|---|---|
| Object | a recursive template; keys are kept as they are |
| Array | recursive evaluation element by element → `list` |
| String | the value-position kind is `ref_or_literal`: starting with `$` ⇒ a reference, otherwise a literal |
| `{"$lit": v}` | produces `v` (used for literals that start with `$`) |

- **Per-item structure is built in `fields`, not here**: a list of records comes out of `each` (§4.1), and a `result` merely references the field that holds it. There is no template-level iteration directive — that is exactly what the retired `$map` was, and it put a second iteration mechanism (with its own name resolution, depth limit and error class) next to the operator that already existed.
- when a value is `Missing`, it lands per `emit.policy` (default `empty` ⇒ `""`).

> **This is the direct answer to blocker R of draft `02`**: the `result` of draft `04` exhibited three undefined forms (`$fields.*`, `$seed-0001.<multi-level path>`, and a pure literal) plus a `$get` that was never defined. This design fixes the three categories "reference / literal / directive" once and for all; `$get` is deleted, and `$lit` is now the only directive.

---

## 7. Schema

| Source | Usage |
|---|---|
| Built-in | `$request` (§5.2) |
| Registered | the host calls `register_schema("$article", spec)` (`04` §7) |
| Inline | write the description straight into `emit.config.schema` |

The description language is in `01` §6.1 (`str`/`int`/`float`/`bool`/`json` + `?` optional + `[...]` list + `{...}` nesting).

---

## 8. Scope and "downward propagation" (convergence of Q40–Q46 in draft `01`)

Draft `01` leaves four things unconverged here: the definition of `ctx.globals`, the mutual exclusion between `Q44` and `§2.3`, the `referer_info` name pending removal, and `doc` as an information bonanza (`Q46`). This design converges them into **two sources + one automatic rule**:

| Source | Lifetime | Read/write |
|---|---|---|
| `globals` | the whole chain | read-only (only the static constants of `graph.globals`) |
| the `seed` product | the whole chain | read-only (this run's input, the `inject` allowlist) |
| `locals` | the current node | writable (`ctx.set`/`del` are limited to `locals.*`, that is, `_`-prefixed fields) |
| a node product | from that node to the end of the chain | read-only; **fields without a `_` prefix join automatically** |

**Downward propagation needs no new concept**: under sequential execution, fields without a `_` prefix are naturally referenceable by later nodes; during fan-out each product carries its own copy.

### 8.1 Where `channel` / `source` / `region` land (the ruling on blocker D of draft `02`)

Draft `01`'s `Q44` says they are "products of list parsing, passed down with the item", while `01 §2.3` treats them as "product fields of a collection-style seed"; the two are mutually exclusive (already pointed out as blocker D of draft `02`).

**Ruling: always produce them in `parse.fields` with `["const", …]`; `seed.config` does not hold these three.**

Reasons:
1. the judgement of `Q44` is right — they really are values that "each product carries itself", and a `const` chain expresses that precisely;
2. when one chain serves several channels, different `parse` nodes can give different `const` values, which is more direct than putting one copy in the seed and then finding a way to copy it onto every product;
3. putting another copy in the seed creates the ambiguity of "which one is the truth" (the seed contract of `01 §2.3` versus `Q44`), and that is exactly where draft `02` got stuck first while walking the example;
4. the `seed`'s responsibility converges to "inject + materialize", a single semantics.

### 8.2 Things that do not exist (explicitly deleted)

| Deleted | Replacement |
|---|---|
| the `referer_info` container | fields without a `_` prefix propagate downward automatically (§8) |
| the two mutually exclusive channels `doc.extra.item.*` and `doc.extra.referer_info.*` | just one: the caller passes the previous chain's product dict as one item of the next chain's `inputs` |
| the `doc` visible field of view / the "information bonanza" of `Q46` | the `seed.inject` allowlist |
| "globals crossing the river on the doc" | `globals` is only a chain-level static constant; input travels through the `seed` product (§3) |
| system-reserved variables | none (the wording of `Q15` is kept: no special branches) |

### 8.3 The recommended shape for passing between chains

A collection chain produces `list[dict]` (each item carrying `url`/`title`/`channel`/…); the caller then `run()`s a parse chain for each product, passing that dict as one item of `inputs`:

```python
list_chain   = up2.compile(list_graph)
detail_chain = up2.compile(detail_graph)

page = fetch(list_url)
for item in up2.run(list_chain, {"text": page}).value:
    html = fetch(item["url"])
    out  = up2.run(detail_chain, {"text": html, "meta": item})
```

**This is the explicit version of the same thing draft `01` expressed with a `doc` table + `referer_info` + `tpl:` prefix dispatch**: cross-chain passing is visible in the data flow and does not rely on an implicit carrier. If a host genuinely needs the `doc` table and `tpl:` dispatch, it can build them on top of `store` and the caller; the kernel need not know.

---

## 9. Execution model

```text
run(chain, inputs) -> Ok(value) | Missing | Failed
  ├─ sequential advance (starting from entry):
  │    node = nodes[cur]
  │    outs = exec_node(node)
  │      ├─ seed                      → [the injected input dictionary]
  │      ├─ parse (fields)             → [one field dictionary]
  │      ├─ a field chain ending in each → [that field holds one dictionary per element]
  │      └─ emit                      → [one assembly per upstream product]
  │    dispatch:
  │      ├─ next   → cur = next; outs are fed to that node one by one
  │      └─ routes → for each entry of outs, pick the target node by route_field; the target is evaluated **one by one**
  └─ aggregation: the products of all terminals are aggregated into the export value by the output rules of §5.3
```

### 9.1 Hard constraints

| Constraint | Content | Reason |
|---|---|---|
| Sequential advance | walk the graph from `entry`; no topological sort, no parallelism | settled as Q7 in draft `01` |
| References only backwards | `$<node key>` must be a preceding node | a direct consequence of the sequential semantics; enforced at compile time (L11) |
| **join forbidden (in-degree > 1)** | a node may have **exactly one predecessor node key**; several `routes` labels pointing at the same target are allowed (they all come from the same upstream) | draft `01` only wrote "not forbidden but no join is performed", leaving the ambiguity of "when a node is computed twice, which computation does `$node.field` refer to". This design **forbids it outright** and removes the ambiguity at compile time (`UP2-E1108`) |
| Acyclic | detected at compile time (`UP2-E1104`) | as above |
| terminal ≥ 1 | see §5.4 | otherwise the chain has no product |

---

## 10. lint checklist (enforced at compile time, `UP2-E1xxx`)

| # | Rule | Error code |
|---|---|---|
| L1 | all required fields present; `dsl_version` is a positive integer; `output` has a legal value | `UP2-E1103` |
| L2 | `entry` exists and is of type `seed` | `UP2-E1103` |
| L3 | node keys are unique and not reserved names (`globals`/`locals`/`fields`/`entry`) | `UP2-E1009` |
| L4 | node count ≤ `MAX_NODES` | `UP2-E1012` |
| L5 | `next` / `routes` are mutually exclusive; `routes` implies `default_route` | `UP2-E1101` / `UP2-E1102` |
| L6 | the target nodes of `next` / `routes` / `default_route` all exist | `UP2-E1103` |
| L7 | everything is reachable from `entry` (no orphans, no broken links) | `UP2-E1103` |
| L8 | acyclic | `UP2-E1104` |
| L9 | every node has in-degree ≤ 1 (exactly one predecessor node key) | `UP2-E1108` |
| L10 | terminal ≥ 1; exactly 1 terminal when `output="single"` | `UP2-E1103` |
| L11 | a reference points at a **preceding** node / the `seed` product / `globals` / `$fields` / `$locals`; the path exists in the target product; **a node must not reference its own key** | `UP2-E1006` |
| L12 | a **cross-node** referenced key carries no `_` prefix (`$fields._x` / `$locals._x` are legal inside the node itself) | `UP2-E1014` |
| L13 | `seed.inject` covers every `$<seed key>.*` reference | `UP2-E1006` |
| L14 | `route_field` is a key of `fields`; with `routes` present there must be a `default_route` fallback | `UP2-E1105` |
| L15 | `result` is present when `emit.produces="record"` and absent when `="flat"`; with `produces="flat"` and a `field`, that field must be a key of the preceding node's product | `UP2-E1105` |
| L16 | every reference inside the `result` template resolves | `UP2-E1106` |
| L17 | every stage inside `fields` (including the sub-chains of an `each` field map) and inside `result` passes operator Schema validation | `UP2-E1001`…`E1005` |
| L18 | no resource limit is exceeded (`01` §9) | `UP2-E1012` |
| L19 | the `schema` name is registered, or the inline description resolves | `UP2-E1011` |
| ~~L20~~ | **withdrawn**: `presets` and their mutual-reference rule went with the container (§4.3) | — |

> **Changes relative to §2.6 of draft `01`**: removed 5 (`request ≤ 2`), 5b (a `request` may only have a seed upstream), 5c (a collection chain's parse must have routes), 5d (`tpl_key` must not start with `:` → moved to the storage layer, `04` §2), the `outputs` part of 7, and 9/10 (the `default`/`none` reserved names, and `tpl_key` being unrenamable → these belong to the host or the storage layer); added L9 (no join), L10 (terminal count), L15/L16 (export shape and template), L18 (limits), and L20 (no mutual references among presets). **L20 was withdrawn later**, when the L2 iteration redesign replaced `presets` with `each`'s inline field map (change `l2-chain-structure-and-each`); the number stays retired rather than being reused, so existing references keep pointing at the same rule.

---

## 11. A complete walkthrough: ah.gov.cn (rewritten from the walkthrough example in the the internal source material, not shipped in this repository)

Material: the legacy rule of §1 in draft `01` (1 list rule + 2 detail rules, with `url_patterns` completely identical, told apart by order).

### 11.1 The collection chain (`tpl_key = "\u653f\u5e9c\u6587\u4ef6\u5217\u8868"`)

```jsonc
{
  "dsl_version": 1,
  "entry": "seed-0001",
  "output": "list",
  "globals": { "base_url": "https://www.ah.gov.cn" },
  "policy": { "on_missing": "drop" },
  "nodes": [
    { "key": "seed-0001", "type": "seed",
      "config": { "inject": ["text"], "input_format": "html" },
      "next": "parse-0001" },

    { "key": "parse-0001", "type": "parse",
      "config": {
        "input": "$seed-0001.text",
        "fields": {
          "rows": [["css", "nodes", "a[href*='/public/1681/']"],
                   ["py", "slice", ":20"],
                   ["each", {
                     "url":     [["css", "@href", ""], ["py", "urljoin", "$globals.base_url"]],
                     "title":   [["css", "text", ""], ["py", "normalize_space", ""]],
                     "channel": [["const", "\u653f\u5e9c\u6587\u4ef6"]],
                     "source":  [["const", "\u5b89\u5fbd\u7701\u4eba\u6c11\u653f\u5e9c"]],
                     "region":  [["const", "\u5b89\u5fbd\u7701"]],
                     "route":   [["const", "article"]]
                   }]]
        }
      },
      "next": "emit-0001" },

    { "key": "emit-0001", "type": "emit",
      "config": { "produces": "flat", "field": "rows" } }
  ]
}
```

Product (`output: "list"`): `[{"url": …, "title": …, "channel": "\u653f\u5e9c\u6587\u4ef6", "source": …, "region": …, "route": "article"}, …]`

**Key-point cross-reference**:

| Blocker in draft `02` | How this design dissolves it |
|---|---|
| **A** missing node-splitting semantics | `each` takes on "run this field map per element, after an ordinary chain that produced the list" — the truncation is a plain `["py","slice",":20"]` before it, and the records land in the named field `rows` |
| **B** can a chain argument position reference `$node.slot` | Yes. `["py","urljoin","$globals.base_url"]` is exactly such a reference (argument kind = `ref_or_literal`, `02` §3.2); swapping in `$seed-0001.meta.url` holds just as well. The base therefore varies with the input instead of freezing the URL into the chain |
| **C** a non-empty `headers` has nowhere to land | a collection chain produces only items (with `url`); detail request headers belong to the **host**. When needed, assemble them with `produces:"request"` in a parse chain (§5.2), or add hotlink-protection headers uniformly in the host's request layer |
| **D** mutually exclusive sources for `channel/source/region` | always produced with `["const", …]` in `fields` (§8.1) |
| **E/F/G** the propagation container was undecided / a single route had to write routes / per-item semantics were not explicit | propagation = fields without a `_` prefix are visible automatically; a single target uses `next` directly; per-item is switched on explicitly by an `each` stage inside the field chain that holds the list |

**The empty selector of `["css","@href",""]`**: an empty selector string ⇒ takes **the current input node itself**. Inside `each`'s field map the first-stage input of a field chain is that element, so this is the standard way to extract a value per item (the rule is in `02` §6.1).

### 11.2 The parse chain (`tpl_key = "\u6b63\u6587\u8be6\u60c5"`)

```jsonc
{
  "dsl_version": 1,
  "entry": "seed-0001",
  "output": "single",
  "nodes": [
    { "key": "seed-0001", "type": "seed",
      "config": { "inject": ["text", "meta"], "input_format": "html" },
      "next": "parse-0001" },

    { "key": "parse-0001", "type": "parse",
      "config": {
        "input": "$seed-0001.text",
        "fields": {
          "title":    [["css1","@content","meta[name=\"ArticleTitle\"]"], ["py","normalize_space",""]],
          "pub_time": [["css1","@content","meta[name=\"PubDate\"]"], ["py","strip",""], ["py","parse_time","zh"]],
          "content":  [["css","remove","script,style,noscript"],
                       ["css1","html","div.j-fontContent"],
                       ["py","html_to_markdown",""]]
        }
      },
      "next": "emit-0001" },

    { "key": "emit-0001", "type": "emit",
      "config": {
        "produces": "record",
        "schema": "$article",
        "result": {
          "item_type": "article",
          "url":       "$seed-0001.meta.url",
          "title":     "$parse-0001.title",
          "pub_time":  "$parse-0001.pub_time",
          "content":   "$parse-0001.content",
          "channel":   "$seed-0001.meta.channel",
          "source":    "$seed-0001.meta.source",
          "region":    "$seed-0001.meta.region"
        }
      } }
  ]
}
```

`$article` is a schema registered by the host (`04` §7) and looks like:

```jsonc
{
  "item_type": "str",
  "url":       "str",
  "title":     "str",
  "pub_time":  "str?",
  "content":   "str",
  "channel":   "str?",
  "source":    "str?",
  "region":    "str?",
  "doc_key":   "str?",
  "files":     [{"name": "str", "url": "str", "size": "int?"}],
  "extra":     "json?"
}
```

**Key-point cross-reference**:

| Blocker in draft `02` | How this design dissolves it |
|---|---|
| **M** the old "2 detail rules + `url_patterns` dispatch" has nowhere to land | see §12 (`variants`, L4); L1/L2 split it into two chains, one chain per rule, **with the caller choosing the chain by URL** — the selection signal is explicit on the caller side instead of being guessed inside the chain |
| **N** `cast datetime` conflicts with the export encoding | the `py` conversion vocabulary has no `datetime`; time goes to `py.parse_time` (which outputs `str`); the export type is declared by `schema` (`02` §6.4/§6.6) |
| **O** the terminal state `parser="none"` conflicts with the dispatch table | `emit` is the chain's terminal, and "no further dispatch" is a structural fact that needs no `parser` field. The conflict disappears with the removal of the `doc` concept |
| **P** `list_title` has nowhere to go once injected | reference `$seed-0001.meta.title` directly (the `title` produced by the collection chain); declare in the schema whatever is needed, and "read but nowhere to write" no longer exists |
| **Q** `ctx.globals` idles empty | `globals` holds only chain-level static constants; input travels through the `seed` product (§3). Not merging the two ⇒ no more idle semantics |
| **R** the `result` syntax was undefined | fixed once and for all in §6 |
| **S** the boundary between `outputs`/`produces`/`result` is unclear | `outputs` is deleted (§4.5) |
| **T/U/V/W** two propagation channels / ctx write permission undecided / `list_title` already lost / the field error policy and the two gates | a single propagation channel (§8); the write surface is limited to `locals` (`02` §6.8); `list_title` becomes an ordinary field; the two gates are the host's business gates, and the kernel only emits the tri-state (`02` §5) |

### 11.3 Master table of where the legacy elements go

| Legacy element | New landing place |
|---|---|
| `task_name` / `channel` / `region` | a `const` product in `parse.fields`, or the caller's `inputs` |
| `request` / `request.url` | the caller's job; when needed, assemble with `emit.produces="request"` |
| `input_format` | `seed.config.input_format` (primary input) / `parse.config.format` (secondary materialization) |
| `nodes` (splitting + truncation) | a field chain: `["css","nodes",…]` → `["py","slice",":20"]` → `["each", {…}]` |
| `fields` | `parse.config.fields` (triples, semantics unchanged) |
| `fields.headers` | the host's request layer |
| `fields.referer_info` | deleted (fields without a `_` prefix propagate downward automatically) |
| `url_patterns` | the caller picks the chain; several shapes inside one chain use `variants` (§12, L4) |
| `detail` (several rules) | several chains (several pieces of chain data) or `variants` (L4) |
| `tpl_key` / `root_domain` | **not in the chain format**; they are storage identifiers introduced by the L3 binding layer (`04` §2) and never appear in L1/L2 |

---

## 12. Reserved field: `variants` (L4, a placeholder at this stage)

Blocker M of draft `02` is the only place where "a real requirement exists but neither design draft gives it a landing place": one site has several sets of detail fields dispatched by `url_patterns`, yet the two patterns of `ah.gov.cn` are **completely identical** (the legacy system told them apart by "order + two rounds of attempts") — which shows that `url_patterns` itself is not a reliable dispatch signal.

A mechanism this design **reserves but does not implement in L1/L2**:

```jsonc
"config": {
  "variants": [
    { "when": { "url_pattern": "/public/\\d+/\\d+\\.html?$" }, "fields": { /* variant A */ } },
    { "when": { "doc_type": "article" },                       "fields": { /* variant B */ } },
    { "fields": { /* fallback: no when means unconditional */ } }
  ]
}
```

| Design point | Content |
|---|---|
| Match target | the `meta` injected by `seed` (`url` / `doc_type` / custom keys), **not an arbitrary expression** |
| Signal allowlist | three: `url_pattern` / `doc_type` / `route`; no general expression language is introduced |
| Evaluation semantics | tried in declaration order, and **the first variant that produces something other than `Missing` wins**; a variant without `when` is the fallback |
| Why it is restricted | the old `dsl-design` D3 states plainly that "conditional branching is not done yet, to avoid growing into half a programming language". The signal allowlist pins expressiveness to "pick one set of fields" |
| Why not in L1 | multi-shape sites are first split into several chains and chosen by the caller (the selection signal is explicit). `variants` opens only once the number of real sites proves that "splitting chains" costs too much |

**Q1' of draft `01` (variable single version, one chain per row) stays unchanged**: `variants` are field variants inside a chain, not multiple versions of a chain.
