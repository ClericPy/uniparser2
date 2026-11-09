"""The `public` scope and the `try` guard directive (change `public-scope-and-try`).

The three scopes read as constants / shared / private: ``globals`` is the chain's read-only
constants, ``public`` is the run's own notes (writable, never fingerprinted), ``locals`` is private
to the scope that wrote it. The guard directive is **not** an operator: it changes what the
evaluator does with the next stage's outcome, so the operators stay pure.
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
    start,
)


def run(chain: Any, value: Any = "x", *, scope: Scope | None = None) -> Outcome:
    compiled = compile_field(chain)
    return eval_field(compiled, value, scope=scope)


def compile_error(chain: Any) -> str:
    with pytest.raises(Up2Error) as info:
        compile_field(chain)
    return info.value.diagnostic.code


# ---------------------------------------------------------------- the public scope


def test_public_is_writable_and_readable() -> None:
    scope = Scope()
    assert run([["py", "const", 7], ["ctx", "set", "public.page"]], scope=scope) == Ok(7)
    assert run([["ctx", "get", "public.page"]], scope=scope) == Ok(7)


def test_public_may_be_collected_like_any_scope() -> None:
    scope = Scope(public={"page": 3})
    assert run([["ctx", "dict", {"p": "public.page"}]], scope=scope) == Ok({"p": 3})
    assert run([["ctx", "list", ["public.page"]]], scope=scope) == Ok([3])


def test_public_may_be_deleted() -> None:
    scope = Scope(public={"page": 3})
    assert run([["ctx", "del", "public.page"]], scope=scope) == Ok("x")
    assert scope.public == {}


def test_globals_stays_read_only() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["ctx", "set", "globals.page"]])
    assert info.value.diagnostic.code == "UP2-E1015"


def test_the_input_root_stays_read_only() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["ctx", "set", "in.page"]])
    assert info.value.diagnostic.code == "UP2-E1015"


def test_a_node_writes_and_the_next_node_reads() -> None:
    """The point of the scope: a value outlives the node that wrote it."""
    story = {
        "entry": "write",
        "steps": [
            {
                "name": "write",
                "body": {"_w": [["py", "const", 42], ["ctx", "set", "public.v"]]},
                "type": "dict",
            },
            {"name": "read", "body": {"v": "$public.v"}, "type": "dict"},
        ],
        "collect": "read",
    }
    assert start(story, "seed").go() == ("done", [{"v": 42}])


def test_public_is_shared_across_the_fan_out() -> None:
    """The scope is run-level, so a value written inside an element outlives the element."""
    story = {
        "entry": "fan",
        "steps": [
            {
                "name": "fan",
                "body": {
                    "rows": [
                        ["py", "const", ["a", "b"]],
                        [
                            "each",
                            {
                                "_w": [["py", "const", 1], ["ctx", "set", "public.n"]],
                                "v": "$public.n",
                            },
                        ],
                    ],
                },
                "type": "dict",
            },
        ],
        "collect": "fan",
    }
    assert start(story, "seed").go() == ("done", [{"rows": [{"v": 1}, {"v": 1}]}])


def test_public_is_not_chain_data() -> None:
    """The fingerprint covers the chain, not what a run wrote into the shared scope."""
    from uniparser2.store.fingerprint import graph_hash

    story = {
        "entry": "write",
        "steps": [
            {"name": "write", "body": {"_w": [["ctx", "set", "public.v"]]}, "type": "dict"},
        ],
        "collect": "write",
    }
    before = graph_hash(story)
    start(story, "seed").go()
    assert graph_hash(story) == before


def test_public_is_a_reserved_root() -> None:
    """A step may not be named after a root."""
    with pytest.raises(Up2Error) as info:
        start(
            {
                "entry": "public",
                "steps": [{"name": "public", "body": {"v": [["py", "const", 1]]}, "type": "dict"}],
                "collect": "public",
            }
        )
    assert info.value.diagnostic.code == "UP2-E1009"


# ---------------------------------------------------------------- the guard directive


def test_a_guarded_failure_is_skipped() -> None:
    chain = [["py", "const", "keep"], ["try", "skip"], ["py", "int"]]
    assert run(chain, "not-a-number") == Ok("keep")


def test_a_guarded_failure_breaks_the_chain() -> None:
    chain = [["py", "const", "keep"], ["try", "break"], ["py", "int"], ["py", "strip"]]
    assert run(chain, "not-a-number") == Ok("keep")


def test_a_guarded_success_disarms_the_guard() -> None:
    """The guard covers one stage: a later failure is not swallowed."""
    chain = [["py", "const", ""], ["try", "skip"], ["py", "strip"], ["py", "int"]]
    outcome = run(chain, "not-a-number")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"


def test_an_unguarded_failure_fails_the_run() -> None:
    chain = [["py", "const", "keep"], ["py", "int"]]
    outcome = run(chain, "not-a-number")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"


def test_the_raise_policy_is_the_default_behaviour() -> None:
    chain = [["py", "const", "keep"], ["try", "raise"], ["py", "int"]]
    outcome = run(chain, "not-a-number")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"


def test_two_guards_in_a_row_are_a_compile_error() -> None:
    assert compile_error([["try", "skip"], ["try", "skip"], ["py", "strip"]]) == "UP2-E1005"


def test_a_guard_at_the_end_of_a_chain_is_a_compile_error() -> None:
    assert compile_error([["py", "strip"], ["try", "skip"]]) == "UP2-E1005"


def test_an_unknown_policy_is_a_compile_error() -> None:
    assert compile_error([["try", "ignore"], ["py", "strip"]]) == "UP2-E1005"


def test_a_guard_does_not_run_as_a_stage() -> None:
    """The directive does no work: the value flows through it unchanged."""
    assert run([["py", "const", "v"], ["try", "skip"], ["py", "strip"]]) == Ok("v")
