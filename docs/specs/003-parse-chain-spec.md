# uniparser2 Design · 03 Parse Chain Spec

> **Status**: design draft **v0.3** (the story bundle's keys, its jumps and its executor), rewritten around
> the **story** model (v0.1 described three node types and a graph). **Upstream**: `00`, `01`, `02`, `07`.
> **What this document answers**: what a chain is (a **story**: a sequence of named typed steps), what a
> step is (`body` / `call` plus `type`), how a product carries a **type name**, the one suspension
> mechanism (**effects**: `Request`, `RequestBatch` and `call`), how `next` / `collect` resolve, and how a run
> proceeds.
> **Supersedes**: v0.1 of this note — the three node types (`seed`/`body`/`emit`), `entry`/`nodes`/`output`,
> `next`/`routes`/`default_route`, the `emit` export shapes and the graph lint family — see §12.1 for the
> ruling and `D-03-3` for the rejected alternatives; and v0.2's `chains` table, `key` / `out` spelling and
> derived exit — see §12.4 (`D-03-4`). v0.1's materialization ruling (§6 here) and its `each` ruling (§7
> here) are carried over unchanged.
> **Implemented**: the operator layer (`02`), the field-chain evaluator (`compile_field` + `eval_field`),
> the **first story executor** (`core/story.py`: `compile_story` / `start` / `run.go` / `run.feed`),
> which `up2 lint` and `up2 trial` both reach, the **type registry** the step boundary builds from
> (`core/types.py`, §3.2), the **run-scoped materialization cache** (`core/materialize.py`, §6), the
> **trace** (`core/trace.py`, §4.4) that `up2 trial --trace` reports, the **declared `entry`** with the
> unreachable-step lint (`UP2-E1018`), and the **whole-chain reference** that replaced the identity
> stage (§2).

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
  "globals": { "base_url": "https://www.ah.gov.cn" },   // chain-level, read-only constants
  "entry": "start",                                     // the step the run starts at
  "steps": [
    { "name": "start",   "body": { "url": "$in" },
      "type": "Request",      "next": "seeds"   },        // who receives the answer
    { "name": "seeds",   "body": { "items": [ /* … */ ] },
      "type": "RequestBatch", "next": "items"   },
    { "name": "items",   "body": { "items": [ /* … */ ] }, "type": "ArticleList" },
    { "name": "store",   "call": "host.store_notices",
      "args": { "table": "notices", "rows": "$in" }, "type": "dict" }
  ],
  "collect": "store"                                         // whose products are the run's output
}
```

**One site, one JSON.** A site bundle carries everything a site needs: the story's steps, each of them
naming what parses what. Several channels live in one file — each channel's seed, its own list parser and
its own item parser are steps — instead of being scattered over a host table. The file is still plain data,
so `dumps(loads(x))` stays a fixed point and a bad bundle still fails at compile time.

| Field | Required | Description |
|---|---|---|
| `globals` | no | the chain-level **static** environment (such as `base_url`); read-only for every step |
| `entry` | yes | the **name** of the step the run starts at, with the caller's value as its input |
| `steps` | yes | the sequence; **array order is execution order**, and `next` jumps within it |
| `collect` | yes | the **name** of the step whose products are the run's output, collected in order as a list |

**There is no `chains` table** (`D-03-4`). A parse rule is a **step**: a named chain and a step's `body`
were the same object — a field chain over one input — so the table was a second namespace for it, and only
the host (which looked the chain up) could say which rule applied. Now the kernel resolves it, and the
routing is visible in the bundle.

**There is no `input` field.** The first step's input is the value the caller passes to the run — the run
starts at the step **`entry` names**, with that value as its input; every later step's input is what the
step before it produced (or the host's answer, §4). A step that needs a value from further back writes a
reference (`$<step name>.field`); a step that needs a constant reads `$globals`.

**`$in` names this step's own input.** It is a reserved reference root next to `globals` / `locals`, so a
step reads its own input without writing it to `locals` first. It resolves through the same path walk as any
other root (a mapping by key, a sequence by index, a host object by `getattr`), and a step name may not be
`in`.

**A chain may be a reference, and that is the only identity.** Wherever a chain is expected — the value of a
field-map entry, or a step's `body` — a **string beginning with `$`** is accepted and means "the value the
reference names, unchanged": `"url": "$in"` is the step's own input, `[["py","urljoin","$in.url"]]` roots a
chain in a field of it, and a chain may also **open** with a reference (`["$globals.base", ["py","strip",""]]`).
This is the same spelling `args` already uses for an argument, and it is the **only** way to express identity
— there is deliberately no single-element stage form. Reference rules are unchanged: an unknown root is
`UP2-E1006`, and a step may not name itself.

**The story's start and exit are declared**, never derived: `entry` names the step the run begins at and
`collect` names the step whose products are the run's output, collected in order as a list. While execution was
strictly linear "the first step" and "the last step" said them; with `next` a step can be visited more than
once and the last step is not unique, and the first step is a fact of the array rather than of the story.
A step that no `next` reaches and that the fall-through never passes is **dead**, and lint says so
(`UP2-E1018`, §10 L13).

### 2.1 The step

| Field | Description |
|---|---|
| `name` | the step's name: unique in the bundle, not a reserved root (`globals` / `locals` / `in`), and what `next` / `collect` / a reference (`$reqs.items`) use |
| `body` **or** `call` | what the step does — mutually exclusive, told apart by shape and by keyword |
| `type` | the **type name** of the product (§3) |
| `next` | on a step whose `type` is `Request` / `RequestBatch`: the **step that receives the responses**. Required there, refused elsewhere; the step-level default, which a single task item may override (§4.1) |
| `args` | only with `call`: the arguments handed to the host function. A reference is resolved in this step's scope, so `"rows": "$in"` passes the step's own input (§4.2) |

**One story per site, not one per layer.** A story runs from the first request to the last product: a
request **suspends** the run, the host sends it, and the answer goes to the step `next` names so the
**same** run continues (§4–§5). Several channels live side by side in the same bundle — their seeds, their
list parsers and their item parsers in one file (§11) — and nothing in the story knows a domain name or a
business key.

**`body`** takes one of three shapes:

| Shape | Meaning |
|---|---|
| a string beginning with `$` | **one reference**: the value it names, unchanged (§2) |
| an array (`[ ["css","nodes","ul a"], … ]`) | **one chain**: one value in, one value out (`02` §1); its first element may be a `$` reference |
| an object (`{ "title": [ … ], "body": [ … ] }`) | **a field map**: every chain is fed **the same input** and the product is one dictionary |

The field map is the workhorse. A chain is a one-value pipeline, so "pull the title, the body and the date
out of **one** document" cannot be written as a chain at all — measured: the stages run in sequence, so a
second `["css1","text","div.content"]` receives the first stage's output, not the document. A `_`-prefixed
field name is a temporary of that step: readable by the later chains of the same step, never a key of the
product. A field-map value that is a whole-chain reference (`"url": "$in"`) is that value with no stage
evaluated for it at all.

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
| built-in **effect** types | `Request`, `RequestBatch` | `Request` = one request; `RequestBatch` = a batch of tasks (`items`). Producing either hands the work to the host and **suspends the run** (§4) |
| host-registered types | `NoticeList`, `Article`, … | declared with `type`; the host registers name → constructor (`register_type`, §3.2) |

The built-in set is deliberately **closed at `Request` / `RequestBatch` plus the JSON basics**. Anything
with domain meaning is the host's registration, so the engine keeps no business vocabulary (`07` §3's
zero-coupling criterion; acceptance item 8 there). Those nine names need no registration
(`null` / `bool` / `str` / `int` / `float` / `list` / `dict` / `Request` / `RequestBatch`); every other
name is looked up in the host's registry at the step boundary, where an unknown one is `UP2-E1011`
(§3.3).

**There is no declared type for an answer.** A request's answer is whatever the host `send`s back
(§4.1): the story continues with it **unwrapped and unconverted**, and reads it with `py.getattr` (a
host object's own attribute) or `py.getitem` (a mapping key). `Response` used to be a four-key
dictionary in this table; it is **deleted** — an incoming answer is the host's own fact, and only the
outgoing `Request` stays a neutral structure so a story's intent stays library-independent.

### 3.2 A type is a constructor

| Product | How the declared type is built |
|---|---|
| a dictionary | `Cls(**payload)` |
| a list | `Cls(*items)` |
| anything else | `Cls(product)` |

So a collection carries a type of its own (`NoticeList(*items)`, `RequestBatch(*tasks)`) instead of
degrading to the built-in `list`; the built-in `list` name is left for collections that need no meaning.

The host registers one: **`register_type(name, constructor)`** (`unregister_type`, `type_names`,
`get_type` beside it). A name is a **string the step writes**, the constructor is a class or any
callable, and the registry is process-wide host state exactly like `register_udf` — not part of the
bundle, so a story stays library-independent data (§3.1). A later registration replaces an earlier one,
and a host registration wins over a built-in name.

```python
# host side, once, before the run
from dataclasses import dataclass
import uniparser2 as up2


