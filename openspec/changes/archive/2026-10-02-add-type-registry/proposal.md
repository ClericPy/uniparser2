# Add the type registry and the step-boundary construction

## Why

A step's `type` has been a **declared name only**: nothing checked it, so `"type": "Article"` was
documentation the kernel never used, and the shape a host cares about could only be validated by the
host after the run. `03` §3 already describes the mechanism that closes this — a host registers
name → constructor, and the kernel builds the declared type from the product at the **step boundary**,
where the product is produced and where the author can see which key is wrong. `UP2-E1011` has been
reserved for the unregistered name since that section was written.

## What Changes

- **The type registry lands** (`core/types.py`): `register_type(name, constructor)` with
  `unregister_type` / `type_names` / `get_type` beside it. The registry is process-wide host state
  exactly like `register_udf`, never part of the bundle, so a story stays library-independent data.
- **The step boundary builds the declared type from the product**: a dictionary is `Cls(**payload)`, a
  list `Cls(*items)`, anything else `Cls(product)`. The constructor is a **validator, not a
  container** — the product continues as **JSON**, and a constructor that answers anything but the
  payload it validated is refused by `pack` at that same step (`UP2-E2003`).
- **An unregistered name is `UP2-E1011`** at the step that declares it, listing the registered names
  (the built-ins included). The check is at the boundary, not at compile time, because `03` §2's two
  file shapes compile without a host.
- **A constructor that raises is the new `UP2-E2019`**, at that step and with the constructor's own
  exception text in `reason` (`UP2-E2019 the type 'Article' rejected the step product: TypeError:
  Article.__init__() missing 1 required positional argument: 'title'`).
- **The built-in names are registered for free**: the JSON basics (`null` / `bool` / `str` / `int` /
  `float` / `list` / `dict`) and the effect types `Request` / `RequestBatch`. `list` / `dict` and the
  effects keep the product as it is; the scalar names go through their Python constructor. A host
  registration wins over a built-in name.

## Capabilities

### New Capabilities

None. The registry and the step boundary belong to the capabilities that already own the value domain
and the story layer; a third one would split the same boundary across two specs.

### Modified Capabilities

- `core-evaluator`: a step product is validated by the host-registered type at the step boundary, and
  the type registry API is added to the value domain's contract.
- `chain-iteration`: a step's `type` is a name the kernel resolves against the registry at the
  boundary, so an unregistered name and a refusing constructor are failures of that step.

## Impact

- Kernel: new `core/types.py` (the registry and `build_type`); `core/story.py` (the boundary builds the
  declared type and reports the two codes); `core/errors.py` (`UP2-E1011` was reserved, `UP2-E2019` is
  new); `core/__init__.py` and `uniparser2/__init__.py` re-export the registry API.
- Docs: `03` §3.1/§3.2/§3.3/§9/§10 L8/§13 O1, `002` §7/§7.1, `001` §1.2/§4.2, `007` §3/§5, both
  READMEs, and a host-side example in this change's `design.md`.
- Tests: `tests/chains/test_type_registry.py` (a registered dataclass, a rejection, a list product, a
  nested rejection, the exit product staying JSON), and the existing story cases register the two names
  they declare.
- No dependency change and no DSL syntax change: a bundle whose `type` names a built-in type runs
  exactly as before.
