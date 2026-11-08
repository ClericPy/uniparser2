# Proposal

## Why

The stage grammar carries three inconsistencies that cost every author, human or model, more than the
characters they save:

- **Two stage shapes for the same idea**: `["css","text","h1"]` (operator / action / parameter) next to
  `["const","article"]` (operator / parameter). The second slot is a parameter for four operators and
  an action for the other seven.
- **The common case carries a placeholder**: every one of the 21 parameter-less `py` functions must
  write `""` (`["py","strip",""]`), because the arity is fixed at three.
- **Python API details leak into the surface**: `split` exposes `maxsplit`, `sort` exposes a type-coercion
  `key` and a `reverse` flag, `parse_time` exposes `lang` / `date_order` / `now` — none of them part of
  the everyday job, and `parse_time`'s `format` is silently read as `lang` when written positionally.

Also missing: `re` has no replacement action, so `\1`-style reformatting — a core regex job — is
impossible without leaving the DSL.

The everyday chain is 0 or 1 parameters wide; the surface should be that small, and richer needs should
go to `code`/`udf` rather than grow operator parameters.

## What Changes

- **One stage shape**: `[operator, action]` / `[operator, action, parameter]`, where the second slot is
  always the action for a multi-action operator and always the parameter for a single-action one, and a
  trailing empty slot is simply omitted (`["py","strip"]`, `["json"]`).
- **One parameter rule**: one value is written bare; two or more fixed parameters are a positional
  array (`["py","replace",["old","new"]]`); an object is a data map (`each`, `ctx.dict`), never a
  parameter list.
- **Trim the leaks**: drop `split.maxsplit`, replace `sort`'s `key`/`reverse` object with `sort` /
  `sort_desc` (no parameters — Python's `sorted`), and delete `parse_time` — `strptime` takes an
  explicit literal format and answers a `datetime`, which `strftime` renders back to text.
- **Name the stage's value**: `$obj` in a parameter tree is the same value `ctx.obj` reads, so a
  priority list can put a saved candidate before the live one (`["py","or",["$locals.a","$obj"]]`).
- **Add `re.sub`** with compile-time validation of every `\N` / `\g<name>` against the pattern.
- **Check `udf` parameters at compile time**: the registered signature is known, so a non-object
  parameter or an unknown keyword is a compile error instead of a runtime surprise.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `dsl-operators`: the stage grammar, the parameter shapes, and the operator surfaces named above.
- `core-evaluator`: arity and parameter binding are validated against the action's declaration, a
  trailing empty slot is legal exactly when the action's remaining parameters are optional, and `$obj`
  names the stage's incoming value.
- `chain-iteration`: `each` selects its mode by the parameter's shape (field map or one chain).
- `code-execution`: the stage is `["code", src]`, `inputs` is gone, and the sandbox's built-ins are
  `obj` and `ctx`.
- `predicates`: `or`/`and` include the incoming value, `between` is added, and `default` is removed.
- `time-parsing`: `parse_time` is deleted; `strptime` parses with an explicit literal format.
- `time-formatting`: `strftime` renders a `datetime` and rejects locale-dependent directives.

## Impact

- `core/ast.py` (stage shape), `core/compile.py` (arity, parameter classification), `core/registry.py`
  (`param_form`, arity), `core/refs.py` and `core/evaluator.py` (`$obj`), `core/export.py` (the
  `datetime` exit hint), `ops/pyops.py`, `ops/regex.py`, `ops/jsonquery.py`, `ops/udf.py`;
  `pyproject.toml` drops the `time` extra.
- Every chain in tests, samples, docs and the generated catalogue; the 74 declared pairs are regrouped.
- Stored chains: a chain written in the old shape fails to compile with a precise pointer; the storage
  format itself does not change.
- `CHANGELOG.md` with a **BREAKING** note (alpha: syntax changes bump the minor).
