"""The type registry and the step boundary (design doc 03 §3).

A step's `type` is a **shape**: the host registers name → constructor, and the kernel builds that
constructor from the step's product at the boundary, where the product is (03 §3.2/§3.3). Three
things are pinned here: the constructor receives exactly the payload the product holds, a
constructor that refuses the product stops the **step that declared it**, and the product still
leaves as JSON — a constructor is a validator, never a container for objects.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, is_dataclass
from typing import Any, ClassVar

import pytest

from uniparser2 import (
    Up2Error,
    compile_story,
    get_type,
    register_type,
    start,
    type_names,
    unregister_type,
)

_REGISTERED = ("Book", "Article", "Shelf", "Strict", "Rewritten", "Padded")


def _article(*items: Any) -> list[Any]:
    """A list-shaped constructor: `Cls(*items)` (03 §3.2)."""
    return list(items)


class Strict:
    """A plain callable constructor: a class (or any callable) may be registered (03 §3.1).

    It validates the *shape* the product must have for this type and answers the same JSON, so it
    also pins the "a constructor is a validator" rule without needing a container at all.
    """

    SCHEMA: ClassVar[dict[str, type]] = {"title": str, "price": str}

    def __init__(self, **payload: Any) -> None:
        if set(payload) != set(self.SCHEMA):
            raise TypeError(f"Strict needs exactly {sorted(self.SCHEMA)}, got {sorted(payload)}")
        wrong = [name for name, kind in self.SCHEMA.items() if not isinstance(payload[name], kind)]
        if wrong:
            raise TypeError(f"Strict field(s) {sorted(wrong)} must be str")


@dataclass
class Book:
    """The documented example: a dataclass whose fields are the payload (03 §3.2/§11.2)."""

    title: str
    price: str


@pytest.fixture(autouse=True)
def _types() -> Iterator[None]:
    """Register the names these cases use and put the registry back afterwards."""
    register_type("Book", Book)
    register_type("Article", _article)
    register_type("Shelf", _article)
    register_type("Strict", Strict)
    yield
    for name in _REGISTERED:
        unregister_type(name)


def _story(steps: list[dict[str, Any]], *, collect_name: str | None = None) -> dict[str, Any]:
    """A bundle whose entry is the first step's name (a story declares both endpoints, `03` §2)."""
    return {
        "entry": str(steps[0]["name"]),
        "steps": steps,
        "collect": collect_name or str(steps[-1]["name"]),
    }


def _run(bundle: Any, value: Any = None) -> Any:
    return start(bundle, value).go()


def _run_error(bundle: Any, value: Any = None) -> Any:
    with pytest.raises(Up2Error) as info:
        start(bundle, value).go()
    return info.value.diagnostic


# ---------------------------------------------------------------- the registry API


def test_registering_replaces_a_name() -> None:
    register_type("Book", _article)
    assert unregister_type("Book") is True
    assert unregister_type("Book") is False


@pytest.mark.parametrize("name", ["", "  "])
def test_a_type_name_must_not_be_empty(name: str) -> None:
    with pytest.raises(ValueError, match="non-empty name"):
        register_type(name, Book)


def test_a_constructor_must_be_callable() -> None:
    not_callable: Any = "Book"
    with pytest.raises(ValueError, match="callable"):
        register_type("Book", not_callable)


def test_get_type_reports_the_host_registration_only() -> None:
    """A built-in name has no host constructor behind it; `build_type` supplies the rule."""
    assert get_type("Book") is Book
    assert get_type("dict") is None
    assert get_type("NeverRegistered") is None


def test_the_names_include_the_builtins_and_the_hosts() -> None:
    names = type_names()
    assert "Book" in names
    for builtin in ("dict", "list", "str", "Request", "RequestBatch"):
        assert builtin in names
    assert names == tuple(sorted(names))


# ---------------------------------------------------------------- the step boundary


def test_a_dataclass_validates_a_product_and_the_product_stays_json() -> None:
    """The constructor is handed `Cls(**payload)`; the run continues with the JSON (03 §3.3)."""
    bundle = _story(
        [
            {
                "name": "book",
                "body": {"title": [["const", "T"]], "price": [["const", "12.00"]]},
                "type": "Book",
            }
        ]
    )
    assert _run(bundle) == ("done", [{"title": "T", "price": "12.00"}])


def test_the_exit_product_is_json_even_when_the_constructor_returns_an_object() -> None:
    """A dataclass instance is the constructor's *input to validate*, not the product it carries."""
    bundle = _story(
        [
            {
                "name": "book",
                "body": {"title": [["const", "T"]], "price": [["const", "P"]]},
                "type": "Book",
            }
        ]
    )
    product = _run(bundle)[1][0]
    assert not is_dataclass(product)
    assert product == {"title": "T", "price": "P"}
    assert list(product) == ["title", "price"]


def test_a_nested_registered_type_rejects_a_misshapen_record() -> None:
    """A container type validates every record it carries: one bad record fails the step."""
    bundle = _story(
        [
            {
                "name": "books",
                "body": {
                    "title": [["const", "T"]],
                    "price": [["const", "P"]],
                    "extra": [["const", 1]],
                },
                "type": "Strict",
            }
        ]
    )
    diagnostic = _run_error(bundle)
    assert diagnostic.code == "UP2-E2019"
    assert diagnostic.message == (
        "the type 'Strict' rejected the step product: TypeError: Strict needs exactly "
        "['price', 'title'], got ['extra', 'price', 'title']"
    )
    assert diagnostic.pointer == "/steps/0"
    assert "shape" in diagnostic.fix


