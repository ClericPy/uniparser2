"""The type registry and its ``["type", name]`` stage (design doc 03 §3).

The registry is host state: a name → constructor table, looked up when the stage runs. The
constructor is a **validator, not a container**: it receives the JSON and the run continues with the
JSON it approved. These cases pin the registry API and the shape rules; the stage's compile-time
placement is in ``tests/ops/test_typeop.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar

import pytest

from uniparser2 import Up2Error, register_type, run, type_names, unregister_type

_REGISTERED = ("Book", "Article", "Shelf", "Strict")


@dataclass
class Book:
    """A dataclass whose fields are the payload: the documented validator shape."""

    title: str
    price: str


def _article(*items: Any, **payload: Any) -> Any:
    """A constructor that accepts both product shapes (`Cls(*items)` / `Cls(**payload)`)."""
    return list(items) if items else dict(payload)


class Strict:
    """A constructor with its own message; the stage keeps its exception text."""

    SCHEMA: ClassVar[dict[str, type]] = {"title": str, "price": str}

    def __init__(self, **payload: Any) -> None:
        if set(payload) != set(self.SCHEMA):
            raise TypeError(f"Strict needs exactly {sorted(self.SCHEMA)}, got {sorted(payload)}")


@pytest.fixture(autouse=True)
def _types() -> Iterator[None]:
    for name, constructor in (
        ("Book", Book),
        ("Article", _article),
        ("Shelf", _article),
        ("Strict", Strict),
    ):
        register_type(name, constructor)
    yield
    for name in _REGISTERED:
        unregister_type(name)


def _story(chain: list[Any], type_name: str | None = None) -> dict[str, Any]:
    body = chain if type_name is None else [*chain, ["type", type_name]]
    return {"nodes": {"a": body}}


def _run(bundle: Any) -> Any:
    return run(bundle, "a")


def _run_error(bundle: Any) -> Any:
    with pytest.raises(Up2Error) as info:
        run(bundle, "a")
    return info.value.diagnostic


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
    from uniparser2 import get_type

    assert get_type("Book") is Book
    assert get_type("dict") is None
    assert get_type("NeverRegistered") is None


def test_the_names_include_the_builtins_and_the_hosts() -> None:
    names = type_names()
    assert "Book" in names
    for builtin in ("dict", "list", "str", "int", "float", "bool", "null"):
        assert builtin in names
    assert "Request" not in names
    assert "RequestBatch" not in names
    assert names == tuple(sorted(names))


def test_a_dataclass_constructs_a_product_and_the_instance_flows() -> None:
    """The stage answers the instance, so a later stage may read it (no payload substitution)."""
    bundle = _story(
        [
            ["py", "const", {"title": "T", "price": "12.00"}],
            ["type", "Book"],
            ["py", "getattr", "price"],
        ]
    )
    assert _run(bundle) == "12.00"


def test_a_constructed_instance_cannot_be_the_exit() -> None:
    """What flows may be an object; what leaves is JSON."""
    bundle = _story([["py", "const", {"title": "T", "price": "12.00"}], ["type", "Book"]])
    diagnostic = _run_error(bundle)
    assert diagnostic.code == "UP2-E2003"


def test_a_nested_registered_type_rejects_a_misshapen_record() -> None:
    bundle = _story([["py", "const", {"title": "T", "price": "P", "extra": 1}]], "Strict")
    diagnostic = _run_error(bundle)
    assert diagnostic.code == "UP2-E2019"
    assert "Strict needs exactly" in diagnostic.message
    assert diagnostic.pointer == "/nodes/a"


def test_a_missing_required_field_is_reported_by_the_constructor() -> None:
    bundle = _story([["py", "const", {"title": "T"}]], "Book")
    diagnostic = _run_error(bundle)
    assert diagnostic.code == "UP2-E2019"
    assert "missing 1 required positional argument: 'price'" in diagnostic.message


def test_a_constructor_keeps_its_own_exception_text() -> None:
    class Boom:
        def __init__(self, **payload: Any) -> None:
            raise ValueError(f"no such book: {sorted(payload)}")

    register_type("Boom", Boom)
    try:
        diagnostic = _run_error(_story([["py", "const", {"title": "T"}]], "Boom"))
    finally:
        unregister_type("Boom")
    assert diagnostic.code == "UP2-E2019"
    assert diagnostic.message == (
        "the type 'Boom' rejected the value: ValueError: no such book: ['title']"
    )


def test_a_list_product_is_built_from_its_items() -> None:
    assert _run(_story([["py", "const", ["a", "b"]]], "Shelf")) == ["a", "b"]


def test_builtin_names_need_no_registration() -> None:
    assert _run(_story([["py", "const", "2026"]], "int")) == 2026
    assert _run(_story([["py", "const", "2026"]], "null")) is None


def test_a_constructor_may_answer_its_own_json_shape() -> None:
    register_type("Padded", lambda *items: [*items, "extra"])
    try:
        assert _run(_story([["py", "const", ["a"]]], "Padded")) == ["a", "extra"]
    finally:
        unregister_type("Padded")


def test_a_host_registration_may_shadow_a_builtin_name() -> None:
    register_type("int", lambda product: len(str(product)))
    try:
        assert _run(_story([["py", "const", "2026"]], "int")) == 4
    finally:
        unregister_type("int")


def test_an_unregistered_name_fails_with_the_registered_names() -> None:
    diagnostic = _run_error(_story([["py", "const", 1]], "NoticeList"))
    assert diagnostic.code == "UP2-E1011"
    assert "NoticeList" in diagnostic.message
    assert "register_type" in diagnostic.fix


def test_a_constructor_never_carries_an_object_into_the_product() -> None:
    def digging(**payload: Any) -> Any:
        del payload
        return object()

    register_type("Digging", digging)
    try:
        diagnostic = _run_error(_story([["py", "const", {"u": 1}]], "Digging"))
    finally:
        unregister_type("Digging")
    assert diagnostic.code == "UP2-E2003"


def test_a_node_without_a_type_stage_builds_nothing() -> None:
    assert _run(_story([["py", "const", {"u": "x"}]])) == {"u": "x"}
