# uniparser2 Design · 03 Story Spec

> **Status**: design draft **v0.4** (the **node** model: `globals` + `nodes`, node calls, a
> synchronous `run`). Rewritten from v0.3, whose `steps` array, `entry` / `collect`, step-level
> effects (`Request` / `RequestBatch` / `call`) and `next` routing are retired. **Upstream**: `00`,
> `01`, `02`, `07`.
> **What this document answers**: what a story is (`globals` + a map of callable nodes), what a node
> body is (a chain or a field map), how a chain calls another node (`["node", name]`), how a field
> map feeds `$locals`, where types are validated (`["type", name]`), how host code enters (`udf`,
> `fetch`), and how a run proceeds (`run`).
> **Supersedes**: v0.3 of this note — the `steps` array, `entry` / `collect`, `body` / `call` /
> `next` / `args`, the effect run loop (`start` / `run.go()` / `run.feed()`), the whole-chain
> reference and the `Request` / `RequestBatch` types. v0.1's materialization ruling (§6) and its
> `each` ruling (§7) are carried over.
> **Implemented**: the operator layer (`02`), the field-chain evaluator (`compile_field` +
> `eval_field`), the story compiler and runner (`core/story.py`: `compile_story` / `run`), the
> `node` and `type` stages, the run-scoped udf table, the type registry (`core/types.py`, §3), the
> run-scoped materialization cache (`core/materialize.py`, §6), and the trace (`core/trace.py`, §5.4)
> that `up2 trial --trace` reports.

---

## 1. One story

The end-to-end shape the whole project starts from:

```text
one text in  →  named nodes  →  a JSON product out
```

A story is a set of **nodes**. Each node is a named chain (or field map); a chain may call another
node with its current value. The run starts at the node the host names — or at the first node when a
tool needs a default — and returns that node's product. There is no declared entry, no declared exit
and no step order: composition is a call, not a route.

Two consequences are the point of the design:

- **The host decides what happens to a product.** A story says what a node produces; the host
  decides which node to run and what to do with the answer. No domain name, `tpl_key` or business key
  appears in a story (`07` §3).
- **A story may need the network in the middle of it, without the kernel doing IO.** `fetch` is a
  host `udf`: the story calls it, it blocks until the answer is back, and the answer is the next
  stage's value. The kernel stays pure and synchronous; the host chooses its client, its cache, its
  threads and its retries.

---

## 2. The story JSON

```jsonc
{
  "globals": { "base_url": "https://www.ah.gov.cn" },   // read-only constants; a run may override
  "nodes": {
    "list":   [["py","const","https://www.ah.gov.cn/"], ["udf","fetch"],
               ["py","getattr","text"], ["css","@href","ul.notices a"]],
    "item":   { "url":   [["py","urljoin","$globals.base_url"]],
                "title": [["py","getattr","text"], ["css1","text","h1"], ["py","normalize_space"]] },
    "crawl":  [["node","list"], ["each", [["node","item"]]]]
  }
}
```

**One site, one JSON.** The nodes are the site's parsing and fetching steps in one file: a list
node, a detail node, and a node that composes them. The file is plain data, so `dumps(loads(x))` is
a fixed point and a bad bundle fails at compile time.

| Field | Required | Description |
|---|---|---|
| `globals` | no | the story's **static** constants (such as `base_url`); read-only for every node. A run may merge overrides without changing the stored story |
| `nodes` | yes | a non-empty object of **node name → node body**; every node is an entry point |

### 2.1 A node

A node body is exactly one of:

| Shape | Meaning |
|---|---|
| an array | **one chain**: one value in, one value out; `[]` is identity |
| an object | **one field map**: every field chain sees the same input; the product is one object |

A node name is a non-empty string, unique by the object key, containing no `.`, `/` or `~` (a JSON
Pointer and a reference path must be able to name it), and it is not one of the reserved reference
roots (`globals`, `locals`, `public`, `in`, `obj`). Node order is **not** execution order; it exists
only so a tool can name a default. The CLI and the snapshot runner use the **first node** when the
caller names none; `run` always accepts a name.

