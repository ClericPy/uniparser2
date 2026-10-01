# uniparser2 Design · 03 Parse Chain Spec

> **Status**: design draft **v0.2**, rewritten around the **story** model (v0.1 described three node types
> and a graph). **Upstream**: `00`, `01`, `02`, `07`.
> **What this document answers**: what a chain is (a **story**: a linear sequence of steps), what a step is
> (`parse` / `call` plus `out`), how a product carries a **type name**, the one suspension mechanism
> (**effects**: `Request` and `call`), and how a run proceeds.
> **Supersedes**: v0.1 of this note — the three node types (`seed`/`parse`/`emit`), `entry`/`nodes`/`output`,
> `next`/`routes`/`default_route`, the `emit` export shapes and the graph lint family — see §12.1 for the
> ruling and `D-03-3` for the rejected alternatives. v0.1's materialization ruling (§6 here) and its `each`
> ruling (§7 here) are carried over unchanged.
> **Not implemented**: this layer has no executor yet. What exists today is the operator layer (`02`) and
> the field-chain evaluator (`compile_field` + `eval_field`); `up2 lint` / `up2 trial` compile **one field
> chain**, nothing more.

---

## 1. One story

The end-to-end shape the whole project starts from:

```text
one text in  →  typed products out  →  the host acts on each product by its type
```

A chain is one such run, and this note calls it a **story**. A story is **linear**: one entry, one exit,
one step after another. It carries **no roles** — there is no seed, no parse node, no emit node, and no
"kind of node" for an executor to branch on. What a step consumes is simply the value the step before it
produced (or the value the caller handed in); what it produces is a value with a **type name**.

Two consequences are the point of the whole design:

- **The host decides what happens to a product.** Dispatch is by the product's **type name**, and it lives
  in the host — not in the story data. A story says *what a product is*; the host says *what to do with it*.
  Which story fits a given response is exactly the decision the L3 binding layer already makes on the
  caller's side (`07` §3: no domain name, no `tpl_key`, no business key ever appears in a story).
- **A story may need the network in the middle of it.** The kernel performs no IO, so a step whose product
  is a `Request` **suspends** the run: the host sends it, and what comes back becomes the next step's
  input. That single mechanism is what lets one JSON describe a real multi-level flow (§4, §11).

---

## 2. The story JSON

```jsonc
{
  "dsl_version": 1,
  "globals": { "base_url": "https://www.ah.gov.cn" },   // chain-level, read-only constants
  "policy":   { "on_missing": "drop", "on_error": "raise" },
  "steps": [
    { "key": "reqs",  "parse": { "items": [ /* … */ ] }, "out": "TaskList", "then": "article" },
    { "key": "rows",  "parse": { "items": [ /* … */ ] }, "out": "NoticeList" },
    { "key": "store", "call": "host.store_notices", "with": { "table": "notices" }, "out": "dict" }
  ]
}
```

| Field | Required | Description |
|---|---|---|
| `dsl_version` | yes | an integer, initial value `1`; bumped only on a structural change |
| `globals` | no | the chain-level **static** environment (such as `base_url`); read-only for every step |
| `policy` | no | the chain-level default policy (`01` §5); whether a step may override it is open (§13) |
| `steps` | yes | the linear sequence; **array order is execution order** |

**There is no `input` field.** The first step's input is the value the caller passes to the run; every
later step's input is what the step before it produced. A step that needs a value from further back writes
a reference (`$<step key>.field`); a step that needs a constant reads `$globals`.

**There is no name for "this step's own input"** — the input *is* the first stage's input value, and a
reference is only needed for reaching backwards. The one place this bites is a step-level configuration
object that wants to read its own input (a `Request` whose `url` *is* the input, say); today the closest
spelling is `["ctx","set","locals._u"]` (a pass-through, measured), and §13 records the gap.

**The story's exit is the last step's `out`**, derived, never declared again. (`03` v0.1 §4.5 had already
deleted the old `outputs` declaration for this reason: a second source of truth for the same fact.)

### 2.1 The step

| Field | Description |
|---|---|
| `key` | the step's name, used by backward references (`$reqs.items`). Whether it is required is open (§13) |
| `parse` **or** `call` | what the step does — mutually exclusive, told apart by shape and by keyword |
| `out` | the **type name** of the product (§3) |
| `then` | only on a step that produces tasks: the **default continuation chain key** for the tasks it produces (§4.1); a single task item may carry its own `then` and override it |
| `with` | only with `call`: the arguments handed to the host function |

