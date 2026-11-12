# Design

## Context

`docs/specs/003` describes the v0.3 story model: an ordered `steps` array, a declared `entry` and
`collect`, step-level effects (`Request`, `RequestBatch`, `call`) and a `next` routing key. It is
implemented in `core/story.py` as a generator that suspends and resumes.

That model is being replaced. The target flow is a call graph, not a routed sequence:

```
list  ── fetch list ── each item ── call detail ── fetch item ── parse item
```

The user's rulings across the design discussion: `node` (not `step`), `stage` (not `layer`), only
synchronous execution, `fetch` is a `udf`, no `Request`/`RequestBatch`/effects, no `entry`/`collect`/
`next`/`body`/`args`/`call_step`/`each: true`, `[]` is the only identity, all fields live in
`$locals`, a `node` call shares the caller's `$locals`, and `type` is a chain-tail validator.

## Goals

- One composition primitive: **call a node**.
- One rule for a field map: every field is evaluated against the node input, every result lands in
  `$locals`, `_` only removes the field from the product.
- One exit rule: the run's product must be JSON; anything mid-chain may be a host object.
- The kernel remains pure, synchronous and single-exit.
- The documented vocabulary matches the code: story, node, chain, stage, operator, action, parameter,
  product, `$globals`, `$locals`, `$public`, `$in`, `$obj`.

## Non-goals

- Pagination loops, `first_ok` fallback groups and cross-story calls (separate changes).
- Snapshot/store schema changes: a store row is still one story; the snapshot runner uses the first
  node.
- Async hosts. The kernel is synchronous; a host may call `run` in a thread, and a udf returning an
  awaitable is rejected.
- Changing the `py` allowlist's named-parameter model. `py` is a closed table of value transforms;
  the `*`/`**` call forms belong to `udf`, whose signatures are host-defined.

## The story

```jsonc
{
  "globals": { "base_url": "https://github.com" },
  "nodes": {
    "pinned": [["node", "list"], ["node", "detail"]],
    "list": [["py", "const", "https://github.com/ClericPy"], ["udf", "fetch"], ...],
    "detail": { "url": [["py", "getattr", "url"]], "status": [["py", "getattr", "status_code"]] }
  }
}
```

| Key | Required | Meaning |
|---|---|---|
| `globals` | no | the story's read-only constants; a run may merge overrides |
| `nodes` | yes | a non-empty object of node name → node body |

A node body is:

| Shape | Meaning |
|---|---|
| an array | one **chain**: one value in, one value out; `[]` is identity |
| an object | one **field map**: every field chain sees the same node input; the product is one object |

Node names are non-empty, unique by object key, contain no `.`, `/` or `~`, and are not reserved
reference roots (`globals`, `locals`, `public`, `in`, `obj`). There is no ordering between nodes: a
node runs when it is called, and every node is a valid entry point. Tools that need one default
(the CLI, the snapshot runner) use the **first node** in the document; `run` always accepts an
explicit name.

A story bundle is still chain data: `dumps(loads(x))` is a fixed point, a duplicate JSON key is
rejected by the strict reader, and a bad bundle fails at compile time with a `UP2-E*` code and a
JSON Pointer.

## Stages and composition

The stage grammar is unchanged (`02` §1): `[operator]`, `[operator, action]` or
`[operator, action, parameter]`. Three stages are composition rather than value transforms:

| Stage | Meaning |
|---|---|
| `["py", name, …]` | call an allowlist function; the action table binds the parameters |
| `["udf", name, …]` | call a host function from the run's udf table |
| `["node", name]` | call a node of this story with the current value as its `$in` |
| `["type", name]` | validate the value against the host type registry; must be the last stage |

`node` is a registered operator with a static action (`call`), two slots, and the node name in slot
2. `compile_field` checks the name against the story's node table (`UP2-E1016`). `type` is a
registered operator with a static action (`check`), two slots, and the type name in slot 2; a `type`
stage that is not the last stage of its chain is `UP2-E1005`.

`["node", name]` always passes the **current stage value** as the callee's input; there is no
argument slot. To call a node with another input, put a stage before it that produces that input
(`["py","const",…]`, a field read, or a field-map builder). This keeps one rule for every call:
"the value in front is what the callee receives".

### The node call graph

The compiler builds an edge set: every `node` stage in every node body, including the sub-chains of
`each`, points at its callee. A cycle is `UP2-E1017` with the travel path and a pointer at the
closing stage. There is no unreachable-node check: every node is an entry point.

## Field maps and `$locals`

A field map is compiled as `field name -> chain`. Evaluation is ordered:

1. every field chain receives the **node input** as its stage value (not the previous field's
   value);
2. every field's result is written into the **current scope's** `$locals` under its field name;
3. a field whose name starts with `_` is not added to the product; every other field is.

Consequences:

- a later field reads an earlier one with `$locals.name`, without a relay field;
- a node called from the map (or from a later stage) sees the fields the map wrote;
- a product field and a local of the same name are the same value, and the product is just the
  non-`_` view of the map.

`each` uses the same rule per element: every field lands in the element's child scope, and the
non-`_` fields form the element's dictionary. A read falls outward through the scope lineage; a
write stays in the scope that received it. A node call shares the current scope: it does not create
a frame. `$locals` therefore lives for the whole run, with `each` elements as nested scopes.

`$in` is always the **current node invocation's input**. Inside an `each`, the element is the stage
value, not `$in`; inside a `node` call, the callee sees the value it was called with. A node call
saves and restores the caller's `$in`.

`$public` keeps its meaning: the run's own writable notes, shared across every node and element.
`$globals` is read-only during a run; `run(globals={...})` merges over the story's constants before
the run starts, and the effective table is what `$globals` reads.

## `udf` and the host

