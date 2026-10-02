# Merge `get` into `getitem`

## Why

`py.get` (a dict key) and `py.getitem` (a list index) are one operation — Python's `__getitem__` — split
only because their parameters had different types. An author must remember which one takes a string, and
the two names read the same to anyone else. What is genuinely missing is the "not found" outcome: both
settle as `Missing` today, which the settlement-policy retirement removes.

`getattr` is *not* the same operation and stays separate: a response object is not subscriptable, so only
`getattr` reads its attributes.

## What Changes

- `py.get` is **deleted**; `py.getitem` becomes the only subscript action and follows Python semantics:
  list/tuple by index, dict by key, str by character.
- Its parameter is named `at` and becomes `Kind.REF_OR_LITERAL`, so a computed key works
  (`["py","getitem","$globals.field"]`) where a literal alone was required before; the stage form is
  unchanged (`["py","getitem",0]` / `["py","getitem","title"]`).
- **A key or index that is not there is an error, not `Missing`**: new code `UP2-E2018`, with `reason`
  carrying the exception class and the key/index — `KeyError: 'text' — the dict has no key 'text'` — plus
  the JSON Pointer to the stage.
- A parameter of the wrong type, or a value that cannot be subscripted, fails with `UP2-E2002`.
- **No coercion**: a string index on a list is an error, never converted to an integer.

## Impact

- `ops/pyops.py`: the `get` entry goes, `getitem` takes dicts as well as sequences, its parameter name and
  kind change; action count 41 → 40.
- `core/errors.py`: register `UP2-E2018`. It was first drafted as `UP2-E2006`, a number already retired
  ("regex execution timed out", `01` §9 / `02` §7.1) and a retired number is never reused.
- Tests and tooling: `tests/ops/test_pyops.py` (the whitelist size and the `get` cases),
  `tests/ops/test_registry.py` (the pair count), `tools/demo_report.py`, `demo.py`.
- Docs: `docs/operator-reference.md`, `docs/report/up2-report.md` (re-render), `02` §6, `03` §11 and every
  sample that writes `["py","get",…]` — including the two artifacts under `samples/`.
- **Behavior break for an existing story**: a chain that relied on a missing key or index settling as
  `Missing` now fails with `UP2-E2018`. The two `samples/` stories and `03` §11 are updated in the same
  change; no other caller in this repository depends on the old outcome.