@dataclass
class Article:                      # the declared shape; the fields are the product's keys
    url: str
    title: str
    pub_time: str = ""


up2.register_type("Article", Article)

bundle = {
    "steps": [
        {
            "name": "record",
            "body": {"url": [["py", "getattr", "url"]], "title": [["css1", "text", "h1"]]},
            "type": "Article",
        }
    ],
    "collect": "record",
}
run = up2.start(bundle, response)   # a missing `title` fails at this step, not at the exit
```

### 3.3 Where validation happens

At the **step boundary, by the kernel**, using the constructor the host registered for `type`: the
kernel builds the declared type from the JSON, reports a mismatch at the step that produced it, and continues with
the JSON.

A **name that no host registered** is `UP2-E1011`, reported at the step that declares it and listing the
names that are registered (the built-ins included). The check cannot move to compile time: `03` §2's
two file shapes are both compiled without a host — a recipe may be linted in a process that never
registered a type — so the boundary is where the registry is known for sure.

**A constructor that raises is `UP2-E2019`**, also at that step, with the constructor's own exception
text in `reason` (its message is the useful half of the diagnostic) and the step's JSON Pointer. The
type name, the reason and the pointer are everything an author needs to see which key is wrong: a
dataclass reports `Article.__init__() missing 1 required positional argument: 'title'`.

**A value that flows may be a host object; a step product must be JSON.** A response object, a
`selectolax` node handle and anything a `udf` returns may be a step's input, a `call` argument or an
answer — they are carried by reference, never copied, wrapped or converted on the way in, and
`py.getattr` reads them. The step boundary is where that stops: after the type constructor runs the
product is JSON again, so the single exit (`pack`, `UP2-E2003`), the snapshots and the trace stay
comparable. The constructor is a **validator, not a container**: building `Article(**fields)` proves
the record's shape, and what the step hands on is JSON, never the `Article` instance. What continues
is **the constructor's own answer**, so a constructor that answers JSON built from the product — a
plain `dict`, or a dataclass whose fields are exactly the payload — decides the product, while any
answer that is not JSON (an object, a handle) is refused by `pack` at that same step (`UP2-E2003`).
`type` names a type; it never means "the chain is carrying a Python object" — it means "the product
has this shape". Pydantic instances therefore live **only on the host side**:
`Article.model_validate(product)` when the host receives a product, `model_dump()` when a callback
returns one. Measured: a host function returning a `dataclass` instance is still rejected at once
(`UP2-E2009 udf.make_article returned a value that cannot be a product: Article`).

---

## 4. Effects: a request suspends the run, `call` too

An **effect** is a step whose product must be produced by the host. The kernel never performs it: it hands
over a description, waits, and **resumes with what `send(...)` brings back** (§5).

### 4.1 `Request` — one request or a batch, and who receives the responses

```jsonc
{ "name": "seeds", "body": { "items": [ /* … */ ] }, "type": "RequestBatch", "next": "items" }
```

| The step produces | The host does | What it `send`s back |
|---|---|---|
| `type: "Request"` | sends it | **one answer** — whatever its own HTTP client returned, unwrapped |
| `type: "RequestBatch"` | sends them all, at its own pace | **one answer per task**, in the tasks' order |

So a request **suspends** and the run continues — the story is one flow, from the first request to the exit.
**The kernel, not the host, decides what happens to an answer**: `next` names the step that receives it
(§4.1.1), so the parsing stays in the story data and the host only sends. Which HTTP client, how much
concurrency, how many retries, what headers — all of it is the host's, and the request dictionary it
receives is all it needs.

**The package offers a default for that host side** (`uniparser2.net`, change
`default-host-downloader`): a synchronous, **standard-library only** downloader that takes the request
dictionary the kernel hands over and answers with a response carrying `text` and `url` — the two a
story reads with `py.getattr` — plus a request cache under `.cache/requests/` (never committed), so a
second run replays the answers instead of the network. It is a **default**, not a requirement: a host
with sessions, retries, cookies or rate limiting brings its own client and ignores it, and the
kernel is unaffected either way (it performs no IO).

**`next` is not part of the request structure.** The HTTP fields sit at the task's top level and `next`
rides beside them (a task is a request with exactly one extra key), but the kernel strips it before the
effect is handed over: **the host never sees `next`**. That flatness is not cosmetic — a field map's value
must be a chain, so a nested `{"request": {…}}` item is `UP2-E1004` (measured) and would force the link
through a `_url` local plus `ctx.dict`. Flat keeps the common case one key longer than the request it
describes.

#### 4.1.1 `next`, and the per-task override

| Where it is written | What it says |
|---|---|
| on the step (`"next": "items"`) | the **default** receiving step, for every answer of this step |
| in a task item (`{"url": …, "next": "items"}`) | this task's answer goes to that step instead |

The receiving step runs **once per answer**, in task order, with that answer as its input. A `Request`'s
answer continues the run: the receiving step's product becomes the input of the step after it. A
`RequestBatch` collects the receiving steps' products **in task order** into a list, which becomes the
input of the step after the **last** step that received an answer — so a fan-out rejoins the linear flow
once, however many tasks it carried. A receiving step that is itself a request suspends the run again, and
the answers to *it* are resolved inside the same fan-out before the join.

The `Request` structure is v0.1's built-in, unchanged:

| Key | Type | Default |
|---|---|---|
| `url` | `str` | **required** (a request without a `url` is `UP2-E2005`) |
| `method` | `str` | `"GET"` |
| `headers` | `json` | `{}` |
| `params` | `json` | `{}` |
| `body` | `str` (**base64**) | `null` |
| `json` | `json` | `null` |
| `timeout` | `float` | `30.0` |

**The body is base64 text.** A body is binary, and the request dictionary is JSON throughout — it
lives in chain data, in a cache key and in a journal — so `body` carries base64 and the downloader
decodes it before sending. A request with a `json` key sends that value as JSON instead, and the two
are alternatives.

**There is no `follow_redirects` key.** It is a parameter of the **request method** — of the HTTP
client, not of the request a chain declares: whether a redirect is followed is the client's business,
like its retries and its proxy. A chain says *what* to fetch; the client says *how*. The downloader
follows redirects, and the answer carries the **final** URL, so a chain that needs to know where it
ended reads `url`.

The kernel assembles and **never sends**: which HTTP client, how much concurrency, how many retries,
whether to add hotlink-protection headers — all of it is the host's.

**The answer has no type of its own.** It is exactly what the host `send`s back, with no kernel-side
conversion: an `httpx.Response`, a `requests.Response`, a `selectolax` node or a plain mapping. A step
reads it with `py.getattr` (its own attribute — `["py","getattr","status_code"]`) or `py.getitem` (a
mapping key), and a **dotted reference works on either** (`$resp.headers`, `$in.request.url`). A step
therefore picks the host library's own attribute names; that coupling is recorded in the story, and a host
may adapt before `send` if it wants one spelling for several clients.

A step that parses an answer object therefore starts by reading the body
(`["py","getattr","text"]`), and a step that resolves relative links reads the final URL
(`["py","getattr","url"]`).

### 4.2 `call` — the host function

```jsonc
{ "name": "store", "call": "host.store_notices",
  "args": { "table": "notices", "rows": "$in" }, "type": "dict" }