`udf` is the only place host code enters a story. Its name resolves from the run's table:
`register_udf` installs process-wide defaults, and `run(udfs={...})` overlays them for that run.
A name that is not in the effective table is `UP2-E1010`, reported by `run` **before** evaluation
with the names that are available. Because the table is run state, compilation checks the signature
only when the name is already known; an unknown name is checked at run start.

The argument slot has four forms:

| Slot 3 | Call |
|---|---|
| omitted | `f(value)` — the upstream value is one DTO argument |
| `"*"` | `f(*value)` — the upstream value must be a list |
| `"**"` | `f(**value)` — the upstream value must be a mapping with string keys |
| any other value | `f(argument)` — the literal or reference is the single argument |

A udf may return any value, including a host object such as a response. Mid-chain that object is
carried by reference and read with `py.getattr` / references. The **run's exit** and a `type` stage
are the JSON boundaries: `pack` refuses anything that is not a JSON value (`UP2-E2003`). A udf that
returns an awaitable is `UP2-E2009` ("the kernel is synchronous; call the async function in the
host").

`fetch` is not a built-in. It is the conventional name for the host's downloader; the samples and
the README register it. It takes **one request object**: a URL string becomes `{"url": …}` with
`["ctx","dict",{"url":"obj"}]`, so `["udf","fetch"]` works after a list of URLs and after a request
field map.

## `type`

`["type", "Article"]` calls the host-registered constructor with the current value, exactly like the
old step boundary (`03` §3): a mapping is `Cls(**payload)`, a list `Cls(*items)`, anything else
`Cls(value)`. The constructor is a validator: the product continues as JSON, so a dataclass's fields
are rebuilt into the JSON they approved, and a constructor that answers a non-JSON object is
`UP2-E2003`. An unregistered name is `UP2-E1011`; a constructor that raises is `UP2-E2019`.

A field-map node cannot carry a trailing stage, so a node that needs a named shape wraps its map:

```jsonc
"detail": [["node", "detail_fields"], ["type", "Article"]],
"detail_fields": { "url": …, "title": … }
```

This is deliberate: the field map stays one shape, and the call model is the only way to compose.

## The run

```python
run(
    story: Mapping[str, Any],
    node: str | None = None,
    input: Any = None,
    *,
    globals: Mapping[str, Any] | None = None,
    udfs: Mapping[str, UdfFn] | None = None,
    trace: Trace | None = None,
) -> Any
```

1. merge the udf table (process-wide defaults + `udfs`) and compile the story with that table
   visible, so known functions get their signature checked;
2. resolve `node` (default: the first node) and `globals` (story constants + overrides);
3. fail `UP2-E1010` if a udf name the story uses is missing;
4. execute the node with `Scope(globals=effective, locals={}, public={}, step_input=input,
   udfs=effective)`;
5. `pack` the product; a non-JSON exit is `UP2-E2003` at the entry node.

The run is synchronous and has no suspension. The host that wants concurrency runs several `run`
calls (or one `run` over a list) in its own threads; the kernel never starts one. The materialization
cache lives on the run's scope, so it is released with the run.

## Errors

| Code | Use |
|---|---|
| `UP2-E1005` | malformed story/node/stage shape (`nodes` empty, `[]` is allowed, `{}` is not, a `type` stage not last) |
| `UP2-E1006` | unknown reference root or a path into `obj` |
| `UP2-E1009` | a node name is reserved or contains `.` / `/` / `~` |
| `UP2-E1010` | a udf name is not in the run's table |
| `UP2-E1011` | a `type` stage names an unregistered type |
| `UP2-E1012` | `MAX_STORY_NODES`, `MAX_STEPS_PER_FIELD`, `MAX_EACH_DEPTH`, `MAX_FIELDS_PER_MAP` |
| `UP2-E1016` | a `node` stage names no node of this story |
| `UP2-E1017` | the node-call graph closes a cycle |
| `UP2-E2003` | the exit product (or a `type` product) is not JSON |
| `UP2-E2009` | a udf returned an awaitable |
| `UP2-E2019` | a type constructor rejected the value |

`UP2-E1018` (unreachable step) and the effect-specific `UP2-E2005` paths are removed with the model.
`UP2-E2005` remains for value conversions (`split`, `strptime`, …).

## Migration

- Samples: each `site.json` becomes `globals` + `nodes`; each host registers `fetch` (and its
  `store` / `type` names) and calls `run(story, node=…, input=…)`.
- CLI: `up2 lint` reports node names; `up2 trial` takes `--node` (default: the first node). The
  story trial has no host, so a story that calls `udf` reports `UP2-E1010` and names the missing
  functions.
- Snapshot runner: `run(story, input=value, udfs={"fetch": cached_fetch})`; the first node is the
  default entry.
- Store: `publish`/`snapshot` compile the new shape; no schema change.
- Trace: `step` becomes `node` in the event; the effect fields and `EFFECT_*` constants are removed.
- README: the hero is rewritten around the node model, and the GitHub pinned example is tested and
  added to both languages.

## Alternatives considered

- **Keep effects and add nested suspension.** Rejected: the user's model is a synchronous call
  model; nested effects still produce serial requests and force a host loop for every fetch.
- **Make `fetch` a built-in operator.** Rejected: the kernel must not perform IO; `fetch` is host
  code, and the udf table already provides the binding point.
- **Give field maps a trailing `type` stage by allowing an object as a stage.** Rejected: it breaks
  the "array = chain, object = field map" rule; the wrapper node keeps one shape.
- **Let `py` use the DTO/`*`/`**` forms.** Rejected: `py` is a closed table with declared parameters;
  changing its binding would rewrite 48 actions and their compile-time checks. The forms are the
  `udf` contract, where signatures are arbitrary.