**A story is one layer.** Because a request's response is handled by the chain its task names (`then`), the
natural unit is **one story per layer**: the seed story makes the first request, the list-page story turns
that response into tasks, the article story turns one response into one record (§11). Nothing forces that
split — a story may have several steps, and a step may hand off more than once — but the flow between
layers travels as **tasks**, not as one long run.

**`parse`** takes one of two shapes:

| Shape | Meaning |
|---|---|
| an array (`[ ["css","nodes","ul a"], … ]`) | **one chain**: one value in, one value out (`02` §1) |
| an object (`{ "title": [ … ], "body": [ … ] }`) | **a field map**: every chain is fed **the same input** and the product is one dictionary |

The field map is the workhorse. A chain is a one-value pipeline, so "pull the title, the body and the date
out of **one** document" cannot be written as a chain at all — measured: the stages run in sequence, so a
second `["css1","text","div.content"]` receives the first stage's output, not the document. A `_`-prefixed
field name is a temporary of that step: readable by the later chains of the same step, never a key of the
product.

**`call`** names a host function. It may have side effects and it **must return a serializable receipt**,
which becomes the step's product; the kernel's single exit (`01` §4) therefore still holds.

The identity with `each` is deliberate: `each`'s argument is the same field-map shape (`02` §6.9). `each`
runs the map once per element of a list; a step runs it once for its whole input.

---

## 3. Products and types

### 3.1 Where a type name comes from

| Source | Names | How the name is obtained |
|---|---|---|
| the JSON value domain | `null` / `bool` / `str` / `int` / `float` / `list` / `dict` | from the value itself (`01` §2's type-name table) |
| built-in **effect** types | `Request`, `TaskList` | `Request` is what a task carries; producing a `TaskList` hands the tasks to the host and **ends the run** (§4) |
| built-in **data** types | `Response` | declared with `out`; validated like any other product |
| host-registered types | `NoticeList`, `Article`, … | declared with `out`; the host registers name → constructor |

The built-in set is deliberately **closed at `Request` / `Response` plus the JSON basics**. Anything with
domain meaning is the host's registration, so the engine keeps no business vocabulary (`07` §3's
zero-coupling criterion; acceptance item 8 there).

### 3.2 A type is a constructor

| Product | How the declared type is built |
|---|---|
| a dictionary | `Cls(**payload)` |
| a list | `Cls(*items)` |

So a collection carries a type of its own (`NoticeList(*items)`, `TaskList(*tasks)`) instead of
degrading to the built-in `list`; the built-in `list` name is left for collections that need no meaning.

### 3.3 Where validation happens

At the **step boundary, by the kernel**, using the constructor the host registered for `out`: the kernel
builds the declared type from the JSON, reports a mismatch at the step that produced it, and continues with
the JSON.

**Host objects never enter a chain.** Measured on the current kernel: a host function returning a
`dataclass` instance is rejected at once (`UP2-E2009 udf.make_article returned a non-serializable value:
Article`). Pydantic instances therefore live **only on the host side**:
`Article.model_validate(product)` when the host receives a product, `model_dump()` when a callback returns
one. `out` names a type; it never means "the chain is carrying a Python object".

---

## 4. Effects: `call` suspends, a request hands off

An **effect** is a step whose product must be produced by the host. The kernel never performs it: it hands
over a description and waits.

### 4.1 `Request` — the task hand-off

```jsonc
{ "key": "reqs", "parse": { "items": [ /* … */ ] }, "out": "TaskList" }
```

| The step produces | The host does | What happens next |
|---|---|---|
| `out: "TaskList"` — items of `{ "request": Request, "then": "<chain key>" }`, one task or many | sends each `request` (concurrently, at its own pace) and, per response, starts the chain named by that task's `then` | the response becomes **that chain's input**; the run that produced the tasks is already over |

A request is therefore a **hand-off, not a suspension**: a step whose `out` is `TaskList` is the last step
of its run, and its product is the work to be done. The step's own `then` is the default for every task it
produces, and a task item that carries its own `then` overrides it — that is how one batch fans out to
different parsers: which parser suits a response is the host's dispatch (`§1`), and here the dispatch key
travels **in the data**, per task.

The `Request` structure is v0.1's built-in, unchanged:

| Key | Type | Default |
|---|---|---|
| `url` | `str` | **required** (missing is an error, not `Missing`) |
| `method` | `str` | `"GET"` |
| `headers` | `json` | `{}` |
| `params` | `json` | `{}` |
| `body` | `json` | `null` |
| `timeout` | `float` | `30.0` |
| `follow_redirects` | `bool` | `true` |

The kernel assembles and **never sends**: which HTTP client, how much concurrency, how many retries,
whether to add hotlink-protection headers — all of it is the host's.

`Response` is the answer's type:

