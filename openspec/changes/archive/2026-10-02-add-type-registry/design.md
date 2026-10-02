# Design — the type registry and the step boundary

## Context

See `proposal.md` — Why. `03` §3 has described the mechanism since the story model landed: a name the
host registers, a constructor the kernel builds from the product at the step boundary, and the product
continuing as JSON. What exists today is the boundary itself (`core/story.py`'s `_step_product` already
checks that a product is JSON through `core/export.pack`) and the reserved code `UP2-E1011`.

Two constraints shape the approach. The kernel is **stdlib-only, IO-free and fully synchronous**, so the
registry can only be pure dictionary operations — `core/udfs.py` is the precedent, and a class of the
same import set fits. And a story bundle is compiled by `up2 lint` / `up2 trial`, i.e. **in a process
that never registered a type**: registration cannot be a precondition for compiling, so the registry is
consulted at the boundary and never at compile time.

## Goals / Non-Goals

**Goals:**

- One documented API (`register_type` / `unregister_type` / `type_names` / `get_type`) that a host uses
  before the run, with no change to the bundle format.
- The declared shape validated **at the step that produced it**, with the constructor's own exception
  text in the diagnostic, so the author sees which key is wrong.
- The product continues as JSON: the single exit and the snapshots stay comparable.

**Non-Goals:**

- No schema language: the constructor **is** the schema (a dataclass, a pydantic model, a hand-written
  validator), so the kernel names no model framework.
- No host-side post-run validation library and no `Article.model_validate` wrapper: a host that wants an
  object builds it from the exit product itself.
- No compile-time check of the type name (that would make `up2 lint` depend on host state).

## Decisions

1. **`register_type(name, constructor)` — not `register_model`.** The parameter is a class *or* any
   callable, and `model` names a framework rather than the contract; `type` is also the word the DSL
   already uses (`03` §3.1), so the API and the step key agree. *Alternative rejected*:
   `register_model`, which reads narrower than the contract and ages with whatever model library is
   fashionable.
2. **A module-level registry in `core/types.py`, mirroring `core/udfs.py`.** A host installs its
   vocabulary once per process; the kernel's other extension surfaces (`register_udf`, the operator
   registry) have exactly that lifetime. *Alternative rejected*: a registry object threaded through
   `start(...)`, which adds a parameter to every entry point for the one caller that wants isolation —
   `unregister_type` serves the tests instead.
3. **The name is resolved at the step boundary, not at compile time.** A recipe is data and may be
   linted where the types were never registered; the boundary is the first point where the registry and
   the product are both known. The cost is that `up2 lint` cannot report an unknown type name; the
   benefit is that a bundle stays a portable artifact with no host prerequisite. *Alternative rejected*:
   a compile-time check against an explicitly passed registry, which would make `lint` fail on a recipe
   that a host can run.
4. **The built-in names are a closed set the host may shadow.** `list` / `dict` / `Request` /
   `RequestBatch` keep the product as it is (a dictionary product written `"dict"` must keep its keys),
   the scalar names (`str` / `int` / `float` / `bool`) go through their Python constructor — the same
   coercion a host constructor would perform — and `null` answers nothing. A host registration is
   consulted first, so a host that wants its own `int` construction gets it.
5. **A constructor is a validator, not a container.** After the call the boundary keeps JSON: a
   constructor that answers a JSON value (a plain `dict`, a scalar, a `list`) is the product; a
   dataclass (or model) whose fields are the payload it was handed answers an object, so the payload
   is what continues; anything that is not JSON is refused by `pack` at that same step
   (`UP2-E2003`). *Alternative rejected*: letting the constructed object flow — it breaks the single
   exit, the snapshots and the trace, and is exactly what `03` §3.3 forbids.
6. **Two codes, two very different failures**: `UP2-E1011` (nothing is registered under that name —
   the *author's* mistake) and the new `UP2-E2019` (a registered constructor refused the product — a
   shape mismatch that the constructor describes best). `UP2-E2019` proved free: `CODES` has no such
   entry, and `002` §7.1 lists `E2001`–`E2018` plus `E2099`, with only `E2015` retired. `UP2-E1011` was
   reserved for this check by `002` §7 and `03` §10 L8 and had never been implemented.

## Host-side example

```python
from dataclasses import dataclass

import uniparser2 as up2


@dataclass
class Book:
    """The declared shape: its fields are the product's keys."""

    url: str
    title: str
    price: str
    pub_time: str = ""


up2.register_type("Book", Book)

bundle = {
    "steps": [
        {
            "name": "book",
            "parse": {
                "url": [["py", "getattr", "url"]],
                "title": [["py", "getattr", "text"], ["css1", "text", "h1"]],
                "price": [["py", "getattr", "text"], ["css1", "text", "p.price_color"]],
            },
            "type": "Book",
        }
    ],
    "exit": "book",
}

run = up2.start(bundle, response)
effect = run.next()
# A product missing `price` stops here, not at the exit:
# UP2-E2019: the type 'Book' rejected the step product:
#   TypeError: Book.__init__() missing 1 required positional argument: 'price' | at /steps/0
#
# A name nobody registered stops here too:
# UP2-E1011: the step declares type 'Book', which no host registered | at /steps/0
```

## Risks / Trade-offs

- **A story becomes coupled to the host's registered names** → a bundle names types only, and
  `UP2-E1011` lists what is registered, so the mismatch is a one-line fix; the samples declare built-in
  type names and stay runnable with no host registration.
- **`up2 lint` cannot see the registry** → `lint` still validates everything static (the name is a
  non-empty string, the bundle shape, the references); the boundary reports the rest at the first run,
  which `up2 trial` reaches.
- **A dataclass that types a field the payload does not carry adds that key to the product** → the
  constructor's answer is what continues, exactly as a `Cls(*items)` collection decides a list's
  items; a key that must be absent from the product is a field-map decision (the product's own keys),
  and a missing required key is still `UP2-E2019` at that step.
- **Module-level state and tests** → the cases that register a name unregister it in teardown, and the
  story cases register the two names they declare.

## Open Questions

None. `03` §13 O1 is settled by decision 1.
