# Design

## Context

The consumption half of `03` §6 is implemented: `css` / `css1` parse HTML text when handed a `str`,
`xpath` parses XML text, and `json` parses JSON text. Each stage that receives text therefore builds
its own structure, and a field map over one document pays one full parse per field.

The kernel invariants bound the solution: `core/` is stdlib-only and IO-free, everything is synchronous,
a value leaving a run passes through `core/export.pack`, and a chain is data that compiles without a
host. `MAX_MATERIALIZE_BYTES` and `MAX_MATERIALIZE_ITEMS` are already specified in `01` §9 but not yet
declared in `core/limits.py`.

Two seams are available for reaching an operator from a run: `Scope` (created per step, inherited by
`each` elements through `Scope.child`) and `registry.Call` (the context object every operator receives).

## Goals / Non-Goals

**Goals:**

- One parse per document per run, for every text-consuming operator.
- A bounded cache: `MAX_MATERIALIZE_BYTES` (64 MiB) in materialized bytes and `MAX_MATERIALIZE_ITEMS`
  (8) artifacts, both enforced by LRU eviction.
- One artifact larger than the byte cap stays usable while it is in use.
- A hit is observably identical to a miss; eviction costs a parse and nothing else.
- No new dependency, no new error code, no change to the chain syntax, and no public API churn beyond
  what a host needs to inspect the accounting.

**Non-Goals:**

- Adding new materialization formats (`tomllib` / `csv` / YAML entries of `03` §6). The entry shape
  makes them possible; no operator consumes them today, so no entry is declared.
- A module-level or cross-run cache: `03` §6 rules this out, and it is the reason the cache is not a
  global.
- Caching anything that is already in the value domain (an `Opaque` node, a parsed JSON value): only a
  `str` source is materialized.
- The trace (`06`) and the remaining L2 items.

## Decisions

### D1 — The cache lives on `Scope`, and a run builds exactly one scope

A `Materializer` is created lazily by the `Scope` that needs it, and `Scope.child()` shares it, so
every operator of one run reaches the same cache with no extra parameter threaded through `eval_field`,
`compile_field` or the operator signatures. `StoryRun` builds one scope for the whole run and re-points
its `step_input` per step, so the cache's lifetime is the run's lifetime and a run's cache is
collectible the moment the run is (the release requirement needs no finalizer).

Alternatives: a cache passed as an explicit `eval_field` parameter (touches every caller and the public
signature), a module-level cache keyed by run id (cross-run sharing, which `03` §6 forbids), a cache on
`CompiledStory` (shared by every run of one bundle, the same defect).

### D2 — `registry.Call` exposes the cache, so operators never import the evaluator

The operator already receives a `Call` carrying `value`, `params`, `payload`, `scope` and `run_chain`.
One more field, `cache`, follows that precedent: the operator reaches the run's cache without importing
`core.materialize`'s caller and without a new operator-facing protocol. The field is read-only.

### D3 — The key is `(format, source)`, identity first, a content hash on a miss

`03` §6 fixes the key: "the target format plus the source value — object identity first, a content hash
on a miss". Each entry keeps a **strong reference to its source**, so an entry's source can never be
collected while the entry lives; that kills the `id()`-reuse hazard (a collected string whose address is
later reused by another string) at the root. A lookup compares `entry.source is source` for the identity
hit and falls back to `blake2b` over the source text compared against the entry's digest, so an equal
but distinct string still hits. The hash is computed only on a miss path, where the parse it saves costs
orders of magnitude more.

### D4 — Accounting is in materialized bytes, measured by the consumer that materialized it

`sys.getsizeof` is not enough: a `selectolax` document is one object whose child nodes live in the C
extension, and `getsizeof` reports no more than its header, while a JSON tree is thousands of Python
objects. Each entry therefore declares its own size, measured at the moment of materialization:

| Format | Measure |
|---|---|
| HTML | the byte length of the parsed document's own serialization (a selectolax tree is a 96-byte Python handle whatever its size is — measured — so a walk of the handle measures nothing) |
| XML | the byte length of the document's serialized form |
| JSON | the tree's own footprint: container headers plus the payload of its strings (bounded by a node budget) |

The numbers stay in the same order of magnitude as the ≈24× measured amplification of an HTML tree and
the ≈2.2–2.7× of a JSON tree, which is what the bound needs to be meaningful. The alternative — the
source text's length — is explicitly rejected by `03` §6, because the amplification differs per format.

### D5 — LRU with the cap soft for the artifact currently being materialized

`OrderedDict.move_to_end` on read gives recency for free. On insertion the cache evicts from the front
until both bounds hold, but never evicts the entry being built: an artifact larger than the byte cap is
retained while it is in use, which is the "one document, one parse" guarantee. The accounting is
therefore allowed to exceed the byte cap by exactly that artifact, as `03` §6 states.

### D6 — The mutation contract is enforced by the existing copy-before-write discipline

`03` §6 makes "a cached tree MUST NOT be mutated in place" a contract for every format operator.
`htmldom.remove`, `text` (which needs the noise tags stripped) and `self` already work on a copy or hand
out handles, and XPath evaluation is read-only, so no operator code changes for this beyond documenting
it; the tests pin it as behaviour rather than as an implementation accident.

### D7 — Where the cache is observable

The run's scope is reachable from `StoryRun` (`run.scope`), and the scope exposes the materializer
(`scope.materializer`, created on first use) with its materialized bytes and artifact count. Tests read
that seam to pin eviction, the over-cap case and the release, instead of reaching into private state. No
new error code is needed: the cache has no failure mode (a missing operator dependency is still
`UP2-E1107`, decided by the operator before it materializes anything).

### D8 — The samples' domain types stay, with a host recipe to register them

The two sample bundles keep their own domain type names (`ShelfPage`, `Book`, `Author`), so a run needs a
host: `samples/*/host.py` is that host — the type registrations, a `urllib` fetch loop and the `call`
target, ~100 lines each. It doubles as the document's "host recipe", which is what `03` §5/§11 describe
in prose. One consequence had to be measured, not assumed: a step's field map produces **dictionaries**,
and a container type's constructor receives the *product's parts* (`Cls(**payload)` for a dict,
`Cls(*items)` for a list, `03` §3.2), so the books sample's `shelf_page` stays a **chain** (which yields
the list itself) and the shelf fan-out unrolls the aggregate with `py.flatten`. That is the sample's own
structure, not a kernel rule.

## Risks / Trade-offs

- **The size measures are approximations.** They are honest about being proportional measures of the
  artifact's own footprint, not RSS, and they are per format. A future format whose measure is
  misleading would need its own, which is why the measure lives with the consumer.
- **Measuring a large JSON tree costs a walk.** It happens once per materialization (a miss), against a
  parse that already walked the same text, and it is bounded by a node budget.
- **`html_to_markdown`, `csv` and YAML are not cached.** They are not materializing consumers today;
  adding a format later is one entry and one `cache.get` call, which D2 makes cheap.