| Key | Type | Default | Why |
|---|---|---|---|
| `status` | `int` | required | the host (or the next steps) must be able to tell a 404 page from content |
| `text` | `str` | `""` | the body, the raw material of the next steps |
| `headers` | `json` | `{}` | content type, redirect chain, … |
| `url` | `str` | `""` | the **final** URL after redirects — relative links must resolve against it, not against the requested one |

A step that parses a `Response` therefore starts its chains by taking the body apart
(`["py","get","text"]`), and a step that resolves relative links takes `["py","get","url"]` as the base.

### 4.2 `call` — the host function

```jsonc
{ "key": "store", "call": "host.store_notices", "with": { "table": "notices" }, "out": "dict" }
```

The host runs the function and sends back the receipt; the receipt becomes the step's product, validated
against `out` like any other product. A function with side effects is legal **here and only here**: the
kernel stays pure, and the receipt keeps the single exit. How `with` is written is open (§13).

### 4.3 Effects are station-level only

Both `call` and a task-producing step are written at the **step** level, never inside a chain or inside an
`each` field map. `call` suspends a run that continues afterwards (one suspension at a time, so the
executor needs only **flat** suspension); a task-producing step **ends** its run.

- A fan-out is one `TaskList` product, not N effects inside `each`.
- **Concurrency is the host's**, exercised on the task list it already holds: it may send 50 requests in
  parallel because the step handed it 50 tasks.
- A nested effect (a request decided inside `each`, say) would have forced nested suspension and still
  produced serial requests. Ruled out (`D-03-3`).

### 4.4 Trace, suspension and hand-off

| | What it carries | Who consumes it |
|---|---|---|
| **trace event** | one per **step**: its key, its product type, a product summary, timing | audit, the trial UI (`06`), debugging, `up2 trial --trace` |
| **suspension** | a `call` — the run continues with the receipt | the host, which must answer before the run continues |
| **hand-off** | a task-producing step's `TaskList` | the host, which sends the tasks and starts the chains they name; that run is over |

The host sees every step's product, and it only has to **answer** at a `call`. With the answers (and the
tasks it sent) recorded, a flow replays deterministically: the kernel never performs IO, so replayability
(`01` §1) is kept.

---

## 5. The run loop

```text
start(story, value) -> run                    # compile, then run to the end or to the first `call`
run.next()   -> {effect:"call", …} | {effect:"done", product: …}
run.send(receipt) -> the next effect / done    # only `call` is answered
```

A task-producing step does not appear here: it simply ends the run, and its `TaskList` product is the
host's to-do list. The kernel side keeps its invariants (no IO, no threads, one exit); the host side is
ordinary code:

```python
queue: list[tuple[str, object]] = [("seed", seed_url)]      # (chain key, that chain's input)
while queue:
    key, value = queue.pop()
    run = up2.start(chains[key], value)
    while True:
        effect = run.next()
        if effect.kind == "done":
            product = effect.product
            break
        run.send(handlers[effect.name](**effect.with))       # `call` → receipt
    for task in tasks_of(product):                           # `TaskList` → one entry per task
        queue.append((task.then, fetch(task.request)))        # the host owns the network
```

A host that would rather not write that loop can register handlers for both kinds and use a driver; that
driver is **not** part of this note, and it belongs to the host side, not to L2.

---

## 6. On-demand materialization and the run-scoped cache

**Status**: the operators materialize on demand **today** (measured: `css1` on HTML text, `json` on JSON
text and `xpath` on XML text all return the parsed result). The cache described below is **not
implemented**; it lands with this layer, which is where many fields and many steps start from the same
input value. Until then, feeding the same text to several `css`/`json` stages parses it once per stage.

**A story does not materialize its input.** How an input becomes structure is decided by the operator that
consumes it, at the moment it consumes it:

| Consumer | On a `str` input | On its own value domain |
|---|---|---|
| `css` / `css1` | parses HTML into an `Opaque` document | a `DomNode` / a node list is unwrapped |
| `json` | parses JSON text | a JSON tree is walked |
| `xpath` | parses XML into an `Opaque` document | a node is unwrapped |

Two consequences: **a chain never declares a format** (`input_format` / `parse.format` are deleted), and
"one document, one parse" is the cache's job rather than the entry point's.

**`bytes` never enters a chain**: the value domain is the JSON tree plus the `Opaque` handle (`01` §3), so
decoding is the caller's job — the CLI hands over text (`--input K=@file`), and a genuinely binary payload
is materialized by the host or carried in as text (base64).

**The materialization cache is run-scoped and bounded**, and it is a correctness-of-performance part of the
design rather than an optimization:

- **Scope**: it lives with one run and is released with it. Nothing is shared across runs, so no `Opaque`
  handle outlives the run that produced it and two runs cannot observe each other.
