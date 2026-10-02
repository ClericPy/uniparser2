# Tasks

## 1. The registry

- [x] 1.1 `core/errors.py`: register `UP2-E1011` (reserved by `002` §7) and the new `UP2-E2019`
- [x] 1.2 `core/types.py`: `register_type` / `unregister_type` / `get_type` / `type_names`, the built-in
  names, and `build_type` (`Cls(**payload)` for a dictionary, `Cls(*items)` for a list, `Cls(product)`
  otherwise) with `UnknownTypeError` / `TypeConstructionError`
- [x] 1.3 `core/__init__.py` and `uniparser2/__init__.py`: re-export the registry API

## 2. The step boundary

- [x] 2.1 `core/story.py`: build the declared type at the boundary, mapping `UnknownTypeError` to
  `UP2-E1011` (with `type_names()` as the allowed values) and `TypeConstructionError` to `UP2-E2019`
  (with the constructor's own text)
- [x] 2.2 `core/story.py`: keep the product JSON after the constructor ran — a dataclass/model that
  answers exactly the payload it was handed continues as that payload, anything else is `UP2-E2003`
  at the same step

## 3. Tests

- [x] 3.1 `tests/chains/test_type_registry.py`: a registered dataclass validating a product, a rejection
  (`UP2-E2019` with the constructor's text), an unregistered name (`UP2-E1011` with the allowed names), a
  list product (`Cls(*items)`), a nested rejection, and the exit product still JSON
- [x] 3.2 `tests/chains/test_story.py`: register the two names its cases declare, and assert that
  compiling a bundle does not need the registry
- [x] 3.3 `tests/cli/test_cli.py`: the story helper declares a built-in type name, because the CLI
  registers nothing
- [x] 3.4 Conformance stays green with the two codes asserted by cases

## 4. Docs

- [x] 4.1 `03` §3.1/§3.2/§3.3: the registry API, the construction table and both codes, with the
  host-side example
- [x] 4.2 `03` §9/§10 L8/§13 O1 and the `Implemented` note at the top of the note
- [x] 4.3 `002` §7/§7.1: `UP2-E1011` implemented, `UP2-E2019` added
- [x] 4.4 `001` §1.2/§4.2 and `007` §3/§5: the module list and the settled roadmap row
- [x] 4.5 Both READMEs: the status paragraph, the error-code count and a `register_type` example

## 5. Gates

- [x] 5.1 `ruff format --check` / `ruff check` / `mypy` / `pytest --cov=uniparser2.core
  --cov-fail-under=95` / `up2 conformance --check`
- [x] 5.2 The `change-linter` for every edited `.py`
- [x] 5.3 `openspec validate --strict` and archive with the `openspec-archive-change` skill
