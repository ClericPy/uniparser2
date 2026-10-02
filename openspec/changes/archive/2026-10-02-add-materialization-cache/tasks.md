# Tasks

## 1. The cache in the kernel

- [x] 1.1 `core/limits.py`: declare `MAX_MATERIALIZE_BYTES` (64 MiB) and `MAX_MATERIALIZE_ITEMS` (8)
- [x] 1.2 `core/materialize.py`: the `Materializer` — entry shape, `(format, source)` key with identity
  first and a content hash on a miss, materialized-byte accounting, LRU eviction under both bounds, the
  over-cap artifact retained while in use, and the observable `bytes` / `__len__`
- [x] 1.3 `core/refs.py`: `Scope` creates the run's cache lazily and `Scope.child()` shares it
- [x] 1.4 `core/registry.py`: `Call` carries the run's cache
- [x] 1.5 `core/story.py`: one scope for the run, its `step_input` re-pointed per step, reachable from
  the run
- [x] 1.6 `core/__init__.py` and `uniparser2/__init__.py`: export the materializer where a host needs it

## 2. The consumers use the cache

- [x] 2.1 `ops/htmldom.py`: the engine comes from the cache; `parse` measures the document, and no
  consumer mutates a cached document
- [x] 2.2 `ops/xmlxpath.py`: the XML document is materialized through the cache
- [x] 2.3 `ops/jsonquery.py`: JSON text is parsed through the cache
- [x] 2.4 `ops/*`: confirm no other operator builds a tree per stage

## 3. Tests

- [x] 3.1 `tests/core/test_materialize.py`: hit-vs-miss equality, the key (identity and equal text), the
  format split, item-bound and byte-bound eviction, recency, the over-cap artifact in use, release with
  the scope, and the accounting
- [x] 3.2 the consumers' suites: two stages over one document materialize once, a pruned document is
  still intact for the next stage, one document as two formats
- [x] 3.3 **no timing case**: a wall-clock assertion over a parse is either flaky on a loaded machine or
  so loose that it proves nothing; the cache promises the *accounting*, and that is what the cases assert

## 4. Samples keep their domain types

- [x] 4.1 restore `ShelfPage` / `Book` and `Author` in the two `samples/*/site.json` stories
- [x] 4.2 one committed host recipe per sample (`samples/*/host.py`): register the types, run the story
  through `core.story` with a stdlib `urllib` fetch loop, print the exit product
- [x] 4.3 run both samples through those scripts against the live sites and record the output
- [x] 4.4 `up2 lint` still passes on both stories

## 5. Docs

- [x] 5.1 `03` §6: mark implemented and correct what the implementation disproved
- [x] 5.2 `001` §9: the two constants are implemented
- [x] 5.3 `007` §3: the note records the landing
- [x] 5.4 README.md / README.zh-CN.md: the cache is no longer listed as missing

## 6. Gates

- [x] 6.1 `ruff format --check` / `ruff check` / `mypy` / `pytest --cov=uniparser2.core
  --cov-fail-under=95` / `up2 conformance --check`
- [x] 6.2 the `change-linter` for every edited `.py`
- [x] 6.3 `openspec validate --strict` and archive with the `openspec-archive-change` skill
