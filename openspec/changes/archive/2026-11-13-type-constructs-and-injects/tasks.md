# Tasks

## 1. `type` constructs and carries

- [x] 1.1 `ops/typeop.py`: answer `Ok(build_type(...))`, drop `_same_json` and the double `pack`
- [x] 1.2 `core/compile.py`: delete `_check_type_tail` and `TYPE_OPERATOR`; the stage is legal anywhere
- [x] 1.3 Tests: the instance reaches a later stage; a built-in still converts; the exit still refuses
      a non-JSON product; the "must be last" case now compiles

## 2. A run injects its own types

- [x] 2.1 `core/types.py`: a `ContextVar` overlay, `all_types()`, `use_types()`, and lookups that read
      the overlay first
- [x] 2.2 `core/story.py`: `run(..., types=None)`, the merged table, and `Scope(types=...)`
- [x] 2.3 `core/refs.py`: `Scope.types` carried to a child scope
- [x] 2.4 Tests: a mapping overlay, a class sequence (`__name__`), an overlay that does not leak, and
      `type_names()` reporting the effective set

## 3. Docs

- [x] 3.1 `docs/specs/003` §3.3: `type` constructs; anywhere in a chain; the exit rule
- [x] 3.2 `docs/specs/002`: the `type` row and the `run` signature
- [x] 3.3 The docstrings that still say "validator, not a container": `core/types.py`, `ops/typeop.py`,
      `core/udfs.py`, `ops/udf.py`
- [x] 3.4 `CHANGELOG.md` under the version that ships it, marked BREAKING

## 4. Gates

- [x] 4.1 `ruff format --check` / `ruff check` / `mypy`
- [x] 4.2 `pytest --cov=uniparser2.core --cov-fail-under=95`
- [x] 4.3 `up2 conformance --check` (the `(type, check)` pair and every code still asserted)
- [x] 4.4 `openspec validate --all`
