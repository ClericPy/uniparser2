# Tasks

## 1. Grammar: slots, arity, parameters

- [x] 1.1 `core/ast.py`: a stage is `[op]`, `[op, param]` or `[op, action, param]`; a single-action
      operator is exactly 2 slots, a multi-action one 2 or 3; an explicitly empty third slot is
      `UP2-E1004`; the `const` operator no longer compiles
- [x] 1.2 `core/registry.py`: `ParamForm` tokens become `value` / `array` / `none`; an action declares
      its parameters in order; drop the `named` form and the named-or-positional acceptance
- [x] 1.3 `core/compile.py`: bind slot 3 by the action's declaration — one value, a positional array of
      exactly the declared arity, or nothing; an object is accepted only for a parameter whose kind is
      a data map (`each`, `ctx.dict`/`ctx.list`, `xpath`'s `ns`); pointers use `/0/2/<index>`
- [x] 1.4 `core/refs.py`: `obj` joins `RESERVED_ROOTS`; `$obj` names the stage value whole (a path is
      `UP2-E1006`), and reading it with no stage value is `UP2-E2001`
- [x] 1.5 `core/evaluator.py`: `resolve_params` receives the stage value so `$obj` resolves from the
      `Call`, not from a scope
- [x] 1.6 `core/errors.py`: delete `UP2-E2007` and `UP2-E2008`

## 2. Operators

- [x] 2.1 `ops/basic.py`: delete the `const` operator; `json`'s expression defaults to `@`, so
      `["json"]` answers the document and `["json","@"]` stays legal
- [x] 2.2 `ops/const` replacement: `["py","const",value]` returns the value verbatim
- [x] 2.3 `ops/ctx.py`: add the read-only `obj` root (whole value, no path); `ctx.set obj` / `ctx.del obj`
      stay `UP2-E1015`
- [x] 2.4 `ops/xmlxpath.py`: two parameters are a positional array
      (`["xpath","text",["//dc:creator",{"dc":"…"}]]`)
- [x] 2.5 `ops/udf.py`: 2 slots `["udf","f"]`; unary (the upstream value) and nullary; the registered
      signature is checked at compile time; `ctx` is no longer injected
- [x] 2.6 `ops/code.py`: `["code", src]` only (`inputs` deleted); built-ins `obj` and `ctx`; `print` is
      silent through `print_callback`; `UP2_CODE=off` disables the operator
- [x] 2.7 `ops/regex.py`: `search` takes `pattern` or `[pattern, group]`; the `group` action is removed;
      `findall` encodes Python tuples as arrays; `sub` takes `[pattern, replacement]` and validates
      every `\N` / `\g<name>` at compile time
- [x] 2.8 `ops/basic.py` (`each`): the parameter's shape selects the mode — object = field map, array =
      one chain applied to every element

## 3. `py` table

- [x] 3.1 remove `list`, `strip_tags`, `default`, `truthy`, `parse_time`; `strftime` and `strptime`
      replace the canonical-string time pair
- [x] 3.2 `bool` is Python's `bool`; `strip` takes an optional `chars`; `uniq` is `set` + order;
      `sort` / `sort_desc` take no parameters
- [x] 3.3 `or` / `and` include the incoming value as the first operand; operands may be `$` references
- [x] 3.4 add `md5` (non-security, `# noqa: S324`), `between` (half-open, numbers only)
- [x] 3.5 add `strptime`, `from_timestamp`, `to_timestamp`, `find_jsons`
- [x] 3.6 `strftime` consumes a `datetime`; locale-dependent, `%Z` and platform-specific directives stay
      compile errors, `%z` is allowed
- [x] 3.7 `core/export.py`: a `datetime` product is `UP2-E2003` with a fix naming `py.strftime`
- [x] 3.8 `pyproject.toml`: drop the `time` extra and its `all` entry

## 4. Tests

- [x] 4.1 rewrite every chain literal in `tests/` to the 2/3-slot grammar and the array parameters
- [x] 4.2 new cases: `$obj` (reorder, no path, outside a stage), `each` chain form, `re.sub` and the
      tuple-to-array `findall`, `strptime`/`strftime`/`from_timestamp`/`to_timestamp`, `find_jsons`,
      `between`, `or`/`and` with the incoming value, `udf` signature errors at compile time, the
      `datetime` export hint, `code` with no `inputs`
- [x] 4.3 `up2 conformance --check` passes with the regrouped pairs and the removed error codes

## 5. Docs and samples

- [x] 5.1 `docs/specs/02-dsl-spec-triples-and-operators.md`: every operator table and example
- [x] 5.2 `docs/specs/03-parse-chain.md`: `each`'s two modes and `$obj`
- [x] 5.3 samples, `up2-report` demo chains and README snippets
- [x] 5.4 `CHANGELOG.md`: a **BREAKING** entry (alpha: syntax change bumps the minor)

## 6. Gates

- [x] 6.1 `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`
- [x] 6.2 `uv run pytest --cov=uniparser2.core --cov-fail-under=95`
- [x] 6.3 `uv run up2 conformance --check`
- [x] 6.4 `uv run openspec validate simplify-dsl-syntax --strict`