A node body that is a string, a number or `null` is `UP2-E1005`. An empty field map (`{}`) is also
`UP2-E1005`; an empty chain (`[]`) is the identity and is legal everywhere a chain is.

### 2.2 `$in`

`$in` names the **current node invocation's input**:

- at the top of a run, it is the `input` the host passed to `run`;
- at a node called by `["node", name]`, it is the value the caller had at that stage;
- inside an `each`, `$in` is still the node's input — the element is the **stage value**, not `$in`.

A node call saves the caller's `$in` and restores it on return, so an inner call never changes what
an outer stage sees. `$in` has no path limit: `$in.url`, `$in.status_code` and `$in.text` work, and
a dotted path reads a host object's attribute through the same walk as a mapping key.

### 2.3 References

A leading `$` means a reference (the parameter-kind rules of `02` §3 decide whether a string is
read as one):

| Root | Meaning | Writable |
|---|---|---|
| `$globals` | the story's constants, plus this run's overrides | no |
| `$locals` | the current scope's variables (every field of a field map lands here) | yes |
| `$public` | the run's shared notes, across nodes and `each` elements | yes |
| `$in` | the current node's input | no |
| `$obj` | the whole value the current stage received | no |

There is no `<node name>` root: a node's product is the value its call returns, and a field map
already writes every field into `$locals`. `$obj` takes no path (it names the whole value); read a
field with `["py","getitem", key]` or `ctx.get`.

**Identity is `[]`.** A chain written as `"$in"` or as a string is not a chain any more; `[]` is the
only way to say "the value, unchanged". A whole-chain reference does not exist.

---

## 3. Products and types

### 3.1 Where a type name comes from

