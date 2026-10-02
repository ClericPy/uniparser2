# Tasks

## 1. The action

- [x] 1.1 `ops/pyops.py`: delete the `get` entry; `getitem` accepts a mapping (by key), a sequence (by index) and a str (by character); parameter named `at`, kind `REF_OR_LITERAL`; no coercion
- [x] 1.2 Not found → `UP2-E2018` with `KeyError: 'text' — the dict has no key 'text'` / `IndexError: list index out of range` in `reason`; a parameter of the wrong type or a value that cannot be subscripted → `UP2-E2002`
- [x] 1.3 Register `UP2-E2018` in `core/errors.py`

## 2. Catalogue and tests

- [x] 2.1 `tests/ops/test_pyops.py` (41 → 40; the `get` cases become `getitem` cases, including dict keys and a computed key), `tests/ops/test_registry.py` (the pair count), conformance declarations
- [x] 2.2 `tools/demo_report.py`, `demo.py`, `docs/operator-reference.md`, and a `docs/report/up2-report.md` re-render
- [x] 2.3 Tests for every failure path: a missing key, an out-of-range index, a string index on a list, `getitem` on an integer

## 3. Stories and docs

- [x] 3.1 Rewrite `["py","get",…]` as `["py","getitem",…]` in both `samples/` stories and in `03` §11, then re-run them against the real sites
- [x] 3.2 `02` §6 and §7.1: the action's entry, the deletion of `get`, and the new runtime code