- **Key**: the target format plus the source value — object identity first, a content hash on a miss.
  Hashing a 5 MB text costs a couple of milliseconds against the ≈110 ms parse it saves.
- **Bound**: `MAX_MATERIALIZE_BYTES` (64 MiB by default, `01` §9) with LRU eviction, accounted in
  **materialized bytes** — not in source-text bytes, because the amplification differs per format
  (measured: a selectolax DOM is ≈24× its HTML text, a JSON tree ≈2.2–2.7×).
- **At most `MAX_MATERIALIZE_ITEMS` (8) artifacts**, so a run over many small documents cannot fill the cap
  with hundreds of tiny trees.
- **The cap is soft for a single artifact**: an artifact larger than the cap is still retained while it is
  in use, so "one document, one parse" always holds and the worst case is the cap plus that one artifact.
  The largest accepted input is `MAX_TEXT_BYTES` (16 MiB, `01` §9), whose HTML tree is ≈384 MB — a
  documented tradeoff rather than a promise.
- **Eviction** costs a re-parse and nothing else: materialization is a pure function of the text, so a hit
  and a miss MUST be observably identical, and a test pins that equality.
- **Mutation**: a cached tree MUST NOT be mutated in place. `remove` already copies before pruning, and
  that becomes a contract for every format operator.
- **One implementation**: materialization entries are shared, each declaring its own optional dependency —
  `tomllib` and `csv` are stdlib, YAML is third-party — and a missing dependency is `UP2-E1107` with the
  install line, exactly like `css`'s selectolax.

Measured on the current commit (selectolax, synthetic pages): one parse costs 48.0 ms at 2 MB and 109.6 ms
at 5 MB, an HTML tree costs **≈24×** its text in resident memory (2 MB → +49.3 MB, 5 MB → +121.7 MB) while a
JSON tree costs ≈2.2–2.7× (2.1 MB → +4.6 MB), and 20 fields that each re-parse take 748.8 / 1976.7 ms
against 16.5 / 48.6 ms when one parse serves all 20 (**40–45×**). The amplification is why the cap is
accounted in materialized bytes, and why the cache is not a module-level one.

---

## 7. `each` and the field map

Draft `02` pointed out that draft `01` **dropped the whole layer** of the legacy rule's node splitting
(split the chain first, then extract values per item, with a `[:20]` truncation): if the first stage of the
field map is a plain attribute read, the object being evaluated is the whole document rather than a single
`<a>`, so the result is necessarily wrong.

The layer is back as **one operator inside a chain** (`02` §6.9):

```jsonc
"rows": [["css","nodes","li"], ["py","slice",":20"], ["each", {"title": [["css1","text","a"]]}]]
```

| Rule | Content |
|---|---|
| a step's field map | evaluated **once** on the step's input; produces **one** dictionary |
| `each` inside a chain | its input must be a list; the result is one dictionary per element, so that field holds `list[dict]` |
| truncation / sorting | ordinary stages **before** `each` (`["py","slice",":20"]` above) |
| empty collection | `each` on an empty list yields an empty `list`, not `Missing` — an empty list page is a normal result |
| exporting the list | the list is a **named field** of the step's product dictionary |

A nested `each` (a field map inside a field map) is legal up to `MAX_EACH_DEPTH`, and the whole field-map
argument is compiled recursively, so a mistake inside it is reported at compile time with a pointer that
reaches the offending stage.

**Field definitions and evaluation semantics** are in `02` §5. The key points restated:

- a key **without a `_` prefix** ⇒ travels with the step's product and can be referenced by later steps;
- a key **with a `_` prefix** ⇒ local to this step (`locals`): referenceable inside this step, while a
  reference from another step is `UP2-E1014`;
- fields are evaluated in declaration order, and a later field may reference earlier `_` values — inside an
  `each` field map the same rule holds **per element**.

**The `_` prefix inside `each`'s field map**: such a key is stored in the element's locals, later fields of
the same element read it as `$locals._name`, and it never appears in the element's dictionary. So "compute
something once for two fields" needs no relay field.

**Scope inside `each`**: every element is evaluated in its own child scope; a read falls back outward **by
name** — the element's locals, then the step's locals, then the chain-level values — so the innermost scope
holding the first segment of the path resolves the whole path, and a name the element itself wrote is
resolved there and nowhere else. Writes stay in the element, and the element's locals do not outlive the
element, which is why chain authors keep a `_` name unique across nesting levels. There is no iteration
variable to name: the element is the input value of every field chain.