def test_a_missing_required_field_is_reported_by_the_constructor() -> None:
    """A field that must exist is enforced at the step that produced it (01 §4.2)."""
    bundle = _story([{"name": "book", "body": {"title": [["const", "T"]]}, "type": "Book"}])
    diagnostic = _run_error(bundle)
    assert diagnostic.code == "UP2-E2019"
    assert "missing 1 required positional argument: 'price'" in diagnostic.message


def test_a_constructor_keeps_its_own_exception_text() -> None:
    class Boom:
        def __init__(self, **payload: Any) -> None:
            raise ValueError(f"no such book: {sorted(payload)}")

    register_type("Boom", Boom)
    try:
        bundle = _story([{"name": "b", "body": {"title": [["const", "T"]]}, "type": "Boom"}])
        diagnostic = _run_error(bundle)
    finally:
        unregister_type("Boom")
    assert diagnostic.code == "UP2-E2019"
    assert diagnostic.message == (
        "the type 'Boom' rejected the step product: ValueError: no such book: ['title']"
    )


def test_a_list_product_is_built_from_its_items() -> None:
    """`Cls(*items)`: one registered name turns a list product into a typed collection (03 §3.2)."""
    bundle = _story([{"name": "shelf", "body": [["const", ["a", "b"]]], "type": "Shelf"}])
    assert _run(bundle) == ("done", [["a", "b"]])


def test_a_list_product_of_objects_is_json_at_the_exit() -> None:
    bundle = _story([{"name": "rows", "body": [["const", ["a", "b"]]], "type": "list"}])
    assert _run(bundle) == ("done", [["a", "b"]])


def test_a_batch_of_objects_is_json_at_the_exit() -> None:
    bundle = _story(
        [
            {
                "name": "rows",
                "body": {"items": [["const", [{"url": "a"}, {"url": "b"}]]]},
                "type": "dict",
            }
        ]
    )
    assert _run(bundle) == ("done", [{"items": [{"url": "a"}, {"url": "b"}]}])


def test_an_unregistered_name_fails_with_the_registered_names() -> None:
    bundle = _story([{"name": "a", "body": {"u": [["const", 1]]}, "type": "NoticeList"}])
    diagnostic = _run_error(bundle)
    assert diagnostic.code == "UP2-E1011"
    assert diagnostic.message == ("the step declares type 'NoticeList', which no host registered")
    assert diagnostic.allowed == type_names()
    assert "register_type" in diagnostic.fix


def test_a_constructor_never_carries_an_object_into_the_product() -> None:
    """A constructor that answers something which is not JSON fails at that step (`UP2-E2003`)."""

    def digging(**payload: Any) -> Any:
        del payload
        return object()

    register_type("Digging", digging)
    try:
        bundle = _story([{"name": "d", "body": {"u": [["const", 1]]}, "type": "Digging"}])
        diagnostic = _run_error(bundle)
    finally:
        unregister_type("Digging")
    assert diagnostic.code == "UP2-E2003"


def test_builtin_names_need_no_registration() -> None:
    """The JSON basics and the effect types are known to the kernel (03 §3.1)."""
    assert unregister_type("dict") is False
    bundle = _story([{"name": "n", "body": [["const", "2026"]], "type": "int"}])
    assert _run(bundle) == ("done", [2026])


def test_the_null_builtin_answers_nothing() -> None:
    register_type("Gone", lambda **payload: None)
    try:
        bundle = _story([{"name": "g", "body": {"u": [["const", 1]]}, "type": "Gone"}])
        assert _run(bundle) == ("done", [None])
    finally:
        unregister_type("Gone")
    bundle = _story([{"name": "n", "body": {"u": [["const", 1]]}, "type": "null"}])
    assert _run(bundle) == ("done", [None])


def test_a_constructor_may_answer_its_own_json_shape() -> None:
    """A constructor that answers JSON built from the product decides the product (`03` §3.3)."""
    register_type("Padded", lambda *items: [*items, "extra"])
    try:
        bundle = _story([{"name": "p", "body": [["const", ["a"]]], "type": "Padded"}])
        assert _run(bundle) == ("done", [["a", "extra"]])
    finally:
        unregister_type("Padded")


def test_a_host_registration_may_shadow_a_builtin_name() -> None:
    register_type("int", lambda product: len(str(product)))
    try:
        bundle = _story([{"name": "n", "body": [["const", "2026"]], "type": "int"}])
        assert _run(bundle) == ("done", [4])
    finally:
        unregister_type("int")


def test_a_step_without_a_type_builds_nothing() -> None:
    bundle = _story([{"name": "n", "body": {"u": [["const", "x"]]}}])
    assert _run(bundle) == ("done", [{"u": "x"}])


def test_compiling_a_story_does_not_need_the_registry() -> None:
    """The bundle is data and compiles without host state; only the run builds the declared type."""
    story = compile_story(
        _story([{"name": "a", "body": {"u": [["const", 1]]}, "type": "NeverRegistered"}])
    )
    assert story.steps[0].type == "NeverRegistered"
    assert _run_error(story.source).code == "UP2-E1011"