| Source | Names | How the name is obtained |
|---|---|---|
| the JSON value domain | `null` / `bool` / `str` / `int` / `float` / `list` / `dict` | from the value itself (`01` §2's type-name table) |
| host-registered types | `Article`, `NoticeList`, … | a `["type","Article"]` stage; the host registers name → constructor (`register_type`, §3.2) |

`Request` and `RequestBatch` are **not** built-in types any more: a request is an ordinary object a
chain builds, and `fetch` is a `udf` (§4). The built-in set is the JSON basics only.

### 3.2 A type is a constructor

| Product | How the declared type is built |
|---|---|
| a dictionary | `Cls(**payload)` |
| a list | `Cls(*items)` |
| anything else | `Cls(product)` |

The host registers one with **`register_type(name, constructor)`** (`unregister_type`,
`type_names`, `get_type` beside it). A registration is process-wide host state, not part of the
bundle, so a story stays library-independent data. A later registration replaces an earlier one, and
a host registration wins over a built-in name.

```python
from dataclasses import dataclass
import uniparser2 as up2


@dataclass
class Article:
    url: str
    title: str
    pub_time: str = ""


up2.register_type("Article", Article)

story = {
    "nodes": {
        "record": [["node", "fields"], ["type", "Article"]],
        "fields": {
            "url": [["py", "getattr", "url"]],
            "title": [["py", "getattr", "text"], ["css1", "text", "h1"]],
        },
    }
}
product = up2.run(story, "record", response)   # a missing title fails at the type stage
```

### 3.3 Where validation happens

`["type", name]` is a **chain-tail stage**. It builds the declared type from the current value,
reports a mismatch at that stage, and continues with the JSON. The check cannot move to compile
time: a story is compiled without a host, so the registry is only known for sure when the stage
runs.

| Situation | Code |
|---|---|
| no host registered the name | `UP2-E1011`, listing the names that are (the built-ins included) |
| the constructor raised | `UP2-E2019`, with the constructor's own exception text in `reason` |
| the approved value is not JSON | `UP2-E2003` |
| the `type` stage is not the last stage of its chain | `UP2-E1005` at compile time |

**A value that flows may be a host object; a run's exit must be JSON.** A response, a `selectolax`
node handle and anything a `udf` returns may flow mid-chain and be read by `py.getattr` or a
reference. The run boundary (`pack`, `UP2-E2003`) and a `type` stage are where that stops. A `type`
constructor is a **validator, not a container**: building `Article(**fields)` proves the record's
shape, and what the stage hands on is JSON, never the `Article` instance. Pydantic instances live on
the host side: `model_validate` on the way in, `model_dump` on the way out.

A field-map node has no trailing stage, so a node that needs a named shape is written as a chain
that calls the field-map node and then validates:

```jsonc
"record":  [["node", "fields"], ["type", "Article"]],
"fields":  { "url": […], "title": […] }
```

This keeps one rule — a node is a chain **or** a field map — and makes the call the only composer.

---

## 4. Host code: `udf`, and `fetch` in particular

`udf` is the only stage that calls host code. The chain carries a **name**, never a body:

```jsonc
["udf", "fetch"]           // f(value): the request is the value in front
["udf", "fetch", "*"]      // f(*value): value is a list of arguments
["udf", "fetch", "**"]     // f(**value): value is a mapping of keyword arguments
["udf", "translate", "en"] // f("en"): one explicit argument
```

| Slot 3 | The call |
|---|---|
| omitted | `f(value)` — the upstream value is one DTO argument |
| the literal `"*"` | `f(*value)`; the upstream value MUST be a list |
| the literal `"**"` | `f(**value)`; the upstream value MUST be a mapping with string keys |
| anything else | `f(argument)` — the literal or the reference's value |

The name resolves from the **run's udf table**: `register_udf` installs process-wide defaults and
`run(udfs={...})` overlays them for that run. A name the story uses but the table lacks is
`UP2-E1010`, reported by `run` before evaluation with the names that are available.

**A udf may return any value.** A response object flows to the next stage and is read with
`py.getattr`; only the run's exit and a `type` stage require JSON. A udf that returns an awaitable
is `UP2-E2009`: the kernel is synchronous, and an async host calls its async function in its own
event loop before returning.

### 4.1 `fetch` is the host's downloader

`fetch` is not a built-in operator. It is the conventional udf name for the host's HTTP client; the
samples and the README register it. The package offers a default for the host side
(`uniparser2.net`): a synchronous, standard-library downloader that accepts **one request object**
(the `url` / `method` / `headers` / `timeout` / `body` / `params` / `json` keys of `03` v0.3 §4.1)
and answers a response carrying `text`, `url`, `status_code` and `headers`. It is a **default**, not
a requirement: a host with sessions, retries, cookies or rate limiting brings its own client.

```python
from uniparser2.net import RequestCache, fetch

cache = RequestCache()


def cached_fetch(request):                 # the udf the story calls
    cached = cache.get(request)
    if cached is not None:
        return cached
    response = fetch(request)
    cache.put(request, response)
    return response


product = run(story, "crawl", seed, udfs={"fetch": cached_fetch})
```

A request is an ordinary object: a chain builds it with a field map and `py.const`, or with
`["ctx","dict",{"url":"obj"}]` from the current URL string. `fetch` blocks; a list node that wants to
fetch ten items in parallel does it in the host's own code, not in the story. `["py","sleep",2]` is
the way a story waits between requests; it returns the value it received, so the next stage still
sees the response.

---

## 5. The run

### 5.1 The facade

```python
run(
    story,                 # the bundle (mapping)
    node=None,             # a node name; the first node when omitted
    input=None,            # the entry node's `$in`
    *,
    globals=None,          # merged over the story's `globals` for this run
    udfs=None,             # merged over the process-wide udf table for this run
    trace=None,            # a Trace, or None
) -> Any                   # the entry node's product, packed
```

The run is synchronous: it compiles the story, resolves the node and the globals, checks the udf
table, executes the node, and packs the product. Nothing suspends; nothing is handed to a host loop.
A host that wants concurrency calls `run` from its own threads or event loop and owns the result.

The run's `Scope` carries the effective globals, the run's `locals`, its `public` notes, its
materialization cache and its udf table. The cache lives exactly as long as the run.

### 5.2 A node call

`["node", name]` is a stage:

1. take the current stage value;
2. save the caller's `$in`, set `$in` to that value;
3. evaluate the callee's body in the **same scope** (the callee shares `$locals` and `$public`);
4. restore the caller's `$in` and answer the callee's product.

A node call creates no frame. A field map inside the callee writes every field into the scope the
caller is using, which is how a detail node hands `_title` or `url` back to the caller. There is no
`args` object: to call a node with another input, put a stage in front of it that produces that input.

The compiler collects every `node` stage, including the sub-chains of `each`, and rejects a cycle
with `UP2-E1017` (the travel path and the closing stage). Every node is an entry point, so there is
no unreachable-node rule.

### 5.3 Field maps and `$locals`

A field map is compiled as `field name → chain`; evaluation is ordered:

1. every chain receives the **node input** as its stage value (not the previous field's value);
2. every field's result is written into the current scope's `$locals` under its name;
3. a field whose name starts with `_` is not added to the product; every other field is.

So a later field reads an earlier one with `$locals.name`, a node called by the map sees the fields
the map wrote, and the product is exactly the non-`_` view of the map.

`each` applies the same rule per element: every field lands in the element's child scope, and the
non-`_` fields form the element's dictionary. Reads fall outward through the scope lineage; writes
stay in the scope that received them. Every element is isolated from every other element; an
element's locals do not outlive it.

### 5.4 Trace

A trace (`06` §5.1) records one event per evaluated stage. The event names the **node** whose chain
it belongs to (`node`), the field-map key (`field`), the stage's index, the operator and action, the
compiled parameters, input/output views and the timing. A node call produces the events of the
callee under the callee's name. The run is synchronous, so there are no suspension events. A trace
never changes what a run does, and a run without one records nothing.

---

## 6. On-demand materialization and the run-scoped cache

**Status**: the operators materialize on demand (measured: `css1` on HTML text, `json` on JSON text
and `xpath` on XML text all return the parsed result), and the cache described below is implemented
(`core/materialize.py`). Consumers take their artifact through it instead of building one per stage,
so feeding the same text to several `css`/`json` stages is one parse per run.

**A story does not materialize its input.** How an input becomes structure is decided by the
operator that consumes it, at the moment it consumes it:

| Consumer | On a `str` input | On its own value domain |
|---|---|---|
| `css` / `css1` | parses HTML into an `Opaque` document | a `DomNode` / a node list is unwrapped |
| `json` | parses JSON text | a JSON tree is walked |
| `xpath` | parses XML into an `Opaque` document | a node is unwrapped |

Two consequences: **a chain never declares a format** (`input_format` / `parse.format` are deleted),
and "one document, one parse" is the cache's job rather than the entry point's.

**`bytes` never enters a chain**: the value domain is the JSON tree plus the `Opaque` handle
(`01` §3), so decoding is the caller's job — the CLI hands over text (`--input K=@file`), and a
genuinely binary payload is materialized by the host or carried in as text (base64).

**The materialization cache is run-scoped and bounded**:

- **Scope**: it lives with one run and is released with it. It is carried by the run's evaluation
  scope and inherited by every nested scope (`each`'s per-element scope included), so all of a run's
  nodes and fields share one cache; nothing is shared across runs, so no `Opaque` handle outlives the
  run that produced it and two runs cannot observe each other.
- **Key**: the target format plus the source value — object identity first, a content hash on a
  miss. Hashing a 5 MB text costs a couple of milliseconds against the ≈110 ms parse it saves. The
  entry is accepted when its source *is* the queried object or its digest equals the queried text,
  and each entry holds a strong reference to its source, which is what makes the identity check
  sound.
- **Bound**: `MAX_MATERIALIZE_BYTES` (64 MiB by default, `01` §9) with LRU eviction, accounted in
  **materialized bytes** — not in source-text bytes, because the amplification differs per format
  (measured: a selectolax DOM is ≈24× its HTML text, a JSON tree ≈2.2–2.7×). Each consumer measures
  its own artifact.
- **At most `MAX_MATERIALIZE_ITEMS` (8) artifacts**, so a run over many small documents cannot fill
  the cap with hundreds of tiny trees.
- **The cap is soft for a single artifact**: an artifact larger than the cap is still retained while
  it is in use, so "one document, one parse" always holds.
- **Eviction** costs a re-parse and nothing else: a hit and a miss MUST be observably identical.
- **Mutation**: a cached tree MUST NOT be mutated in place. `remove` already copies before pruning.

Measured on the 0.5.0 commit (selectolax, synthetic pages): one parse costs 48.0 ms at 2 MB and
109.6 ms at 5 MB, an HTML tree costs **≈24×** its text in resident memory (2 MB → +49.3 MB, 5 MB →
+121.7 MB) while a JSON tree costs ≈2.2–2.7×, and 20 fields that each re-parse take 748.8 /
1976.7 ms against 16.5 / 48.6 ms when one parse serves all 20 (**40–45×**).

---

## 7. `each` and the field map

`each` is one operator inside a chain (`02` §6.9). Its parameter selects the mode: an **object** is
a field map (one dictionary per element), an **array** is one chain (one value per element).

```jsonc
"rows": [["css","nodes","li"], ["py","slice",":20"], ["each", {"title": [["css1","text","a"]]}]]
```

| Rule | Content |
|---|---|
| a node's field map | evaluated **once** on the node's input; produces **one** dictionary |
| `each` inside a chain | its input must be a list; the result is one value per element |
| truncation / sorting | ordinary stages **before** `each` |
| empty collection | `each` on an empty list yields an empty list |
| exporting the list | the list is a **named field** of the node's product |

A nested `each` (a field map or chain inside a field map) is legal up to `MAX_EACH_DEPTH`, and the
whole parameter is compiled recursively, so a mistake inside it is reported at compile time with a
pointer that reaches the offending stage.

**Field definitions and evaluation semantics** are in `02` §5. The key points restated:

- every field's result is stored in the current scope's `$locals`;
- a key **without a `_` prefix** also travels with the product;
- a key **with a `_` prefix** is only a local: referenceable inside the same scope, never a key of
  the product;
- fields are evaluated in declaration order, and a later field may read earlier values — inside an
  `each` field map the same rule holds **per element**.

**Scope inside `each`**: every element is evaluated in its own child scope; a read falls back
outward **by name** — the element's locals, then the enclosing scope's locals, then the chain-level
values — so the innermost scope holding the first segment of a path resolves the whole path, and a
name the element wrote never resolves in an outer scope. Writes stay in the element. There is no
iteration variable to name: the element is the input value of every field chain.

**`$in` inside `each` is still the node input**, not the element. A field that needs the element
writes the stage that consumes it; a node call inside `each` receives the element as its `$in`,
because the call passes the current stage value.

---

## 8. Scope and propagation

| Source | Lifetime | Read/write |
|---|---|---|
| `globals` | the whole run | read-only; the story's constants plus this run's overrides |
| `$in` | one node invocation | read-only; the value the node was called with |
| `locals` | the whole run, with `each` elements as child scopes | writable (`ctx.set`/`del`); every field map writes here |
| `public` | the whole run | writable; **not** chain data, so it never enters the fingerprint |
| `obj` | one stage | read-only; the whole value the stage received |

The three scopes read as **constants / shared / private**: `globals` is what the story declares,
`public` is what the run remembers, `locals` is what the current scope computed. `public` is the
run's own notes — a value written in one node is readable in the next, and a value written inside an
`each` element outlives the element, because the scope is run-level rather than per-field. `locals`
is the private tier: a node call shares the caller's locals, an `each` element gets a child scope.

**Downward propagation needs no new concept**: a node call returns its product; a field map writes
its fields into `$locals`; a later node reads them. To pass a value to a node called with a
different input, write the value in front of the call (a stage or a field map).

### 8.1 Where `channel` / `source` / `region` land

Always produce them inside a node's field map with `["py","const", …]`. They are values each product
carries itself; different nodes can give different constants; a second copy in the run's input would
create the "which one is the truth" ambiguity.

### 8.2 Things that do not exist

| Deleted | Replacement |
|---|---|
| `entry` / `collect` / `steps` | `nodes`; `run` names a node (the first is the tool default) |
| `next` / `Request` / `RequestBatch` / `call` | a node call, or `["udf", …]` |
| `body` / `args` | a node body is a chain or a field map; a udf takes its argument per §4 |
| the whole-chain reference (`"$in"`) | `[]` |
| `referer_info` / `meta` / `$request` | `$locals` / the call value |
| a step-product reference root (`$node.field`) | `$locals` (every field map writes there) |

### 8.3 Passing between stories

A collection story returns `list[dict]`; the host then runs a detail story per product, handing
that dict in as the run's input:

```python
rows = run(collection_story, "list", page_text)
for item in rows:
    detail = run(detail_story, "record", item, udfs={"fetch": cached_fetch})
```

Cross-story composition is the host's; the kernel does not know a store or another story.

---

## 9. The exit and schema

- **The exit is the product of the node `run` names** (the first node when none is named).
- **A `schema` is the registered type itself**, applied by a `["type", name]` stage; the run's exit
  still passes through `pack` (`UP2-E2003`).
- **A node always produces a product or fails**: a query that matched nothing is a value (its
  shape's empty value, `01` §4.2), so there is no "skipped node" and no invented `null`.
- A node call's product may be a host object; only the run's exit and a `type` stage require JSON.

---

## 10. Compile-time lint checklist

| # | Rule | Code |
|---|---|---|
| L1 | the bundle is an object with `globals` (optional, object) and `nodes` (required, non-empty object); no `entry` / `collect` / `steps` | `UP2-E1005` |
| L2 | a node body is a chain (array, `[]` allowed) or a field map (object, `{}` refused); no other shape | `UP2-E1005` |
| L3 | node names are non-empty, contain no `.` / `/` / `~`, and are not reserved roots | `UP2-E1009` |
| L4 | node count ≤ `MAX_STORY_NODES` | `UP2-E1012` |
| L5 | every `node` stage names a node of this story | `UP2-E1016` |
| L6 | the node-call graph is acyclic | `UP2-E1017` |
| L7 | every stage (including sub-chains of `each`) passes operator validation | `UP2-E1001`…`E1005` |
| L8 | a `type` stage is the last stage of its chain and names a non-empty string | `UP2-E1005` |
| L9 | no resource limit is exceeded (`01` §9) | `UP2-E1012` |
| L10 | an operator's optional dependency is installed | `UP2-E1107` |
| L11 | a udf name is a non-empty string (registration is checked by `run`) | `UP2-E1005` |

`type` names and udf names are host state, so their existence is checked when the run (or the stage)
reaches the registry: `UP2-E1011` for a type, `UP2-E1010` for a udf.

---

## 11. A complete walkthrough: GitHub pinned items

The README's example, end to end. It fetches a profile, takes the first pinned item, fetches its
detail page, and reads the response's status code and an `[class*="Actions"]` text.

```jsonc
{
  "globals": { "base_url": "https://github.com" },
  "nodes": {
    "pinned": [
      ["node", "list"],
      ["each", [["node", "detail"], ["py", "sleep", 2]]]
    ],
    "list": [
      ["py", "const", "https://github.com/ClericPy"],
      ["ctx", "dict", {"url": "obj"}],
      ["udf", "fetch"],
      ["py", "getattr", "text"],
      ["css", "nodes", "div.js-pinned-items-reorder-container ol > li"],
      ["each", {"url": [["css1", "@href", "a"], ["py", "urljoin", "$globals.base_url"]]}]
    ],
    "detail": [
      ["node", "detail_request"],
      ["udf", "fetch"],
      ["node", "detail_parse"]
    ],
    "detail_request": {
      "url": [["py", "getitem", "url"], ["py", "strip"]]
    },
    "detail_parse": {
      "url": [["py", "getattr", "url"]],
      "status": [["py", "getattr", "status_code"]],
      "actions": [
        ["py", "getattr", "text"],
        ["css1", "text", "[class*=\"Actions\"]"],
        ["py", "normalize_space"]
      ]
    }
  }
}
```

Wait: `detail_request` is a field map whose `url` reads the element's `url` key with
`py.getitem`; the field map writes `url` into `$locals` and returns `{"url": …}`. `detail` calls it,
then `fetch` gets that object, and `detail_parse` reads the response with `py.getattr`.

The host:

```python
from uniparser2.net import RequestCache, fetch

cache = RequestCache()


def cached_fetch(request):
    hit = cache.get(request)
    if hit is not None:
        return hit
    response = fetch(request)
    cache.put(request, response)
    return response


product = run(story, "pinned", udfs={"fetch": cached_fetch})
```

`py.sleep` returns the detail product, so the `each` chain's final value is still one detail record
per item. Put `["py","first"]` between `["node","list"]` and the `each` to request only the first
pinned item.

### 11.1 The fields it extracts

| Field | Chain | Meaning |
|---|---|---|
| `url` | `$in.url` | the request's final URL |
| `status` | `["py","getattr","status_code"]` | the response's status code |
| `actions` | `["py","getattr","text"]`, `css1` `[class*="Actions"]`, `normalize_space` | the link's text, whitespace-collapsed |

### 11.2 Key points

- The list node fetches once, extracts the pinned links, and returns one `{"url": …}` per item.
- `pinned` runs `detail` per item; `detail` builds the request, fetches, and parses in one call.
- `$in` inside `detail_request` / `detail_parse` is the element `{"url": …}`; the response object is
  the stage value after `fetch`, read with `py.getattr`.
- `$locals` carries the field-map results across the node calls: `detail_request` writes `url`, and
  `detail_parse` can read it if it wants.
- No effect, no `next`, no `Request` type; `fetch` is a udf the host registers.

---

## 12. Deviation records

### 12.1 `D-03-7` — the node model replaces the step model

The step model's `entry` / `collect` / `next` / effects could not express nested fetch/parse calls
without fan-out effects, and its vocabulary was larger than the behavior. The node model has one
composition primitive (`["node", name]`), one field-map rule, and one exit (`run`). The retired
codes are `UP2-E1018` (unreachable step) and the effect-specific `UP2-E2005` paths; they are
**retired, not reused** (`02` §7.1's rule).

### 12.2 `D-03-2` — materialization is on demand (carried over)

Unchanged from v0.1: operators materialize their own inputs through the run's cache (§6).

### 12.3 `D-03-1` — `presets` is retired (carried over)

The field map is inline, so there is nothing left to name.

### 12.4 `D-03-8` — `py` keeps its named-parameter table

`py` is a closed allowlist of value transforms with declared parameters; the DTO / `*` / `**` call
forms belong to `udf`, whose signatures are host-defined. Changing `py`'s binding would rewrite
every action and its compile-time checks, and would make `py.const` (which ignores its input)
impossible to express uniformly.

### 12.5 `D-03-9` — `$obj` and `$public` stay

`$obj` names the whole stage value; `$public` is the run's shared notes. They are the only two
advanced roots left after the node-product root was removed, and `ctx.dict` needs `obj` to include
the current value in a payload.

---

## 13. Open questions

- **Pagination**: a bounded story-level step, or a host loop over `run(node=…)`. Deferred.
- **`first_ok`**: a fallback group over several parser nodes. Deferred, separate change.
- **Cross-story calls**: the host composes; the kernel does not read the store.
- **A field-map node with a type**: the wrapper node (`["node","fields"], ["type", …]`) is the
  current answer; a dedicated syntax is deferred.