**`$fields` is shorthand for this step** (including this step's `_` keys) and is valid only inside the step
that declares the field map. **A step cannot reference its own key** (`$reqs.items` written inside `reqs`'s
own field map ⇒ `UP2-E1006`, whose message points at `$fields.items`). These two are the mistakes chain
authors make most often, and the `UP2-E1006` message must say so explicitly.

**`presets` does not exist** (`D-03-1`): the field map is inline, so there is nothing left to name.

---

## 8. Scope and downward propagation

Two sources plus one automatic rule:

| Source | Lifetime | Read/write |
|---|---|---|
| `globals` | the whole story | read-only (the chain-level static constants) |
| the run's input | the whole story | read-only; it is the **first step's input**, and it has no name of its own (§2) |
| `locals` | the current step | writable (`ctx.set`/`del` are limited to `locals.*`, that is, `_`-prefixed fields) |
| a step's product | from that step to the end of the story | read-only; **fields without a `_` prefix join automatically** |

**Downward propagation needs no new concept**: under linear execution, the fields of an earlier step are
referenceable by later ones. During a fan-out (an effect answering with a batch) the products are carried
by the batch itself.

### 8.1 Where `channel` / `source` / `region` land (blocker D of draft `02`)

Draft `01`'s `Q44` says they are "products of list parsing, passed down with the item", while `01 §2.3`
treats them as "product fields of a collection-style seed"; the two are mutually exclusive.

**Ruling: always produce them inside a step's field map with `["const", …]`.** Reasons: they really are
values each product carries itself; when one story serves several channels, different steps can give
different `const` values; and putting another copy in the run's input creates the ambiguity of "which one
is the truth", which is exactly where draft `02` got stuck while walking the example.

### 8.2 Things that do not exist

| Deleted | Replacement |
|---|---|
| the `referer_info` container | fields without a `_` prefix propagate downward automatically |
| the two mutually exclusive channels `doc.extra.item.*` / `doc.extra.referer_info.*` | one: the caller passes the previous story's product as the next run's input |
| the `doc` visible field of view (`Q46`) | the run's input value |
| "globals crossing the river on the doc" | `globals` is only a chain-level static constant |
| system-reserved variables | none (`Q15`'s wording is kept: no special branches) |

### 8.3 Passing between stories

A collection story produces `list[dict]` (each item carrying `url` / `title` / …); the host then runs a
detail story per product, handing that dict in as the run's input:

```python
page = fetch(list_url)
rows = up2.run(collection_story, page)                  # the run's input is the page text
for item in rows:
    html = fetch(item["url"])                           # the host owns the network
    out  = up2.run(detail_story, {"text": html, "meta": item})
```

This is the **explicit** version of what draft `01` expressed with a `doc` table + `referer_info` +
`tpl:` dispatch: cross-story passing is visible in the data flow. Note that a story may also fetch for
itself (§4.1), so **a request ends its story**: the layer that sends hands its tasks to the layer that
parses, and the split is what lets the host own its concurrency, retries and caching
policy around a boundary. If a host genuinely needs the `doc` table and `tpl:` dispatch, it can build them
on top of its store and the caller; the kernel need not know.

---

## 9. The exit and schema

- **The exit is the last step's product**, of the type its `out` names. There is no assembly template and no
  export mode: a step's field map already produces the dictionary, and a product that needs a shape gets a
  registered type instead of a template.
- **A `schema` is the registered type itself.** Validation is the step-boundary construction of §3.3;
  misshapen JSON is reported at the step that produced it (`UP2-E2014` for an exit-shape mismatch at the
  run's boundary).
- The old `result` template (and the reference categories it needed) is **dissolved**: its job was to
  assemble the export, which the field map now does directly.

---

## 10. Compile-time lint checklist

| # | Rule | Code |
|---|---|---|
| L1 | the required top-level fields exist; `dsl_version` is a positive integer | existing |
| L2 | every step declares **exactly one** of `parse` / `call`, and `with` only with `call` | existing (`UP2-E1005`) |
| L3 | step keys are unique and not reserved names (`globals` / `locals` / `fields`) | existing (`UP2-E1009`) |
| L4 | step count ≤ `MAX_NODES` | existing (`UP2-E1012`) |
| L5 | a reference points at an **earlier** step, a `globals` path, `$fields` or `$locals`; the path exists in the target product; a step must not reference its own key | existing (`UP2-E1006`) |
| L6 | a cross-step referenced key carries no `_` prefix | existing (`UP2-E1014`) |
| L7 | every stage (including the sub-chains of an `each` field map) passes operator validation | existing (`UP2-E1001`…`E1005`) |
| L8 | `out` names a built-in type or a registered type | new |
| L9 | a `TaskList`-producing step is not the last step of its story (a request ends the run and hands off); a request is never written inside a chain or an `each` field map | new |
| L10 | no resource limit is exceeded (`01` §9) | existing (`UP2-E1012`) |
| L11 | an operator's optional dependency is installed | existing (`UP2-E1107`) |
| ~~L20~~ | **withdrawn** with `presets` (`02` §6.9); the number stays retired rather than reused | — |

The v0.1 graph rules are gone with the graph: `entry`/`nodes`/`output` shape checks, `next`/`routes`
mutual exclusion, `routes` ⇒ `default_route`, target existence, reachability/orphans, acyclicity,
in-degree ≤ 1, terminal count, `route_field`, `seed.inject` coverage, the `result`-template rules. The
`UP2-E1101`–`E1106` codes they used are **retired, not reused** (`02` §7.1's rule), which is a change to
`02`'s error table and lands with the implementation change.

---

## 11. A complete walkthrough: ah.gov.cn

Material: the legacy rule of §1 in draft `01` (1 list rule + 2 detail rules, with `url_patterns`
completely identical, told apart by order). The flow is now **three stories** — the seed, the list page and
the article — joined by the tasks each one produces: the seed URL goes out as a request, the list page's
response becomes twenty tasks, and each task names the chain that parses its response.

### 11.1 Three stories: the seed, the list page, the article

Each layer is a **story of its own**, joined to the next by the tasks it produces (§4.1); the host walks
that queue. No story knows a domain, a site or a business key — only the host does.

```jsonc
// 1) "seed": the seed URL becomes the first request; its response goes to "list_page"
{
  "dsl_version": 1,
  "steps": [
    { "key": "start",
      "parse": { "url": [ ["py","str",""] ] },   // only the URL; method/headers/timeout are defaults
      "out": "TaskList",
      "then": "list_page" }
  ]
}
```

```jsonc
// 2) "list_page": the list page's response becomes 20 tasks, each naming its own parser
{
  "dsl_version": 1,
  "globals": { "base_url": "https://www.ah.gov.cn" },
  "policy": { "on_missing": "drop", "on_error": "raise" },
  "steps": [
    { "key": "items",
      "parse": { "items": [
          ["py","get","text"],                           // the Response is a dict; take the body first
          ["css","nodes","a[href*='/public/1681/']"],    // what is selected is `self`: node handles
          ["py","slice",":20"],
          ["each", {                                     // the second round of `css1`, per node
              "_url":    [ ["css1","@href",""], ["py","urljoin","$globals.base_url"] ],
              "request": [ ["ctx","map", {"url": "locals._url"}] ],   // → {"url": …}
              "then":    [ ["const","article"] ]         // this task's own continuation chain
          }] ] },
      "out": "TaskList" }
  ]
}
```

```jsonc
// 3) "article": one article's response becomes one record
{
  "dsl_version": 1,
  "policy": { "on_missing": "drop" },
  "steps": [
    { "key": "article",
      "parse": {
        "url":      [ ["py","get","url"] ],
        "title":    [ ["py","get","text"], ["css1","text","h1"], ["py","normalize_space",""] ],
        "pub_time": [ ["py","get","text"],
                      ["css1","@content","meta[name=\"PubDate\"]"], ["py","strip",""],
                      ["py","parse_time","zh"] ],
        "content":  [ ["py","get","text"], ["css","remove","script,style,noscript"],
                      ["css1","html","div.j-fontContent"], ["py","html_to_markdown",""] ]
      },
      "out": "Article" }
  ]
}
```

**The host walks the queue** (it owns the network, the concurrency and the retries):

```python
queue = [("seed", "https://www.ah.gov.cn/public/1681/list.html")]
while queue:
    key, value = queue.pop()
    product = run_chain(key, value)                       # compile + run, answering `call`s
    for task in tasks_of(product):                        # TaskList: {request, then}
        queue.append((task.then, fetch(task.request)))    # send now, parse by that task's key
```

```text
seed(the seed URL)  → TaskList[1]   ⇢ one fetch → list_page(Response)
list_page(Response) → TaskList[20]  ⇢ twenty fetches (host concurrency) → article(Response) × 20
article(Response)   → Article       → one record
```

**Measured on the current commit** (the field maps, with `each` over a one-element list standing in for a
step — the same semantics): the list page's map gives
`{'items': [{'request': {'url': '…/public/1681/1.html'}, 'then': 'article'}, …]}`; the article map gives
`{'url': '…/1.html', 'title': 'Notice on Issuing the List', 'pub_time': '2026-09-24',
'content': 'Body line one.\n'}`. **Three constraints were found by running them:**

- **`css` is not `css1` per item.** `["css","@href",""]` yields a **list** (every match), so the following
  `py.urljoin` fails with `UP2-E2002`; a per-item read must be `css1`. (The v0.1 walkthrough wrote `css`
  and had never been run.)
- **A `Response` must be taken apart first.** `css` consumes text or a node, so every chain that parses a
  response starts with `["py","get","text"]` (§4.1); resolving a relative link against the final URL uses
  `["py","get","url"]`.
- **Every value of a field map is a chain**, so a task item is assembled with `ctx.map`: `_url` computes the
  link and `"request": [["ctx","map",{"url":"locals._url"}]]` turns it into the request dictionary. A
  nested object literal there is `UP2-E1004` (measured); a local plus `ctx.map` is how a nested product is
  built.

`["py","str",""]` in the seed step is the "read my own input" workaround of §13 O5: it is the identity on a
string, but a real identity action would read better.

### 11.2 The fields it extracts, and the registered types

`Article` is a host-registered type: the article story ends with `Article(**fields)`, which is where the
shape is validated — a misshapen record is reported in the article story, while that response is being
parsed, and not at the end of the flow. The **collection** of articles is what the host accumulates: it
runs the article story once per task, so N responses give N `Article` products (the host may then build a
`ArticleList(*articles)` if its own API wants one).

Handing each record to the business is the host's step; a story can also do it with a `call` appended to
the article story:

```jsonc
{ "key": "store", "call": "host.store_articles", "with": { "table": "articles" }, "out": "dict" }
```

Two of the old flow's needs disappear here: `channel` / `source` / `region` are ordinary `["const", …]`
fields of the article story (§8.1), and "which of the two detail rules applies" is the **host's** question
(§11.3, item M) — the story never guesses.

`$article`'s old schema description survives as `Article`'s fields:

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

### 11.3 Key points, and where the legacy elements go

| Blocker in draft `02` | How this design dissolves it |
|---|---|
| **A** missing node-splitting semantics | all of it is one chain: `["css","nodes",…]` → `["py","slice",":20"]` → `["each", {…}]` (§7) |
| **B** can an argument position reference an earlier product | yes: the parameter kind is `ref_or_literal` (`02` §3.2), so `["py","urljoin","$globals.base_url"]` holds, and so does a reference to an earlier step's field |
| **C** a non-empty `headers` has nowhere to land | the host's request layer; when a story must describe one, the `Request` product carries `headers` (§4.1) |
| **D** mutually exclusive sources for `channel`/`source`/`region` | always `["const", …]` inside a step's field map (§8.1) |
| **E/F/G** propagation container / single route / per-item semantics | propagation = fields without `_` are visible to later steps; there is no routing to write; per-item is switched on explicitly by an `each` stage (§7) |
| **M** the old "2 detail rules + `url_patterns`" | the **host** picks the story by URL (`07` §3); the story no longer guesses. `variants` (v0.1 §12) is dissolved with it |
| **N** `cast datetime` conflicts with the export encoding | the `py` vocabulary has no `datetime`; time goes through `py.parse_time`, which outputs `str` |
| **O** `parser="none"` conflicts with the dispatch table | there is no dispatch table and no `parser` field: a story ends where its last step ends |
| **P** `list_title` has nowhere to go | it is an ordinary field of the step that produced it, or the host carries it in the next run's input |
| **Q** `ctx.globals` idles empty | `globals` holds only static constants; the run's input travels as the first step's input (§2) |
| **R/S** the `result` syntax and the `outputs`/`produces`/`result` boundary | all three are gone: the field map is the product, `out` names its type (§9) |
| **T/U/V/W** two propagation channels / ctx write permission / `list_title` lost / error policy | one propagation rule (§8); the write surface is `locals` (`02` §6.8); `list_title` is an ordinary field; the kernel only emits the tri-state (`02` §5) |

| Legacy element | New landing place |
|---|---|
| `task_name` / `channel` / `region` | a `["const", …]` field inside a step, or the caller's input |
| `request` / `request.url` | a task's `request` (§4.1), or the host's own request layer |
| `input_format` | deleted: the consuming operator decides the format, under the run-scoped cache (§6) |
| `nodes` (splitting + truncation) | one chain: `["css","nodes",…]` → `["py","slice",":20"]` → `["each", {…}]` |
| `fields` | a step's field map (semantics unchanged) |
| `fields.headers` | the host's request layer |
| `fields.referer_info` | deleted (fields without `_` propagate to later steps) |
| `url_patterns` | the host picks the story |
| `detail` (several rules) | several stories, or one story with a registered type per shape |
| `tpl_key` / `root_domain` | **not in the story format**: storage identifiers of the L3 binding layer (`04` §2) |

---

## 12. Deviation records

### 12.1 `D-03-3` — the story model replaces the node model

v0.1 described a graph: three node types (`seed` / `parse` / `emit`), an `entry`, `nodes` with `next` /
`routes` / `default_route`, `emit` export shapes (`record` / `flat` / `request`), a `result` assembly
template and a lint family that policed the graph (reachability, cycles, in-degree ≤ 1, terminal count).

It is replaced by **one linear story with typed steps and two effects**. The rulings, with the alternative
each one rejected:

| # | Ruling | Rejected, and why |
|---|---|---|
| R1 | dispatch is by the **product's type name**, host side | a `routes` table inside the story: it duplicates the decision the host already makes (which story suits this response) and creates a second dispatch vocabulary |
| R2 | a story is **linear**, no in-story branching | the v0.1 graph: cycles/joins/terminals needed lints and executor branches no case study asked for |
| R3 | no node types; a step consumes whatever came before it | `seed`/`parse`/`emit`: roles that made the executor branch and made "what is my input" a question |
| R4 | no `input` field | an explicit input reference on every step: the upstream value already is the input |
| R5 | `out` is declared per step, validated at the step boundary with the host's constructor | validating only at the run's boundary (too late to name the failing step); comparing with a Python class name (impossible: host objects cannot enter a chain — measured `UP2-E2009`) |
| R6 | products are JSON; Pydantic instances live host-side | carrying live objects: it would end replayability and the single exit |
| R7 | a type is a constructor (`Cls(**dict)` / `Cls(*list)`) | typing every collection as `list`: the element's type is lost and the host cannot dispatch on it |
| R8 | `parse` and `call` are mutually exclusive keywords | one polymorphic "work" keyword: three shapes in one field, which read as noise |
| R9 | effects are **step-level only** | effects inside `each`: nested suspension for a result that is still serial |
| R10 | the request effect's answer is a fixed `Response` | plain body text: cheaper, but loses the status (a 404 page would be parsed as content) and the post-redirect base URL |
| R11 | `call` may have side effects but must return a serializable receipt | a callback returning nothing: it would break the single exit and make a run unreplayable |
| R12 | built-in types are exactly `Request` and `Response` | a larger built-in vocabulary (`Url`, `Page`, `Json`): business meaning in the engine |
| R13 | one batched effect carries a fan-out; concurrency is the host's | forking a run per item as the only way to fan out: it makes concurrency a host convention instead of a first-class effect |
| R14 | a request is a **hand-off**, not a suspension: the step produces a `TaskList` and its run ends; each task carries `{request, then}` and the response becomes the input of the chain `then` names | resuming the same run with the response: it makes "which parser for this response" an implicit consequence of one story's shape, while the key is exactly what must travel per response |
| R15 | the default unit is **one story per layer**, joined by tasks | keeping the whole flow in one story: it forces one run to span several network boundaries whose answers belong to *different* parsers |

### 12.2 `D-03-2` — materialization is on demand (unchanged from v0.1)

The primary input used to be materialized once by the `seed` (`input_format`, later renamed `format` on
`parse`). That turned the entry point into a format registry and made every chain name a format it might
never consume. The ruling: the consumer materializes on demand, and a run-scoped cache keeps it to one
parse per document (§6). The cache lands with this layer.

### 12.3 `D-03-1` — `presets` is retired (unchanged from v0.1)

Draft `04` used `parsers` as the container name, this design renamed it `presets`, and the L2 iteration
redesign retired both along with the container in favour of `each`'s inline field map. If reuse is ever
wanted it belongs to a **callable stage** (a named chain used like any other stage), never to a second
argument shape of `each`.

---

## 13. Open questions

| # | Question | Status |
|---|---|---|
| O1 | the type registry API (name and shape: `register_type` / `register_model`, and whether it takes a constructor, a schema, or both) | open |
| O2 | how `call`'s arguments are written (`with` on the step; bound at registration; or both with the step overriding) | open |
| O3 | is `key` required on every step, or only when something references it? | open |
| O4 | may a step override the chain-level `policy`? | open |
| O5 | an explicit "return the input unchanged" action: a step that reads its own input (the seed step, whose `url` *is* the run's input) has no clean spelling today — `["py","str",""]` is the identity on a string (measured, used in §11.1) and `["ctx","set","locals._u"]` passes any value through (measured) but reads as a side effect | open, small |
| O6 | how far the trace goes (`06` §5.1's structure) and whether a recorded run is the replay format | open, belongs with the trial UI |
| O7 | the **name of the task product type**: `TaskList` (used throughout this note, since its items are `{request, then}` and not bare requests) versus keeping the v0.1 name `RequestBatch` | open, naming |
