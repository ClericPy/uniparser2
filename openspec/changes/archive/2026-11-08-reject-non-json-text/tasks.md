# Tasks

## 1. The strict text pair

- [x] 1.1 `core/values.py`: `dumps_json` (`allow_nan=False`, `ensure_ascii=False`) and `loads_json`
      (`parse_constant` rejected, `JSONDecodeError` wrapped), both `UP2-E1004`, with `subject`
- [x] 1.2 `core/ast.py`: `_dumps_lists` and `loads` delegate to the pair
- [x] 1.3 `core/errors.py`: `UP2-E1004`'s description covers the stage shape and its JSON text

## 2. The store and the sample runner

- [x] 2.1 `store/fingerprint.py`: `canonical_graph` writes strict JSON
- [x] 2.2 `store/file.py`: template and audit writes use `dumps_json`; `_load_json` and audit lines
      use `loads_json` with the path as the subject
- [x] 2.3 `store/sqlite.py`: the row read uses `loads_json`
- [x] 2.4 `cli/samples.py`: `read_expected` / `record_expected` use the pair and answer the error text
- [x] 2.5 `cli/main.py`: `_load_chain` and `_parse_json_or_text` use the pair

## 3. Tests

- [x] 3.1 `loads("not json")` is `UP2-E1004`
- [x] 3.2 publishing a graph carrying `inf` fails with `UP2-E1004` and writes no chain file
- [x] 3.3 a corrupt chain file read through `get` is `UP2-E1004` naming the file
- [x] 3.4 a snapshot carrying `Infinity` is an error; `record_expected(inf)` answers an error string
- [x] 3.5 a finite graph and a finite snapshot still round-trip

## 4. Docs and gates

- [x] 4.1 `04` §3 and §4.1: strict JSON at the store boundary
- [x] 4.2 `CHANGELOG.md` `[Unreleased]`
- [x] 4.3 `ruff format --check`, `ruff check`, `mypy`, coverage gate, `up2 conformance --check`
- [x] 4.4 `change-linter` on the changed Python files, then archive the change
