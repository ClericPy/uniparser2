"""``ctx`` operator: scope reads and writes (design docs 02 §6.8, 03 §8).

**The write side is hard-limited to locals**: writing globals or a step's product is ``UP2-E1015``.
Paths are always written as bare path literals (``locals._tmp``), with no ``$`` and no ``ctx.``
prefix. ``fields`` was a second name for ``locals`` and is retired (`rename-and-unify`).
"""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import (
    Failed,
    Ok,
    Outcome,
    Scope,
    Up2Error,
    compile_field,
    eval_field,
)


def run(chain: Any, value: Any, *, scope: Scope | None = None) -> Outcome:
    compiled = compile_field(chain)
    return eval_field(compiled, value, scope=scope)


def compile_error(chain: Any, *, products: tuple[str, ...] = ()) -> str:
    with pytest.raises(Up2Error) as info:
        compile_field(chain, products=products)
    return info.value.diagnostic.code


@pytest.mark.covers("ctx", "get")
def test_get_reads_globals_and_locals() -> None:
    scope = Scope(globals={"base": "https://x"}, locals={"_tmp": 7})
    assert run([["ctx", "get", "globals.base"]], None, scope=scope) == Ok("https://x")
    assert run([["ctx", "get", "locals._tmp"]], None, scope=scope) == Ok(7)


@pytest.mark.covers("ctx", "get")
def test_get_missing_path_is_a_failure() -> None:
    outcome = run([["ctx", "get", "locals._nope"]], None)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2001"


@pytest.mark.covers("ctx", "set")
def test_set_writes_local_and_passes_value_through() -> None:
    scope = Scope()
    assert run([["ctx", "set", "locals._raw"]], "hello", scope=scope) == Ok("hello")
    assert scope.locals == {"_raw": "hello"}


@pytest.mark.covers("ctx", "set")
def test_set_supports_nested_path() -> None:
    scope = Scope()
    assert run([["ctx", "set", "locals.a.b"]], 1, scope=scope) == Ok(1)
    assert scope.locals == {"a": {"b": 1}}


@pytest.mark.covers("ctx", "set")
def test_set_cannot_write_globals() -> None:
    assert compile_error([["ctx", "set", "globals.base"]]) == "UP2-E1015"


@pytest.mark.covers("ctx", "set")
def test_set_cannot_write_node_product() -> None:
    assert compile_error([["ctx", "set", "n1.field"]], products=("n1",)) == "UP2-E1015"


@pytest.mark.covers("ctx", "del")
def test_del_removes_local_and_passes_value_through() -> None:
    scope = Scope(locals={"_raw": 1, "keep": 2})
    assert run([["ctx", "del", "locals._raw"]], "v", scope=scope) == Ok("v")
    assert scope.locals == {"keep": 2}


@pytest.mark.covers("ctx", "del")
def test_del_nonexistent_path_is_noop() -> None:
    scope = Scope()
    assert run([["ctx", "del", "locals._nope"]], "v", scope=scope) == Ok("v")


@pytest.mark.covers("ctx", "list")
def test_list_builds_a_list_from_paths() -> None:
    scope = Scope(globals={"base": "B"}, locals={"a": 1, "b": 2})
    assert run([["ctx", "list", ["locals.a", "locals.b"]]], None, scope=scope) == Ok([1, 2])


@pytest.mark.covers("ctx", "dict")
def test_dict_builds_an_object_from_name_to_path() -> None:
    scope = Scope(globals={"base": "B"}, locals={"_t": "T"})
    chain = [["ctx", "dict", {"title": "locals._t", "base": "globals.base"}]]
    assert run(chain, None, scope=scope) == Ok({"title": "T", "base": "B"})


@pytest.mark.covers("ctx", "list")
def test_list_fails_on_a_path_that_cannot_be_read() -> None:
    """A path that does not exist is a failure (`UP2-E2001`), never an empty value."""
    chain = [["ctx", "list", ["locals._nope"]]]
    outcome = run(chain, None)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2001"


def test_list_requires_an_array_and_dict_an_object() -> None:
    assert compile_error([["ctx", "list", "locals.a"]]) == "UP2-E1005"
    assert compile_error([["ctx", "dict", ["locals.a"]]]) == "UP2-E1005"


def test_unknown_action_is_e1002() -> None:
    assert compile_error([["ctx", "nope", "locals.a"]]) == "UP2-E1002"


def test_get_rejects_non_readable_root() -> None:
    assert compile_error([["ctx", "get", "nope.a"]]) == "UP2-E1005"


def test_the_retired_fields_root_is_not_readable() -> None:
    """`fields` was a second name for `locals` and is retired: one writable root, one spelling."""
    assert compile_error([["ctx", "get", "fields.title"]]) == "UP2-E1005"


def test_the_retired_fields_root_is_not_writable() -> None:
    assert compile_error([["ctx", "set", "fields._tmp"]]) == "UP2-E1015"


def test_chain_uses_local_across_steps() -> None:
    """``ctx.set`` stores the upstream value and later stages read it back with ``ctx.get``.

    That is the only use of locals within L1 (``locals._up``).
    """
    chain = [
        ["py", "upper", ""],
        ["ctx", "set", "locals._up"],
        ["py", "lower", ""],
        ["ctx", "get", "locals._up"],
    ]
    assert run(chain, "Ab") == Ok("AB")


def test_scope_read_indexes_a_list() -> None:
    """A reference path dispatches per value kind: a sequence is read by its digit index.

    ``01``'s Q24 said a reference supports no array subscript; the story layer's host objects made
    a dotted path walk mappings, sequences and objects alike, so ``locals.a.0`` is the first
    element. A segment that is not a digit is still ``UP2-E2001``.
    """
    scope = Scope(locals={"a": [1, 2]})
    assert run([["ctx", "get", "locals.a.0"]], None, scope=scope) == Ok(1)
    outcome = run([["ctx", "get", "locals.a.first"]], None, scope=scope)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2001"
