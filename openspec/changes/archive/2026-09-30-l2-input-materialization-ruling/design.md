# Design

## D1 — The format is decided where the value is consumed, not at the entry

Measured on this commit, the operators already materialize on demand: `["css","nodes","li"]` on HTML text
returns the node list, `["json","a.b"]` on JSON text parses the text on every evaluation
([jsonquery.py:80-82](../../../src/uniparser2/ops/jsonquery.py#L80)), and `["xpath", …]` does the same for
XML. A `bytes` input is refused by all of them (`UP2-E2002 … got bytes`). So an eager `input_format` on the
seed only **declares** what the consumer already decides by being that consumer.

`bytes` settles the boundary from the other side: the value domain is `JsonValue | Opaque`
([values.py:24-26](../../../src/uniparser2/core/values.py#L24)), and `is_json_value(b"…")` is `False`
(measured), so a binary payload cannot travel in a chain at all. Decoding therefore belongs to the caller
(`run(chain, inputs)`, the CLI's `--input K=@file`), and a genuinely binary document — an image, a PDF, a
gzip stream — is either materialized by the host or carried in as text.

Rejected: keeping `input_format` as a mere declaration. The chain would name a format it may never consume,
the entry point would become a format registry, and the same fact would live in two places — the argument
that already deleted `outputs`/`produces` (`03` §4.5).

## D2 — What eager materialization bought, and what it cost

It bought exactly one thing: the document is parsed once. Measured, that is worth having — one parse costs
48.0 ms at 2 MB and 109.6 ms at 5 MB, and 20 fields that each re-parse take 748.8 ms / 1976.7 ms against
16.5 ms / 48.6 ms when one parse serves all 20 (**40–45×**).

The price is that every chain must name a format up front and the entry point must know about formats. The
same property is available from the value flow instead: materialize on demand and let a run-scoped cache
make the second consumer free.

## D3 — The cache contract

| Aspect | Rule |
|---|---|
| Scope | one evaluation run; released with it. Nothing crosses runs, so no `Opaque` handle outlives its run and two runs cannot observe each other |
| Key | (target format, source value) — object identity first, content hash on a miss; hashing 5 MB costs a couple of milliseconds against the ≈110 ms parse it saves |
| Bound | a byte cap with LRU eviction; eviction re-parses and nothing else, because materialization is a pure function of the text |
| Purity | a hit and a miss MUST be observably identical (same value, same handles' behaviour); a test pins the equality |
| Mutation | a cached tree MUST NOT be mutated in place. `remove` already copies before pruning ([htmldom.py:130](../../../src/uniparser2/ops/htmldom.py#L130) re-parses the subtree); this becomes a contract for every format operator |
| Implementation | one shared materialization entry per format, declaring its optional dependency (`tomllib`/`csv` stdlib, YAML third-party); a missing one is `UP2-E1107` with the install line, like `css`'s selectolax |

Memory, measured as RSS on this commit: the tree is **≈24×** the text — 2 MB → +49.3 MB, 5 MB → +121.7 MB.
That number sizes the cap, and it is the reason the cache is *not* a module-level one: N documents would be
N × 120 MB, retained forever.

## D4 — The cache is load-bearing, so it is part of the design

With no eager materialization, "one document, one parse" is guaranteed **only** by the cache. It therefore
stops being an optimization: `007` §3's L2 acceptance item ("500 items × 20 fields within 3 s") depends on
it, and it needs its own tests — hit-vs-miss equality, eviction correctness, and release at the end of a run.
It lands with the node layer, which is where many fields and nodes start from the same input value; L1
chains are linear and short, so nothing in the operator layer changes today.

## D5 — Rejected alternatives

| Alternative | Why not |
|---|---|
| Writable `globals`, or a third mutable scope, for cross-node state | a chain-level writable store makes one value evaluate differently in different fields and nodes, and needs "who wrote first" and "roll a half-failed node back" rules — against `N1`. `globals` stays a chain-level constant the **caller** writes; cross-node sharing stays with node products (`03` §3, §8), which any later node references by key without relaying |
| A module-level cache inside the format operators | unbounded growth, `Opaque` handles crossing runs, and concurrency needing its own answer; and it would be a second mechanism for a property the value flow can already provide |
| Eager materialization kept **and** the cache added | two mechanisms for one property — the failure mode this repository has retired three times (`select`/`callback`/`$map`, `outputs`/`produces`) |
