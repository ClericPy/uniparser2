# Proposal: a run-scoped materialization cache

## Why

`03` §6 rules that a story does not materialize its input: the operator that consumes a value decides
how it becomes structure, and a **run-scoped, bounded cache** keeps that to one parse per document.
The consumption half landed with L1, the cache half did not, so every text-consuming operator builds
its own tree: twenty fields over one document parse that document twenty times. Measured on this
commit, one parse costs 48.0 ms at 2 MB and 109.6 ms at 5 MB, and twenty fields that each re-parse a
5 MB page take 1976.7 ms against 48.6 ms when one parse serves all twenty. Acceptance item 7 of `007`
§3 ("a story of 500 items × 20 fields within 3 s") is unreachable without it, which makes the cache
correctness-of-performance rather than an optimization.

## What Changes

- **A materializer in the kernel** (`core/materialize.py`): a run-scoped cache of derived artifacts,
  pure and stdlib-only, keyed by the target format plus the source value — object identity first, a
  content hash on a miss.
- **Enforced bounds**: `MAX_MATERIALIZE_BYTES` (64 MiB) accounted in **materialized** bytes and
  `MAX_MATERIALIZE_ITEMS` (8) artifacts, both with LRU eviction; one artifact larger than the byte cap
  is retained while it is in use ("one document, one parse" always holds).
- **The consumers use it**: `htmldom` (`css` / `css1`), `xmlxpath` and `jsonquery` take their artifact
  from the cache instead of building one per stage. A cached tree MUST NOT be mutated in place, so the
  operators document the copy-before-prune contract they already follow.
- **A run releases its cache**: the cache belongs to the run's evaluation scope, is inherited by every
  nested field-map / `each` scope, and goes away with the run; nothing is shared across runs.
- **Docs**: `03` §6 is marked implemented and corrected where the implementation disproved it, `001` §9
  records the landed constants, `007` §3's note records the landing, and the READMEs stop saying the
  cache is missing.

## Capabilities

### New Capabilities

- `materialization-cache`: the run-scoped cache of derived artifacts — scope and lifetime, the key,
  the two bounds and LRU eviction, the single-artifact-over-cap rule, the no-mutation contract, and the
  hit-vs-miss equality guarantee.

### Modified Capabilities

- `dsl-operators`: the text-consuming operators (`css` / `css1`, `xpath`, `json`) obtain their
  materialized artifact from the run's cache, and a cached artifact is never mutated in place.
- `core-evaluator`: the evaluation scope carries the run's cache, nested scopes share it, and it is
  released with the run; the cache adds no error code and no failure mode.

## Impact

- Kernel: new `core/materialize.py`; `core/refs.py` (`Scope` carries the cache), `core/registry.py`
  (`Call` exposes it), `core/story.py` (one scope per run), `core/limits.py` (the two constants),
  `core/__init__.py`.
- Operators: `ops/htmldom.py`, `ops/xmlxpath.py`, `ops/jsonquery.py`.
- Tests: `tests/core/test_materialize.py` (the cache contract) plus the consumers' existing suites.
- Docs: `03` §6, `001` §9, `007` §3, `README.md` / `README.zh-CN.md`.
- Dependencies: none. No error code is added, so no number is newly claimed.