```

The host runs the function and sends back the receipt; the receipt becomes the step's product, and a
product must be JSON like any other (§3.3). A function with side effects is legal **here and only here**:
the kernel stays pure, and the receipt keeps the single exit.

**The effect carries the function and its arguments, and nothing else** — an effect has no hidden input
slot. A `args` value is a reference or a literal, resolved in the step's scope, so the step's own input
travels explicitly as `"rows": "$in"`. That keeps every argument visible in the bundle, and it is why the
host function's signature is exactly the `args` keys.

### 4.3 Effects are step-level only

Both `call` and a request-producing step are written at the **step** level, never inside a chain or inside
an `each` field map. `call` suspends a run that continues afterwards (one suspension at a time, so the
executor needs only **flat** suspension); a request step suspends too, and the answers resume **the same
run** — there is no hand-off.

- A fan-out is one `RequestBatch` product, not N effects inside `each`.
- **Concurrency is the host's**, exercised on the task list it already holds: it may send 50 requests in
  parallel because the step handed it 50 tasks.
- A nested effect (a request decided inside `each`, say) would have forced nested suspension and still
  produced serial requests. Ruled out (`D-03-3`).

### 4.4 Trace versus suspension

| | What it carries | Who consumes it |
|---|---|---|
| **trace event** | one per **evaluated stage**, plus one per suspension: the step, the field-map key, the fan-out index, the stage's operator / action, its **compiled** parameters, the input and output views (`type` / `preview` / `size`), the state and the timing | debugging, the trial UI (`06` §5.1), `up2 trial --trace` |
| **suspension** | a `Request` / `RequestBatch` (the host sends; the kernel routes the answers) or a `call` (the host returns a receipt) | the host, which must `send` an answer before the run continues |

The host sees every step's product and has to answer at every suspension. With the answers recorded, a flow
replays deterministically: the kernel never performs IO, so replayability (`01` §1) is kept. **The trace is
not that recording** — it is lossy by construction (previews, not values) and it holds no answer; the
replay format is the host's own log of the suspensions it answered (`13` O6).

A trace is collected only when the caller asks for one (`start(bundle, value, trace=…)` /
`eval_field(…, trace=…)`), it lives in memory for as long as the run does, and it never changes what a
run does; the structure is `06` §5.1.

---

## 5. The run loop

```text
start(bundle, value) -> run                    # compile the bundle, then run to the first suspension
run.go()   -> ("request", request, next_step)
              | ("batch", tasks, default_next)
              | ("call", name, with)
              | ("done", product)
run.feed(answer) -> the next effect / done     # answer = the answer(s) or a receipt
```

`start` compiles and drives to the first effect, **from the step `entry` names** with the caller's value as
its input; `next()` reads the **current** effect (it is idempotent, which is what makes the loop below
work); `send(answer)` resumes and drives to the next effect. A run whose effect is `("done", product)`
stays done.

The kernel side keeps its invariants (no IO, no threads, one exit, still synchronous); the host side is
ordinary code, and **sync or async is entirely the host's choice** — the kernel's part is a plain
generator either way:

```python
run = up2.start(bundle, seed_url)
while True:
    effect = run.go()
    kind = effect[0]
    if kind == "done":
        return effect[1]                             # the exit step's products, in order
    if kind == "request":
        run.feed(fetch(effect[1]))                   # the answer is whatever the client returned
    elif kind == "batch":
        run.feed([fetch(task) for task in effect[1]])   # concurrency is the host's
    else:
        run.feed(handlers[effect[1]](**effect[2]))   # a `call`: the receipt is the product
