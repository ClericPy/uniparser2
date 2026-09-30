# Design

## D1 — The three new rejections reuse existing codes

None of the three rules is a new failure class, so none of them adds a code:

| Rule | Code | Why that code |
|---|---|---|
| A map with no fields | `UP2-E1005` | schema validation at the same pointer where "the value is not an object" is already reported |
| A field name that is empty or contains `.` | `UP2-E1005` | same: the map's shape is invalid, not the chain's semantics |
| More than `MAX_FIELDS_PER_MAP` fields | `UP2-E1012` | `UP2-E1012` is "resource limits exceeded" and already covers `MAX_STEPS_PER_FIELD` and `MAX_EACH_DEPTH` |

A dedicated code would add a branch that carries nothing the message does not already carry — the ground
on which `002 §7.1` retires `UP2-E1008`. Keeping one code per class also keeps the conformance audit's
26 codes and the delta spec's single requirement intact.

## D2 — The bound is 256 fields, counted per map

Measured on commit `06fc57e`, compiling one `each` field map with N trivial fields: 1 000 → 10.8 ms,
5 000 → 55.4 ms, 20 000 → 241.2 ms, and the compiled sub-stages equal N. The cost is linear in the field
count and is paid on the **compile** step, which `up2 lint` and the trial UI run interactively. 256 keeps
one map to a few milliseconds while sitting an order of magnitude above the largest realistic map (a
table row with dozens of columns); 1 024 buys nothing and keeps a ~10 ms compile per map.

The check counts **one map's own fields**, not the total across a chain: `MAX_STEPS_PER_FIELD` already
bounds the per-chain work, and `MAX_EACH_DEPTH` bounds the nesting. It is a compile-time check because the
cost is paid before anything is evaluated — a runtime check could not prevent it.

## D3 — A field name must be addressable

`parse_ref` splits a reference on `.` ([refs.py:63](../../../src/uniparser2/core/refs.py#L63)), so a map
key containing a dot occupies a name that no path can reach: measured before this change,
`[["each", {"_a.b": [["py","strip",""]]}]]` compiles and yields `[{}]` — the value is computed and
discarded, silently. An empty name is the same defect with even less to point at.

Both are rejected at the offending key with the key named in the fix line. Rejected: accepting them and
documenting the limitation (a silently unreachable key *is* the defect), and adding an escape for dots in
path segments (a larger change to the reference grammar than the defect deserves).

## D4 — The fallback rule is by name, and the docs now say so

The implementation resolves a path by **first-segment ownership**: `_read_locals` walks outward until a
scope owns `path[0]`, then resolves the whole path there
([refs.py:141-146](../../../src/uniparser2/core/refs.py#L141)). The drafts said "reads fall back
outward … the element's locals, then this node's locals", which reads as per-key fallback. Two
measurements decide which one survives:

- `Scope.json_view` already merges the chain shallowly, outermost first with the innermost key winning
  ([refs.py:177-179](../../../src/uniparser2/core/refs.py#L177)), so in-chain code (`py`, `code`, `udf`)
  sees the element's own `_a` whole. A per-key read rule would make the reference view and the in-chain
  `ctx` view disagree about the same name — or force `json_view` to deep-merge, which it does not do.
- With first-segment ownership, the *current* scope's `_a` is the element's own variable. A per-key rule
  would let a key missing under it be satisfied by an unrelated outer `_a`, which is exactly the
  "element-local variable" the requirement promises not to be.

The alternative that removes the question instead of answering it — a strictly local `$locals` plus an
explicit way to name an outer scope (`locals.__parent__…`, `$loop.parent…`) — was considered and
rejected: it makes **every** cross-layer read pay for the one case that collides, because the author must
count nesting levels, and moving a chain one level deeper invalidates every count. The shadowing rule is
only observable when two levels deliberately reuse one name.

So: fallback is by name, authors keep a `_` name unique across nesting levels, and the machine check is
deferred to the L2 node layer, where a node's `fields` names are visible at the same compilation site —
one check then covers every level instead of half of them (recorded as an open item in `007`).

## D5 — One write path for element locals

`each` assigned `scope.locals[name] = value` directly. For a single-segment name that is what
`Scope.write_local((name,), value)` does ([refs.py:196-205](../../../src/uniparser2/core/refs.py#L196)),
so this is not a behaviour change: it removes the second write door, so a write-side rule added later
cannot be bypassed by the iteration operator. `_LOCAL_PREFIX` keeps deciding *whether* the value is a
temporary; the scope keeps deciding where it lands.

## D6 — Two public-API nits

- `loads` is exported and listed in `core.__all__`
  ([core/__init__.py:53](../../../src/uniparser2/core/__init__.py#L53)), yet `loads(source=…)` raises
  `TypeError: loads() got some positional-only arguments passed as keyword arguments` — verified on this
  commit. The positional-only marker buys nothing here (`dumps`, its round-trip partner, never had one),
  so it goes.
- `Scope.chain()` returns the scope lineage, outermost first, and its only caller is `json_view`. "Chain"
  in this repository means the DSL chain, so the method becomes the private `Scope._lineage()`: one
  caller, and the merge order stays stated in one place instead of being inlined into `json_view`.

## Not in this change

The L2 node layer (`seed` / `parse` / `emit`, `result`, `routes`, the `UP2-E11xx` lint set, the node
trace), the cross-level `_`-name check of D4, and the `$fields` / `$locals` / `$loop` namespace split
those need.
