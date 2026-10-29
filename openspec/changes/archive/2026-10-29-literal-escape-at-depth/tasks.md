# Tasks

## 1. The escape at depth

- [x] 1.1 `core/compile.py`: `_resolve_param`'s dict branch reads a single-key `$`-prefixed object as
      a directive at any depth — `$lit` becomes a `Lit`, any other directive is `UP2-E1005` with the
      escape in the fix line
- [x] 1.2 Keep the kinds untouched: `FIELDS` still compiles a field map, `LITERAL` still keeps `$` as
      text, `REF` still refuses a non-reference
- [x] 1.3 Tests: the escape in a positional array and in a named object; no dict leaks downstream; an
      unsupported directive at depth fails; a literal parameter keeps `$`

## 2. Diagnostics

- [x] 2.1 `core/compile.py`: the `UP2-E1006` fix line names `{"$lit": …}`
- [x] 2.2 `ops/ctx.py`: the `UP2-E1005` (read) and `UP2-E1015` (write) fix lines say a `ctx` path is
      written bare when the path starts with `$`
- [x] 2.3 Tests: the three diagnostics

## 3. Docs

- [x] 3.1 `02` §3.3 and §4: the escape applies at any depth; the decision order states it
- [x] 3.2 `docs/operator-reference.md`: the `{"$lit": …}` note and the bare-path note on `ctx`
- [x] 3.3 `CHANGELOG.md` `[Unreleased]`

## 4. Gates

- [x] 4.1 `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`
- [x] 4.2 `uv run pytest --cov=uniparser2.core --cov-fail-under=95`
- [x] 4.3 `uv run up2 conformance --check`
- [x] 4.4 `change-linter` on the changed Python files