```

A **failed stage raises** (`Up2Error`) instead of becoming an effect: the effect vocabulary has no failure
member, and a run that could not produce a step's product must not hand the host a plausible-looking
request. A suspension is not an error, so `up2 trial` on a story prints it and exits 0.

An `asyncio` host awaits its fetches inside that same loop (`await asyncio.gather(...)` and one
`run.feed`); a thread-pool host does the same with `run_in_executor`. Neither shape leaks into the kernel.

---

## 6. On-demand materialization and the run-scoped cache

**Status**: the operators materialize on demand (measured: `css1` on HTML text, `json` on JSON text and
`xpath` on XML text all return the parsed result), and the cache described below is **implemented**
(`core/materialize.py`, change `add-materialization-cache`). Consumers take their artifact through it
instead of building one per stage, so feeding the same text to several `css`/`json` stages is one parse
per run.

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

- **Scope**: it lives with one run and is released with it. It is carried by the run's evaluation scope
  and inherited by every nested scope (`each`'s per-element scope included), so all of a run's steps and
  fields share one cache; nothing is shared across runs, so no `Opaque` handle outlives the run that
  produced it and two runs cannot observe each other.
- **Key**: the target format plus the source value — object identity first, a content hash on a miss.
  Hashing a 5 MB text costs a couple of milliseconds against the ≈110 ms parse it saves. **Corrected by
  the implementation**: identity and digest are decided in one lookup on the source's own hash bucket —
  the entry is accepted when its source *is* the queried object or its digest equals the queried text —
  and each entry holds a strong reference to its source, which is what makes the identity check sound (a
  collected string cannot have its address reused inside an entry). The observable contract is unchanged:
  an equal but distinct string hits, and a hash collision or a reused address is a miss.
- **Bound**: `MAX_MATERIALIZE_BYTES` (64 MiB by default, `01` §9) with LRU eviction, accounted in
  **materialized bytes** — not in source-text bytes, because the amplification differs per format
  (measured: a selectolax DOM is ≈24× its HTML text, a JSON tree ≈2.2–2.7×). Each consumer measures its
  own artifact: HTML by the document's serialization (a selectolax tree is a 96-byte Python handle
  whatever its size — measured — so `sys.getsizeof` measures nothing), XML by `tostring`, JSON by a
  bounded walk of the tree's own footprint. The measures are proportional, not RSS.
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
  install line, exactly like `css`'s selectolax. The three formats that exist today carry one entry each
  in the consuming operator; the entry contract is the same one a `tomllib` / `csv` / YAML consumer would
  use, and no such consumer exists yet.

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
| empty collection | `each` on an empty list yields an empty `list` — an empty list page is a normal result |
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

**`$locals` is shorthand for this step** (including this step's `_` keys) and is valid only inside the step
that declares the field map. **A step cannot reference its own key** (`$reqs.items` written inside `reqs`'s
own field map ⇒ `UP2-E1006`, whose message points at `$locals.items`). These two are the mistakes chain
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
| `public` | the whole **run** | writable (`ctx.set`/`del` accept `public.*`); **not** chain data, so it never enters the fingerprint |
| a step's product | from that step to the end of the story | read-only; **fields without a `_` prefix join automatically** |

The three scopes read as **constants / shared / private**: `globals` is what the chain declares, `public`
is what the run remembers, `locals` is what one field computes. `public` is the run's own notes — a
value written in one node is readable in the next, and a value written inside an `each` element outlives
the element, because the scope is run-level rather than per-field. It is **not** a writable `globals`:
`globals` is covered by the fingerprint, so writing it would break "same chain, same result".

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
rows = completed(up2.start(collection_story, page))     # the run's input is the page text
for item in rows:
    html = fetch(item["url"])                           # the host owns the network
    detail = completed(up2.start(detail_story, {"text": html, "meta": item}))
```

`completed(run)` is the host's own little loop: it answers each effect from the table of fetches and
handlers it holds, and returns the product of `("done", product)` (the code is in §5).

This is the **explicit** version of what draft `01` expressed with a `doc` table + `referer_info` +
`tpl:` dispatch: cross-story passing is visible in the data flow. A story may equally fetch for itself
(§4.1) — one run then spans both layers, because a request suspends the run instead of ending it; the host
still owns its concurrency, retries and caching policy around the effect. If a host genuinely needs the
`doc` table and `tpl:` dispatch, it can build them on top of its store and the caller; the kernel need not
know.

---

## 9. The exit and schema

- **The exit is the product of the step `collect` names**, collected in order as a list, of the type its `type`
  names. There is no assembly template and no export mode: a step's field map already produces the
  dictionary, and a product that needs a shape gets a registered type instead of a template.
- **A `schema` is the registered type itself.** Validation is the step-boundary construction of §3.3;
  misshapen JSON is reported at the step that produced it with `UP2-E1011` (an unregistered name) or
  `UP2-E2019` (the constructor refused the product), and the boundary check that holds whatever the
  `type` says is §3.3's invariant — **a product must be JSON** (`pack`, `UP2-E2003`).
- **A step always produces a product or fails**: a query that matched nothing is a value (its shape's
  empty value, `01` §4.2), so there is no "skipped step" and no `null` invented for one. A step that
  cannot do its work fails the run at that step with its code.
- The old `result` template (and the reference categories it needed) is **dissolved**: its job was to
  assemble the export, which the field map now does directly.

---

## 10. Compile-time lint checklist

