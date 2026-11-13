# Make `type` construct the declared type, and let a run inject its own

## Why

`type` builds the declared constructor and then **throws the result away** (`typeop.py:75-80`):
`pack(Article(...))` fails with `UP2-E2003`, so `_same_json` substitutes the input payload. A host
spends a constructor call and receives nothing — the instance never reaches a later stage, so
`["type","Article"], ["py","getattr","title"]` cannot be written, while the very same object coming
from a `udf` flows mid-chain and can be read that way (measured).

The chain-tail restriction (`UP2-E1005`) exists only as a consequence of that discard: a later stage
would receive a plain mapping while the reader expects an instance. Once the instance really flows,
the ambiguity is gone and the restriction has no reason to stay.

Separately, the type registry is **process-wide only**: `register_type` mutates a module dict, so two
runs in one process cannot use different constructors for one name. `udf` solved this already
(`run(..., udfs={...})` over a `ContextVar` overlay); `type` never caught up.

## What Changes

- **`type` carries the constructed value**, not the payload it was built from. `["type","Article"]`
  answers `Article(...)`; a later stage reads it with `py.getattr` or passes it to a `udf`.
- **The chain-tail restriction is removed**: `["type", name]` may appear anywhere in a chain.
  `UP2-E1005` for "a `type` stage must be the last stage" is gone (the code stays in `CODES`, the
  check does not report it any more).
- **A run MAY inject its own type table**: `run(story, ..., types={...})` merges over the process-wide
  registry for that run, exactly as `udfs={...}` does. Classes may be passed directly (the name is
  `__name__`) or as a `name → constructor` mapping (the name is whatever the chain writes).
- **The exit is still JSON**: a run whose product is a constructed instance fails `UP2-E2003` at the
  exit node, unchanged. The instance flows *mid-chain*; the boundary rule does not move.
- **pydantic needs no special case**: a model is a callable whose `Cls(**payload)` constructor is the
  contract the stage already uses, so a pydantic model and a dataclass are the same category. No
  dependency is added (`dependencies = []`).
- **`TypedDict` is not a validator**: at runtime it is a `dict` and validates nothing without a
  third-party checker, so supporting it would advertise a check that does not happen. `NamedTuple`
  works for free (stdlib, callable, a host object).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `core-evaluator`: the declared type is constructed at any stage, and the constructed value is what
  the chain carries on.
- `dsl-operators`: the `type` operator constructs instead of validating a tail, and its arity rule
  stays (two slots, one action).
- `story-nodes`: `type` is no longer chain-tail, and `run` gains the `types` overlay.

## Impact

- `src/uniparser2/ops/typeop.py`: the stage answers the constructed value.
- `src/uniparser2/core/compile.py`: `_check_type_tail` and `TYPE_OPERATOR` go.
- `src/uniparser2/core/types.py`: a `ContextVar` overlay, `all_types`, `use_types`.
- `src/uniparser2/core/story.py`, `src/uniparser2/core/refs.py`: the `types` parameter, the merged
  table, and `Scope.types`.
- **BREAKING**: a chain that ended with `["type","Article"]` used to answer the payload and now
  answers the instance, so an exit that relied on the payload fails `UP2-E2003`. No committed sample
  writes a `type` stage; the tests and the notes do.
- Docs: `docs/specs/002`, `docs/specs/003`, and the changelog under the version this ships in.
