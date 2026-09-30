# Design

## D1 — `each` is an operator, not a `py` action

Three concrete reasons, each measured on this commit:

- **Its argument is not a value.** `py`'s 32 actions declare parameter kinds that resolve to leaves,
  and `_resolve_param` walks a container with that same kind
  ([compile.py:307](../../../src/uniparser2/core/compile.py#L307)), so a field map needs a new
  parameter kind whichever operator declares it.
- **It calls no Python function.** `py` is the standard-library allowlist: `_TABLE` maps a name to a
  function, `README` / `docs/operator-reference.md` / the conformance audit all promise "32 pure
  functions", and a `("py","each")` pair would be a 33rd that is not one.
- **Running a sub-chain is a capability no operator has.** Nothing under `ops/` imports
  `core.evaluator` or `compile_field`, and `Call` carries only `value` / `action` / `params` /
  `payload` / `scope` ([registry.py:103](../../../src/uniparser2/core/registry.py#L103)). D2 gives
  that capability a home instead of putting it inside the value-transform module.

Arities also differ: `py` is 3-slot (`["py", action, params]`), while `each` is a 2-slot single-action
operator like `const` / `json` / `code`, so slot 3 would otherwise carry both "a JSON value" and "a
field map". Rejected: `["py", "each", {…}]`.

## D2 — The kernel injects the sub-chain runner into the call

`each` needs to evaluate compiled sub-chains, and today no operator may. Rather than let the operator
import the evaluator (legal by direction — `ops → core` is the allowed way — but then each structural
operator re-implements scope creation and policy plumbing), the kernel injects a runner into the call
context: "evaluate this compiled chain against this value in this scope". `each` stays a plugin, and a
later structural operator (element filtering, for one) enters through the same door.

## D3 — The argument is inline; `presets` is not introduced

The field map has exactly the shape a `parse` node's `fields` has, so `each` can be stated in one
sentence — *run a fields block once per element* — and the argument sits where it is used.

Inline therefore deletes a container, a name-resolution pass, a dangling-name error class and the
"presets cannot reference one another" wart recorded as D-02-4; diagnostics keep their pointer at the
use site (`/1/title/0/2`) instead of pointing at a chain shared by N callers; and being self-contained
makes nesting possible at all. Rejected: naming the argument (`["each", "row"]`), and accepting either
a name or an object — two shapes in one slot is exactly the smell that retired `select`. If reuse ever
becomes real it belongs to a *callable stage* (`["preset","row"]` used like any other stage), never to
a second argument shape; that is not this change.

## D4 — The input is a list, strictly

`each` accepts a list and nothing else. The alternative — list, string and object each iterating
"their elements" — is rejected on four measured grounds:

| Ground | Measurement on this commit |
|---|---|
| The operator set is already list-only and type-strict | `py.flatten` and `py.getitem` reject a string, an object and a tuple with `UP2-E2002` |
| Object items are unusable | the element would be a `(key, value)` pair, and `py.getitem` rejects tuples outright (`py.getitem needs a list, got tuple`) — no operator could consume it |
| "Iterate it" is not one rule | Python's own iteration yields **keys**, so list/string/object is three hand-written rules; the string rule re-opens the `for c in text` footgun that `py` deliberately closes |
| A branch does not buy generality | the callback still has to be written for one element shape (`py.get` vs `py.getitem`), so the mismatch surfaces later and deeper (`get needs a dict, got list`) instead of at the boundary |

A non-list input is `UP2-E2002`, which is the existing "stage input type does not match" code, and the
fix line names the conversion to write. A later change may add `py.items`; it must produce lists, not
tuples, for the second row above.

## D5 — One dictionary per element, and no element is ever dropped

The result holds exactly one dictionary per input element, in input order, so "the list on the page"
and "the list in the export" can be aligned by eye. A field whose value resolves to absent under the
effective policy is simply not a key of that element's dictionary, and an element whose fields all
resolve to absent is still `{}`.

Rejected: implicitly dropping "empty" elements (a rule that can only be guessed, and the reason a
two-stage chain suddenly returns 2 rows where the page had 5) and a `keep`/`filter` mode on `each` (it
would embed a predicate language in an iteration operator, and element filtering is worth a separate
operator that can sit before *and* after `each`). "Per element" describes the scope and the policy
application, not a swallowed error: a `Failed` whose effective policy is `raise` propagates out of
`each` with the failing stage's code.

## D6 — Every element gets its own scope, and reads fall back outward

Each element is evaluated in a fresh child of the calling scope. Reads fall back outward — the
element's own locals, then the calling scope's locals, then the chain-level values; writes always land
in the element's scope, and the element's locals do not outlive the element.

Sharing one scope would let element 2 read what element 1 stored under `_t`, and the bug would be
invisible: the value is present, so nothing reports a missing value. Rejected: innermost-only lookup
(an outer temporary becomes unreachable, and the alternative — copying the calling locals into every
element — silently freezes values instead of reading the live ones). The scope chain becomes a stack
(`Scope` gains a parent link); the node layer will need the same mechanism, so it lands here rather
than being redesigned later.

## D7 — A `_`-prefixed key is the temporary mechanism; no `filter` construct

The dictionary of an element holds exactly the field names that do not start with `_`. A `_`-prefixed
key is stored in that element's locals: readable by the later fields of the same element, absent from
the result. This is the node-level rule of `003` §4.2 — recorded as an Adopt decision in `007` ("the
convention that a `_` prefix means locals") — applied one level down, so it is learned once.
`ctx.set "locals.x"` keeps its meaning mid-chain (it passes the upstream value through), which covers a
temporary created and consumed inside a single chain.

Rejected: a `filter`-like directive for excluding a computed key (post-hoc where the prefix is a
declaration, and it would need a truthiness language — the operator set has no comparison operator at
all — plus an answer for fields that already referenced the value), and a separate `locals` block
beside `fields` (two blocks need an ordering rule, and a temporary derived from an earlier field could
not be declared in place; the prefix is what keeps a single ordered sequence).

## D8 — One limit at compile time, one at runtime

`MAX_EACH_DEPTH` (3) is statically visible in a compiled field map, so nesting deeper than that is
`UP2-E1012` at compile time, in the same spirit as `MAX_STEPS_PER_FIELD`. `MAX_EACH_ITER` (10 000) is
only known at runtime, so it is `UP2-E2012`, checked **before** any field chain runs — a list that is
too long never parses its first element — with a fix line naming `py.slice`. Rejected: reporting the
depth as `UP2-E2012` (the old `$map` wording) — that code is about evaluation, and depth is a
compile-time property.

## D9 — `$item` is removed rather than reinterpreted

The element is already the input value of every field chain inside `each`: a pipeline fact, not a name.
"The element itself" already has a spelling in the operator set — the `self` value mode of
`css` / `css1` / `xpath` — and the one place that wants a *reference* to it (`code`'s `inputs`) can read
its upstream value or a `locals` entry. So `item` leaves `RESERVED_ROOTS` (four names become three:
`globals` / `locals` / `fields`), and `_DEFERRED_ROOTS` / `_DEFERRED_FIX` with the `UP2-E1006`
deferred-root branch leave with it — machinery that existed only to explain `$item` in L1.

## D10 — What this change deliberately does not do

The node layer — `seed` / `parse` / `emit` execution, `routes`, `result` assembly, the node trace of
`up2 trial`, the `UP2-E11xx` lint set — is **not** implemented here. Its design notes are re-aligned
(the three retired mechanisms are deleted and `each` takes their place), and the layer lands in a
following change. In particular `fields` and `locals` stay one namespace for now: there are no nodes
yet to split them, and `refs.py` already documents the alias as an L1 property that the node layer
ends.

## D11 — Version

`005` §7: during `0.x` a new capability bumps the minor, so `__version__` goes `0.2.0` → `0.3.0`. The
conformance audit moves from 60 to 61 declared pairs and from 25 to 26 implemented error codes
(`UP2-E2012` joins `CODES`); the CHANGELOG records the new operator, the withdrawn `$item` root and the
design-level retirements.