| # | Rule | Code |
|---|---|---|
| L1 | the required top-level fields exist (`entry`, `steps`, `collect`); `globals`, if present, is an object | existing (`UP2-E1005`) |
| L2 | every step declares **exactly one** of `body` / `call`, `args` only with `call`, `next` only on a request step, and no unknown bundle/step key | existing (`UP2-E1005`) |
| L3 | step names are unique and not reserved roots (`globals` / `locals` / `in`) | existing (`UP2-E1009`) |
| L4 | step count ≤ `MAX_STORY_STEPS` | existing (`UP2-E1012`) |
| L5 | a reference names `globals` / `locals` / `in` / another step; the path exists in the target product; a step must not reference its own name | existing (`UP2-E1006`) |
| L6 | a cross-step referenced key carries no `_` prefix | existing (`UP2-E1014`) |
| L7 | every stage (including the sub-chains of an `each` field map) passes operator validation | existing (`UP2-E1001`…`E1005`) |
| L8 | `type`, when written, is a non-empty string; a name that is neither a built-in nor registered is `UP2-E1011` and a constructor that refuses the product is `UP2-E2019` — both at the **step boundary**, because compilation never sees a host's registry (§3.3) | existing (`UP2-E1005`), new (`UP2-E1011` / `UP2-E2019`) |
| L9 | every `next` (step-level and per task), `entry` and `collect` resolves to a step of the bundle | new (`UP2-E1016`) |
| L10 | no resource limit is exceeded (`01` §9) | existing (`UP2-E1012`) |
| L11 | an operator's optional dependency is installed | existing (`UP2-E1107`) |
| L12 | the story's **flow is acyclic**: drawn over the steps from the entry, with the program counter's own edges — the next step in array order, or the step a request step's `next` names — no step is entered twice | new (`UP2-E1017`, §12.5) |
| L13 | **every step is reachable from the entry**: a step the walk above never arrives at is dead | new (`UP2-E1018`, §12.6) |
| ~~L20~~ | **withdrawn** with `presets` (`02` §6.9); the number stays retired rather than reused | — |

L5 is checked against every other step's name rather than "an earlier step": with `next` a jump may reach a
step that is written later in the array, so "earlier" is no longer a static fact. What remains static is
that the name exists and that a step never references itself (the compile error points at `$in` / `$locals`).

L9's second half in v0.2 ("a request is never written inside a chain") is **vacuous** now: `type` is a step
key, so a request cannot be declared anywhere else. A task's own `next` is data produced by a field map, so
its target is checked when the batch is handed over (the same `UP2-E1016`).

