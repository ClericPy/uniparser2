# Design — allow host objects as values

## Context

See `proposal.md` — Why. The kernel already carries one kind of third-party object: an `Opaque` DOM handle
flows through a run and is rejected only at the exit (`core/export.py`). Everything else (a response, a
`udf` result) is forced to JSON at a stage boundary, and `UP2-E2009` enforces that by message.

## Goals / Non-Goals

- Goal: a host object flows the way a DOM handle already does, and `py.getattr` reads it.
- Non-goal: general method calls — no arguments, no mutation, no arbitrary host code. That stays `udf`
  (registered, host-versioned) or the opt-in `code` sandbox.
- Non-goal: changing what a **product** may be. Products stay JSON.

## Decisions

1. **Reuse the `Opaque` mechanism instead of adding a second one.** A host object is an opaque value:
   previewed as `type_name` plus a truncated `repr`, refused by `export.pack`.
   *Alternative rejected*: a wrapper class (`HostValue(obj)`) — it adds a layer to unwrap everywhere while
   introducing no rule that differs from `Opaque`'s.
2. **The line is "may flow" vs "may be a product", not "enters the chain" vs "does not".** The old sentence
   was already false for DOM handles. Products stay JSON so the single exit, snapshots and the trace stay
   comparable. *Alternative rejected*: object products — they break snapshot comparison and the exit rule.
3. **`getattr` refuses callables.** A method is never silently turned into a value; the failure names the
   operator to use (`["css","text",""]`) or a `udf`. *Alternative rejected*: auto-calling zero-argument
   attributes — `selectolax`'s `Node.decompose` takes no arguments and mutates the tree, so a chain could
   mutate the document with no visible trace.
4. **Reference resolution dispatches per value kind**: mapping by key, sequence by index, object by
   `getattr`. One dotted path then works on a dictionary and on an object; the failure mode names the class,
   as `getattr` does.
5. **`Response` stops being a type.** The answer is what the host `send`s back, untouched. `Request` keeps
   its neutral structure: a story's outgoing intent must be library-independent, an incoming answer is the
   host's own fact. *Alternative rejected*: shipping our own `Response` class — it loses the library's own
   surface (`headers` case handling, `.json()`, `.request.url`, encoding, timing) and duplicates what the
   host already holds.

## Risks / Trade-offs

- A story becomes coupled to the host library's attribute names (`status_code` vs `status`) → the samples
  record which host they were written against, and a host may adapt before `send`.
- Objects are not comparable across runs → they never become products, so snapshots compare JSON.
- `getattr` can reach undocumented library internals → the callable refusal plus the documented action
  surface; anything richer is a `udf`.

## Open Questions

- Whether a zero-argument, explicitly named `callattr` is ever needed (a `udf` covers it today).
