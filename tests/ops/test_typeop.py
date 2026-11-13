"""The ``type`` stage: it constructs the declared type from the value (design doc 03 §3)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, is_dataclass
from functools import partial
from typing import Any, cast

import pytest

from uniparser2 import Up2Error, register_type, run, unregister_type
from uniparser2.core import registry
from uniparser2.core.types import type_names

COVERS_PAIRS = (("type", "check"),)


@dataclass
class _Article:
    url: str
    title: str
    pub_time: str = ""


def _bad_shape(**payload: Any) -> Any:
    del payload
    return {1, 2}


@pytest.fixture(autouse=True)
def _types() -> Iterator[None]:
    register_type("Article", _Article)
    register_type("BadShape", _bad_shape)
    yield
    for name in ("Article", "BadShape"):
        unregister_type(name)


def _story(chain: Any) -> dict[str, Any]:
    return {"nodes": {"a": chain}}


def _run_error(chain: Any, **kwargs: Any) -> Any:
    with pytest.raises(Up2Error) as info:
        run(_story(chain), "a", **kwargs)
    return info.value.diagnostic


def test_the_operator_is_registered() -> None:
    instance = registry.get("type")
    assert instance is not None
    assert instance.arity == 2


def test_the_stage_answers_the_constructed_value() -> None:
    """A later stage reads the instance, not the mapping it was built from."""
    assert (
        run(
            _story(
                [
                    ["py", "const", {"url": "u", "title": "t"}],
                    ["type", "Article"],
                    ["py", "getattr", "title"],
                ]
            ),
            "a",
        )
        == "t"
    )


def test_a_constructed_value_flows_mid_chain() -> None:
    """`type` is not a chain tail: the stage may be followed by another stage."""
    seen: list[Any] = []

    def peek(value: Any) -> Any:
        seen.append(value)
        return "ok"

    register_type("Peek", peek)
    try:
        assert (
            run(
                _story(
                    [
                        ["py", "const", {"url": "u", "title": "t"}],
                        ["type", "Article"],
                        ["type", "Peek"],
                    ]
                ),
                "a",
            )
            == "ok"
        )
        assert is_dataclass(seen[0])
        built = cast(_Article, seen[0])
        assert built.title == "t"
    finally:
        unregister_type("Peek")


def test_a_missing_key_is_e2019() -> None:
    diagnostic = _run_error([["py", "const", {"url": "u"}], ["type", "Article"]])
    assert diagnostic.code == "UP2-E2019"
    assert "title" in diagnostic.message


def test_an_unregistered_name_is_e1011_and_names_the_registered_ones() -> None:
    diagnostic = _run_error([["py", "const", {}], ["type", "Gone"]])
    assert diagnostic.code == "UP2-E1011"
    assert "Gone" in diagnostic.message
    assert "Article" in diagnostic.message


def test_an_unregistered_name_carries_the_registered_names_in_allowed() -> None:
    """`02` §7 / `03` §3.3: the diagnostic enumerates the substitutes, not only the mistake."""
    diagnostic = _run_error([["py", "const", {}], ["type", "Gone"]])
    assert "Article" in diagnostic.allowed
    assert "int" in diagnostic.allowed
    assert list(diagnostic.allowed) == sorted(diagnostic.allowed)
    assert diagnostic.to_dict()["allowed"] == list(diagnostic.allowed)


def test_the_allowed_names_include_the_run_overlay() -> None:
    @dataclass
    class OnlyHere:
        pass

    diagnostic = _run_error([["py", "const", {}], ["type", "Gone"]], types=[OnlyHere])
    assert "OnlyHere" in diagnostic.allowed


def test_a_non_json_answer_is_carried_as_it_is() -> None:
    """The stage carries what the constructor answered, and nothing checks it afterwards."""
    assert run(_story([["py", "const", {"url": "u"}], ["type", "BadShape"]]), "a") == {1, 2}


def test_a_container_answer_is_the_product() -> None:
    assert isinstance(
        run(_story([["py", "const", {"url": "u", "title": "t"}], ["type", "Article"]]), "a"),
        _Article,
    )


def test_a_builtin_conversion_failure_is_e2019() -> None:
    """A built-in scalar name is a constructor too: its refusal is a coded value rejection."""
    diagnostic = _run_error([["py", "const", "abc"], ["type", "int"]])
    assert diagnostic.code == "UP2-E2019"
    assert "invalid literal for int()" in diagnostic.message


@dataclass
class _Pair:
    first: int
    second: int


@dataclass
class _Slug:
    text: str


def test_a_dataclass_is_built_from_a_list() -> None:
    register_type("Pair", _Pair)
    try:
        assert (
            run(
                _story([["py", "const", [1, 2]], ["type", "Pair"], ["py", "getattr", "second"]]),
                "a",
            )
            == 2
        )
    finally:
        unregister_type("Pair")


def test_a_dataclass_is_built_from_a_scalar() -> None:
    register_type("Slug", _Slug)
    try:
        assert (
            run(
                _story([["py", "const", "hello"], ["type", "Slug"], ["py", "getattr", "text"]]),
                "a",
            )
            == "hello"
        )
    finally:
        unregister_type("Slug")


# ---------------------------------------------------------------- a run's own table


def test_a_run_injects_types_by_name() -> None:
    """The registry is host state; a run may carry its own table instead of registering."""
    chain = [["py", "const", {"url": "u", "title": "t"}], ["type", "Article"]]
    unregister_type("Article")
    try:
        diagnostic = _run_error(chain)
        assert diagnostic.code == "UP2-E1011"
        assert (
            run(
                _story([*chain, ["py", "getattr", "title"]]),
                "a",
                types={"Article": _Article},
            )
            == "t"
        )
    finally:
        register_type("Article", _Article)


def test_a_sequence_of_classes_is_named_by_its_own_name() -> None:
    @dataclass
    class Invoice:
        number: str

    chain = [["py", "const", {"number": "INV-1"}], ["type", "Invoice"], ["py", "getattr", "number"]]
    assert run(_story(chain), "a", types=[Invoice]) == "INV-1"


def test_a_sequence_item_without_a_name_is_a_value_error() -> None:
    """A callable with no ``__name__`` (a partial, say) has nothing to register under."""
    chain = [["py", "const", {"number": "INV-1"}], ["type", "Invoice"]]
    with pytest.raises(ValueError) as excinfo:
        run(_story(chain), "a", types=[partial(int)])
    assert "__name__" in str(excinfo.value)


def test_a_run_overlay_does_not_leak_into_the_process() -> None:
    @dataclass
    class Overlay:
        number: str

    chain = [
        ["py", "const", {"number": "INV-1"}],
        ["type", "Overlay"],
        ["py", "getattr", "number"],
    ]
    assert "Overlay" not in type_names()
    assert run(_story(chain), "a", types=[Overlay]) == "INV-1"
    assert _run_error(chain).code == "UP2-E1011"


def test_the_effective_names_include_the_run_overlay() -> None:
    @dataclass
    class OnlyHere:
        pass

    assert "OnlyHere" not in type_names()
    assert "OnlyHere" in type_names({"OnlyHere": OnlyHere})