The v0.1 graph rules are gone with the graph: `entry`/`nodes`/`output` shape checks, `next`/`routes`
mutual exclusion, `routes` ⇒ `default_route`, target existence, reachability/orphans, acyclicity,
in-degree ≤ 1, terminal count, `route_field`, `seed.inject` coverage, the `result`-template rules. The
`UP2-E1101`–`E1106` codes they used are **retired, not reused** (`02` §7.1's rule), which is a change to
`02`'s error table and lands with the implementation change. **Acyclicity is the one rule of that family
that came back**, and it did not reuse a retired number: it is L12 / `UP2-E1017` (§12.5), it is drawn over
the flow the executor actually walks rather than over a node graph with routes and terminals, and it
rejects a story that *loops*, not one that merely jumps backwards.

**A loop among steps is `UP2-E1017`** (§12.5): `next` may name any step, including one written earlier, and
the samples' own fan-out shape does exactly that — but the run may not come back to a step it is already
executing. The rule walks the flow §5's loop walks: the step after this one, or the step a request step's
`next` names.

**A step the flow never arrives at is `UP2-E1018`** (§12.6): the same walk, started at the entry, answers
"what can this run reach", and a step it cannot reach is dead data. L12 and L13 are two questions about one
graph, so they share one traversal.

The trace of §4.4 has landed (change `add-story-trace`).

---

## 11. A complete walkthrough: ah.gov.cn

Material: the legacy rule of §1 in draft `01` (1 list rule + 2 detail rules, with `url_patterns`
completely identical, told apart by order). The flow is one story: the seed URL goes out as a request, the
list page's response becomes twenty requests, and each response is parsed by the step `next` names.

### 11.1 One bundle, one story: the seed URL to the records

A bundle is one site: the channels' seeds, their list parsers, the item parser and the steps that drive
them — one file (§2). The story suspends twice: once for the seed request, once for the item requests, and
the same run continues after each (§4–§5).

```jsonc
{
  "globals": { "base_url": "https://www.ah.gov.cn" },
  "entry": "start",
  "steps": [
    // 1) the seed URL becomes the first request; `list` receives the answer
    { "name": "start",
      "body": { "url": "$in" },                // only the URL; method/headers/timeout are defaults
      "type": "Request", "next": "list" },

    // 2) the answer becomes the item requests: read its body, take the links, name the receiving step
    { "name": "list",
      "body": { "items": [
          ["py","getattr","text"],                        // the answer is a host object; read its body
          ["css","@href","a[href*='/public/1681/']"],     // every match, as a list
          ["py","uniq",""],
          ["py","slice",":20"],
          ["each", {                                      // one request per link
              "url": [ ["py","urljoin","$globals.base_url"] ]
          }] ] },
      "type": "RequestBatch", "next": "record" },

    // 3) each answer becomes one record (the step runs once per task)
    { "name": "record",
      "body": {
          "url":      [ ["py","getattr","url"] ],
          "title":    [ ["py","getattr","text"], ["css1","text","h1"], ["py","normalize_space",""] ],
          "pub_time": [ ["py","getattr","text"],
                        ["css1","@content","meta[name=\"PubDate\"]"], ["py","strip",""] ],
          "content":  [ ["py","getattr","text"], ["css","remove","script,style,noscript"],
                        ["css1","html","div.j-fontContent"], ["py","html_to_markdown",""] ]
      },
      "type": "Article" }
  ],
  "collect": "record"                                 // N answers → a list of N Articles
}
```

**Adding a second channel** costs one more parse step and one `next` per task's data — no second story, no
host-side table:

```jsonc
// …two steps that each parse one channel's list page:
{ "name": "list_news",   "body": [ ["py","getattr","text"], ["css","@href","div.list-news a"] ],
  "type": "UrlList" },
{ "name": "list_notice", "body": [ ["py","getattr","text"], ["css","@href","div.list-notice a"] ],
  "type": "UrlList" }

// …and a fan-out whose tasks carry the receiving step each one wants:
{ "name": "seeds",
  "body": { "items": [ ["ctx","get","globals.seeds"],
                        ["each", { "url":  [ ["py","getitem","url"] ],
                                   "next": [ ["py","getitem","parser"] ] }] ] },
  "type": "RequestBatch", "next": "list_news" }    // the step's default, overridden per task
```

**The host runs the loop** (it owns the network, the concurrency and the retries):

```python
run = up2.start(bundle, "https://www.ah.gov.cn/public/1681/list.html")
while True:
    effect = run.go()
    kind = effect[0]
    if kind == "done":
        return effect[1]                            # the list of Articles
    if kind == "request":
        run.feed(fetch(effect[1]))                  # the answer is whatever the client returned
    elif kind == "batch":
        run.feed([fetch(task) for task in effect[1]])
```

```text
start(seed URL)   → Request       ⇢ one fetch → answer ─┐
list(answer)      → RequestBatch  ⇢ 20 fetches → answers ┴→ record(answer) ×20 → [Article, …]
```

**Measured on this repository** (both sample bundles, re-run through the executor against their live
sites, through the committed host recipes `samples/books.toscrape.com/host.py` and
`samples/quotes.toscrape.com/host.py`): `samples/books.toscrape.com` suspends four times
(`request → channels`, `batch 2 → shelf_page`, `batch 3 → book`, `call host.store_books`) and finishes
with the receipt `{"table": "books", "stored": 3, "titles": ["It's Only the Himalayas", "Full Moon
over Noah's Ark: An Odyssey to Mount Ararat and Beyond", "See America: A Celebration of Our National
Parks & Treasured Sites"]}`, while `samples/quotes.toscrape.com` suspends twice (`request → links`,
`batch 8 → author`) and finishes with eight `Author` products. The samples use their own domain types
(`ShelfPage`, `Book`, `Author`), so a run needs a host — that host is those two scripts, which
register the types and answer the effects. **Six constraints were found by running them:**

- **`css` is not `css1` per item.** `["css","@href",""]` yields a **list** (every match), so the following
  `py.urljoin` fails with `UP2-E2002`; a per-item read must be `css1`.
- **An answer must be taken apart first.** `css` consumes text or a node, so a step that parses an answer
  object starts with `["py","getattr","text"]` (§4.1); resolving a relative link against the final URL uses
  `["py","getattr","url"]` or `$in.url`.
- **A task is a request with one extra key**, `next`, so a fan-out item needs no nesting: the HTTP fields
  sit at the item's top level. The kernel strips `next` before the host sees the task.
- **The step that receives an answer parses it**, so its field map describes **one** record (not a list of
  records): the batch's products are the list, which is what `collect` collects (§2).
- **An `each` field map always produces dictionaries, and `flatten` only unrolls list elements.** So a
  step that must pass a **plain list** on to the next step cannot unwrap one out of a field map that way:
  the books sample's `shelf_page` therefore stays a **chain** (which yields the list itself), the batch
  aggregates the shelves' lists, and `shelf` unrolls that one level with `["py","flatten",""]`.
- **A chain's first stage already receives the element**, so an `each` field map that must resolve a link
  writes `["py","urljoin","$globals.base_url"]` and nothing else — the identity stage both samples used to
  open with was doing no work (§13 O5).

`"url": "$in"` in step 1 is the whole-chain reference of §2: the seed URL is the step's product unchanged,
where a stage had to say so before this change. The hosts of both samples take the seed from the command
line (the site root by default) rather than from `globals.base_url`, which is the urljoin base of the chains
and not the URL a run starts at.

### 11.2 The fields it extracts, and the registered types

`Article` is a host-registered type: the record step ends with `Article(**fields)`, which is where the
shape is validated — a misshapen record is reported while that response is being parsed, not at the end of
the run. The **collection** of records is what the run's exit product holds: N responses give N `Article`
values (the host may then build an `ArticleList(*articles)` if its own API wants one).

Handing each record to the business is the host's step; a story can also do it with a `call` appended to
the record step:

```jsonc
{ "name": "store", "call": "host.store_articles", "args": { "table": "articles", "rows": "$in" }, "type": "dict" }
```

Two of the old flow's needs disappear here: `channel` / `source` / `region` are ordinary `["const", …]`
fields of the record step (§8.1), and "which of the two detail rules applies" is the **host's** question
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
| **O** `parser="none"` conflicts with the dispatch table | there is no dispatch table and no `parser` field: a run ends when execution passes its last step, and `collect` says which step's products it returns |
| **P** `list_title` has nowhere to go | it is an ordinary field of the step that produced it, or the host carries it in the next run's input |
| **Q** `ctx.globals` idles empty | `globals` holds only static constants; the run's input travels as the first step's input (§2) |
| **R/S** the `result` syntax and the `outputs`/`produces`/`result` boundary | all three are gone: the field map is the product, `type` names its type and `collect` names the step whose products leave (§9) |
| **T/U/V/W** two propagation channels / ctx write permission / `list_title` lost / error policy | one propagation rule (§8); the write surface is `locals` (`02` §6.8); `list_title` is an ordinary field; the kernel only emits the two outcomes (`02` §5) |

| Legacy element | New landing place |
|---|---|
| `task_name` / `channel` / `region` | a `["const", …]` field inside a step, or the caller's input |
| `request` / `request.url` | a task's own keys (§4.1), or the host's own request layer |
| `input_format` | deleted: the consuming operator decides the format, under the run-scoped cache (§6) |
| `nodes` (splitting + truncation) | one chain: `["css","nodes",…]` → `["py","slice",":20"]` → `["each", {…}]` |
| `fields` (the legacy rule's key; not the retired `$fields` root) | a step's field map — the step's `body` (semantics unchanged) |
| `fields.headers` | the host's request layer |
| `fields.referer_info` | deleted (fields without `_` propagate to later steps) |
| `url_patterns` | the host picks the story |
| `detail` (several rules) | several stories, or one story with a registered type per shape |
| `tpl_key` / `root_domain` | **not in the story format**: storage identifiers of the L3 binding layer (`04` §2) |

---

## 12. Deviation records

### 12.1 `D-03-3` — the story model replaces the node model

v0.1 described a graph: three node types (`seed` / `body` / `emit`), an `entry`, `nodes` with `next` /
`routes` / `default_route`, `emit` export shapes (`record` / `flat` / `request`), a `result` assembly
template and a lint family that policed the graph (reachability, cycles, in-degree ≤ 1, terminal count).

It is replaced by **one linear story with typed steps and two effects**. The rulings, with the alternative
each one rejected:

| # | Ruling | Rejected, and why |
|---|---|---|
| R1 | dispatch is by the **product's type name**, host side | a `routes` table inside the story: it duplicates the decision the host already makes (which story suits this response) and creates a second dispatch vocabulary |
| R2 | a story is **linear**, no in-story branching | the v0.1 graph: cycles/joins/terminals needed lints and executor branches no case study asked for |
| R3 | no node types; a step consumes whatever came before it | `seed`/`body`/`emit`: roles that made the executor branch and made "what is my input" a question |
| R4 | no `input` field | an explicit input reference on every step: the upstream value already is the input |
| R5 | `type` is declared per step, validated at the step boundary with the host's constructor | validating only at the run's boundary (too late to name the failing step); comparing with a Python class name (impossible: a product cannot be a host object — measured `UP2-E2009`) |
| R6 | products are JSON; a host object may flow, Pydantic instances live host-side | carrying live objects into a product: it would end replayability and the single exit |
| R7 | a type is a constructor (`Cls(**dict)` / `Cls(*list)`) | typing every collection as `list`: the element's type is lost and the host cannot dispatch on it |
| R8 | `body` and `call` are mutually exclusive keywords | one polymorphic "work" keyword: three shapes in one field, which read as noise |
| R9 | effects are **step-level only** | effects inside `each`: nested suspension for a result that is still serial |
| R10 | the request effect's answer is whatever the host's client returned | a fixed `Response` dictionary: it loses the library's own surface (case-insensitive `headers`, `.json()`, `.request.url`, encoding, timing) and forces a conversion at the boundary; plain body text loses the status and the post-redirect base URL |
| R11 | `call` may have side effects but must return a receipt that is JSON | a callback returning nothing: it would break the single exit and make a run unreplayable |
| R12 | built-in types are `Request` and `RequestBatch`; an answer has no declared type | a larger built-in vocabulary (`Url`, `Page`, `Json`, `Response`): business meaning, or a second copy of what the host's own client already holds |
| R13 | one batched effect carries a fan-out; concurrency is the host's | forking a run per item as the only way to fan out: it makes concurrency a host convention instead of a first-class effect |
| R14 | a request **suspends** the run and the answer resumes the **same** story; what parses the answer is the step `next` names | the hand-off model (a request ends the run, another chain continues): it splits one site's flow across several files and turns "which parser for this response" into a property of the file layout instead of the data |
| ~~R15~~ | **superseded by `D-03-4`**: one site, one bundle still holds; the bundle is `globals` + `steps` + `collect`, and `next` is a **step-level jump** (see that record for what is still rejected: a cyclic goto graph, and routing data outside the story) | — |

### 12.4 `D-03-4` — the bundle's keys, its jump and its exit (change `story-jump-and-naming`)

v0.2 wrote a bundle as `globals` + `chains` + `steps`, with `key` / `out` on a step, a `chain` naming the
table entry that parses an answer, and the exit derived as "the last step's `out`". Running the two sample
sites through the first executor exposed why each of those could not stand:

| # | Ruling | Rejected, and why |
|---|---|---|
| J1 | a step's keys are `name` and `type` | `key` / `out`: generic JSON words for "the name other steps refer to" and "the product's type name" |
| J2 | the `chains` table is **deleted**: a parse rule is a step, and the step that receives an answer parses it | keeping the table and letting `next` point into it: two ways to say "this parses that", two namespaces, and the lookup (hence the routing) living in the host |
| J3 | `next` on a request step names the step that receives the responses, and a task item may override it; **the kernel resolves it and the host never sees it** | the host mapping `next` onto a chain: that is the hand-off `R14` already rejected, and it puts a story concern into host code |
| J4 | `collect` is required and names one step, whose products are the run's output collected in order as a list | "the last step": with a jump a step can be visited more than once, so the last step is not unique; and a batch makes the exit step's products plural |
| J5 | `$in` names the step's own input | `["ctx","set","locals._page"]`: a measured pass-through that reads as a side effect, and it only exists if the step remembered to write it |
| J6 | `py.id` is the identity action (superseded by §12.6: the whole-chain reference replaced it) | `["py","str",""]`: the identity on a string and a conversion on anything else, so a seed value's type depended on the workaround |
| J7 | a `call`'s arguments are the `args` keys, and the step's input travels explicitly (`"rows": "$in"`) | an effect carrying the input implicitly: the host function's signature would then depend on the step's position, not on what the bundle says |
| J8 | what a step product may be is unchanged: **JSON** (`03` §3.3) — the executor packs every product at the step boundary | letting a product be an object: snapshots, the exit and the request dictionary would all have to accept something the host cannot serialize |

### 12.5 `D-03-5` — a story's flow is acyclic, and the graph reading that is rejected (change `add-story-cycle-lint`)

`D-03-4` noted that a cycle among steps is possible but is an authoring error, and left it undetected
(§13 O9). It is now `UP2-E1017`, at compile time, with the travel path in the message:

| # | Ruling | Rejected, and why |
|---|---|---|
| C1 | the lint is drawn over the **program counter's own edges**, one per step, over the steps and from the first one: the step at the next array position, or — for a request step, whose `next` is required (`L2`) — the step `next` names | the **union** reading, which draws a step's fall-through edge and its receiver edges *at the same time*: it refuses the committed samples. `samples/books.toscrape.com` fans out at `channels`, whose receiver `shelf_page` falls through to `shelf`, whose own `next` is `book` — a union cycle through steps each of which runs exactly once. The samples are the acceptance case for the format, and the union graph says "the format's central shape is illegal" |
| C2 | a step entered twice is the failure, and a backward `next` that cannot re-enter its own jump is legal | forbidding a backward `next` outright: it is the samples' own spelling (`fan.next: "left"`, both written later), and §10 L5's "checked against every other step, not an earlier one" says the target is *any* step |
| C3 | `collect` is not an edge: a run ends when the program counter passes the last step, whatever `collect` names | making the exit a graph node: `collect` names the step whose products leave, and a step whose products are only collected when the flow reaches it — the flow ends by running off the array, not by arriving at a node |

The rule is **equivalent to "no backward jump that loops"**, and the equivalence is provable rather than
empirical: in a cycle, the step whose array position is greatest is entered by the fall-through edge (the
only edge that increases the position), so it must be entered by a jump — every cycle contains a forward
jump. A backward jump is therefore always a link of some cycle, and the check above finds a loop exactly
when the run can come back to a step it is already executing. That is the reason the *committed* samples
pass while the pathological `a → … → a` fails, and it is why the rule is not "no backward `next`".

**What `MAX_STORY_STEPS` (64) bounds**: the graph the lint walks, not the number of steps a run may take.
A **forward** jump (`a`'s `next` naming a later step) is legal without qualification — the committed
samples use it (`channels.next: "shelf_page"`, `shelf.next: "book"`) — and it may make a step run more
than once, since the program counter only ever increases on a transition the lint accepted.

### 12.6 `D-03-6` — the entry is declared, and a dead step is a compile error (change `entry-and-input`)

§12.5's walk starts at the first array position, which is what the run used to do as well. The start is now
a **declared key**, and the same walk answers a second question about the same graph:

| # | Ruling | Rejected, and why |
|---|---|---|
| E1 | `entry` is required and names the step the run starts at, with the caller's value as its input; a bundle without it is `UP2-E1005`, a name that resolves to nothing is `UP2-E1016` | defaulting to the first step: it keeps "the first step" as a second way to say what `entry` says, and it hides the one error that matters — an author who believes the first step runs while the flow jumps past it |
| E2 | every step unreachable from the entry is `UP2-E1018` at compile time, and the rule is one more answer from the L12 walk rather than a second model of the flow | reporting it as a warning: a dead step has no legal reading, and `N3` already says a bad chain fails at compile time |
| E3 | the start is a **name**, not an index, and `entry` / `collect` are symmetric top-level keys | an index (or "the first step"): a name survives reordering the array, and both endpoints then read the same way |
| E4 | a chain may be a **whole-chain reference** (`"$in"`, or a chain opening with one), and `py.id` is deleted with its two uses in the samples | a single-element stage form (`["$in"]`): `$` would then mean "a reference" in a parameter and "an operator name" in a stage, and the DSL would carry two spellings for one concept |
| E5 | a chain reference resolves through the same checks a parameter's reference does (`UP2-E1006` unknown root, `UP2-E1014` a `_` key across steps) | a second reference validator: the same mistake would then have two messages, and one of them would drift |
| E6 | a run records no stage event for a whole-chain reference | a synthetic stage row: the trace's `op` column is operators, and inventing a non-operator there makes every consumer branch on it |

The code `UP2-E1018` is the next free `E10xx` number and is **not** retired-and-reused: `E1008` was never
allocated, and `E1101`–`E1106` are the retired graph family (`02` §7.1).

### 12.2 `D-03-2` — materialization is on demand (unchanged from v0.1)

The primary input used to be materialized once by the `seed` (`input_format`, later renamed `format` on
`body`). That turned the entry point into a format registry and made every chain name a format it might
never consume. The ruling: the consumer materializes on demand, and a run-scoped cache keeps it to one
parse per document (§6). The cache has landed (change `add-materialization-cache`).

### 12.3 `D-03-1` — `presets` is retired (unchanged from v0.1)

Draft `04` used `parsers` as the container name, this design renamed it `presets`, and the L2 iteration
redesign retired both along with the container in favour of `each`'s inline field map. If reuse is ever
wanted it belongs to a **callable stage** (a named chain used like any other stage), never to a second
argument shape of `each`.

---

## 13. Open questions

| # | Question | Status |
|---|---|---|
| O1 | the type registry API (name and shape: `register_type` / `register_model`, and whether it takes a constructor, a schema, or both) | **settled** (change `add-type-registry`): `register_type(name, constructor)` — `register_model` was the alternative and lost because the parameter is a class **or** any callable, and a model framework is not something the kernel should name. A name is a string the step writes; the constructor is `Cls(**payload)` for a dictionary, `Cls(*items)` for a list, and the registry is process-wide host state (like `register_udf`), never part of the bundle |
| O2 | how `call`'s arguments are written (`args` on the step; bound at registration; or both with the step overriding) | **half settled** (change `story-jump-and-naming`): `args` is the written form, its values are `ref_or_literal` leaves resolved in the step's scope, and the step's input travels as an explicit `"$in"`; what stays open is whether a registration may bind them instead |
| O3 | is `name` required on every step, or only when something references it? | **settled: required** — `next` and `collect` name steps, and `collect` is required, so a name is never optional in practice; a missing or duplicated name is `UP2-E1009` |
| O4 | may a step override the chain-level `policy`? | **settled: the question is gone** — the settlement policy is retired (`01` `D-01-1`, `02` §5), so there is no chain-level policy and nothing to override; a field-level fallback is written at the action level |
| O5 | an explicit "return the input unchanged" action | **settled the other way** (change `entry-and-input`): `py.id` is **deleted**, and identity is written as a whole-chain reference — `"$in"` for the value itself, `"$in.url"` for a field of it, `["$in", ["py","strip",""]]` for a chain that opens with one. The action was the second spelling of a concept the reference already had (§2, §12.6 E4) |
| O6 | how far the trace goes (`06` §5.1's structure) and whether a recorded run is the replay format | **settled** (change `add-story-trace`): the trace is **a debugging aid, not the replay format**. It records one event per evaluated stage (plus one per suspension), and it is lossy by construction — every value is a `type` / `preview` / `size` view whose whole value is read back by `seq` from the trace object's memory — so it can neither replay a run nor serve as a contract; what replays a run is the host's own log of the suspensions it answered (the request it sent, the answer it got, the receipt returned) together with the run's input, which belongs to the host (`01` §1) and is not defined here. How far it goes is settled the same way: the **evaluated** stage is the unit, because a step's field map hides which chain failed, and a suspension is a second event kind because "it handed the host these 20 tasks here" is not a stage's product |
| O7 | the name of the batch product type | **settled**: `RequestBatch` (v0.1's name, and its items *are* requests); the coinage `TaskList` was dropped |
| O8 | how a task's receiving step is chosen when it **varies per item** | **settled** (change `story-jump-and-naming`): the task's own `next` overrides the step's, so a chain can compute one from the item's own data and one step can route several channels; "route by URL shape" still needs a mechanism or stays a host table |
| O9 | a cycle among steps (a `next` that points backwards) | **settled** (change `add-story-cycle-lint`): the story's **flow must be acyclic** — drawn over the steps from the first one, with one edge per step (the next array position, or the step a request step's `next` names), a step entered twice is rejected at compile time with `UP2-E1017` and the travel path in the message. `next` stays free to name **any** step, including one written earlier: the samples' own fan-out shape does that, and a backward jump is legal as long as the region it enters cannot reach the jumping step again. The rule and the stronger reading it rejects (the union graph, which refuses the samples) are §12.5 |
| O10 | does a `Failed` stage inside a story raise, and is that the host-facing contract? | **settled for now**: the effect vocabulary has no failure member, so a run that cannot produce a step's product raises `Up2Error` carrying the stage's code and the step's pointer; `up2 trial` prints it as a failed state |
| O11 | what a chain product that "matched nothing" means at the step boundary | **re-settled** (change `empty-value-semantics`): it is a value — the shape's empty value — so the step produces a product like any other and there is no "skipped step". The earlier `Missing`-based ruling (a step with no product was skipped) is superseded; a step that *fails* still fails the run (§9, `01` §4.2) |
| O12 | does a dotted reference refuse a callable attribute, as `py.getattr` does? | **settled** (change `close-story-open-questions`): yes — a callable attribute is `UP2-E2002` with `py.getattr`'s own message shape and its fix hint. `$resp.json` resolved to a bound method, which could not leave the run anyway (`pack`, `UP2-E2003`); refusing it at the reference makes the failure early and clear |
| O13 | is the run's start implicit ("the first step") or declared, and is a step nothing reaches an error? | **settled** (change `entry-and-input`): declared — `entry` is a required top-level key symmetric with `collect`, and a step unreachable from it is the new `UP2-E1018` at compile time. §12.6 gives the rulings and the alternatives each one rejected |
