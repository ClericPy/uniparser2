# Design

## Context

See `proposal.md` — Why. Two measurements drive it:

- `pack(Article(...))` answers `Failed(UP2-E2003)`, and `typeop.evaluate` answers the input payload
  whenever `pack(built)` fails — so a dataclass constructor's answer is always discarded.
- A `udf` answering `Article(...)` flows mid-chain and `["py","getattr","t"]` reads it; a story node
  may even produce it and a later node reads it. Only `run`'s exit calls `pack`.

So the kernel already supports a typed object flowing through a run. `type` is the one place that
contradicts it.

## Goals / Non-Goals

**Goals:**

- `type` answers what it built; a later stage can use it.
- A chain may put `type` anywhere.
- Two runs in one process may resolve one type name differently.
- The exit stays JSON, and that boundary does not move.

**Non-Goals:**

- Making the exit accept a host object (it is the snapshot/comparison boundary — `N5`, `pack`).
- A built-in serializer for a constructed instance (a `udf` or an explicit field read is the way).
- Supporting `TypedDict` as a validator (see D4).
- A `tag`-style discriminator (see D3).

## Decisions

### D1 — The stage answers the constructed value

`Ok(build_type(name, value))`, with no `pack` on the way out. The two consequences are deliberate:

- a JSON-constructing type (`int`, `dict`, a JSON-shaped `NamedTuple` field) answers JSON, so nothing
  changes for it;
- a container type (`dataclass`, pydantic model, msgspec `Struct`) answers an object, which flows and
  is refused only where JSON is required — the exit.

`pack` is therefore checked **once**, at the boundary that cares, instead of being simulated inside
the operator to decide what to carry.

### D2 — The chain-tail rule goes with it

The rule existed because the carried value was the payload: a later stage would see a mapping while
the reader of the chain expected an instance. With D1 the carried value *is* the instance, so a later
stage sees exactly what `type` built. `["type","Article"], ["py","getattr","title"]` is now the
natural spelling, and it is the only one that can feed a typed value to a `udf`.

*Alternative rejected*: keeping the tail and adding a second action (`["type","construct", name]` vs
`["type","check", name]`) — two spellings for one idea, and the tail would still need a reason to
exist (it would have none).

### D3 — A run's table is an overlay, keyed by the chain-visible name

`run(..., types=...)` accepts a mapping **or** a sequence of callables:

```python
run(story, types=[Article, Book])  # names come from __name__
run(story, types={"article.v2": ArticleV2})  # the chain writes "article.v2"
```

A sequence is `{cls.__name__: cls for cls in types}`; a mapping is used as it stands. The merge is
`{**all_types(), **overlay}`, so an overlay wins and the process-wide table is untouched. The
implementation copies `udfs` exactly (`ContextVar` + `Scope.types`), because the compile step and the
evaluate step must see one table.

**This is not `msgspec`'s `tag`.** `tag` writes a type discriminator *into the payload* so a union can
be decoded; it is a serialization concern. Here the name is a **lookup key** in a host table, and the
chain already carries it as a literal — no payload field is involved, and no dependency is needed.

*pydantic*: no special case. `Model(**payload)` is the contract `_call` already uses, and
`ValidationError` becomes `UP2-E2019` through the existing `except Exception` in `build_type`. The
`ConfigDict(title=...)` of a model is JSON-Schema metadata, not a name — a custom name is spelled in
the registry, not in the model.

### D4 — `TypedDict` is not a validator; `NamedTuple` is

`TypedDict` erases to `dict` at runtime: `TD(**payload)` returns a plain dict and checks nothing
without pydantic/typeguard. Registering one would look like validation and be none, so it is not
documented as a type. `NamedTuple` is a real callable, has `__name__`, and its instance is a host
object — it works under D1 with no code of its own.

### D5 — The exit rule is unchanged

`run` still packs the entry node's product, so a constructed instance at the exit is `UP2-E2003`. This
is the honest boundary: *what flows may be an object; what leaves is JSON*. A chain that wants to exit
with a record writes the fields out (a field-map node) or serializes with a `udf`.

## Risks / Trade-offs

- **BREAKING.** A chain that ended with `["type","Article"]` and expected the payload now carries the
  instance. No committed sample writes one; the tests and the notes do, and the notes say it.
- **A silent regression becomes a loud one.** Previously an exit carrying a non-JSON construction was
  "handled" by substituting the payload; now it fails. The new failure names the type and points at the
  exit node, which is what a reader needs.
- **`type int` vs `py int` overlap stays.** Both convert; `type` is the only one that can name a host
  class. The docs are explicit, and no attempt is made to remove the overlap (it is the same Python
  constructor).
