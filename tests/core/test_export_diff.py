"""The structural comparison of the snapshot regression (`04` §7-S5, `05` §4.2).

A snapshot is an external behavioral contract, so a difference must be **structured**: the JSON
Pointer of the value that changed, what was expected and what came out -- never a text diff.
"""

from __future__ import annotations

from typing import Any

from uniparser2.core.export import ProductDifference, compare_products, render_difference


def pointers(differences: list[ProductDifference]) -> list[str]:
    return [item.pointer for item in differences]


def test_identical_products_have_no_difference() -> None:
    product: Any = {"title": "a", "items": [1, 2.5, None, True], "nested": {"x": ["y"]}}
    assert compare_products(product, product) == []
    # Same JSON written twice from different objects is still one product.
    assert (
        compare_products(
            product, {"title": "a", "items": [1, 2.5, None, True], "nested": {"x": ["y"]}}
        )
        == []
    )


def test_a_changed_value_reports_its_pointer() -> None:
    differences = compare_products(
        {"list": [{"title": "a"}, {"title": "b"}]}, {"list": [{"title": "a"}, {"title": "B"}]}
    )
    assert pointers(differences) == ["/list/1/title"]
    assert (differences[0].expected, differences[0].actual) == ("b", "B")
    assert differences[0].reason == "values differ"
    assert "/list/1/title" in render_difference(differences[0])


def test_a_type_change_names_both_types() -> None:
    differences = compare_products({"price": "3.5"}, {"price": 3.5})
    assert pointers(differences) == ["/price"]
    assert differences[0].reason == "expected str, got float"
    # bool is not int here: the comparison is by exact type, not by equality.
    assert compare_products(1, True)[0].reason == "expected int, got bool"


def test_a_missing_key_and_an_extra_key_are_both_reported() -> None:
    differences = compare_products({"a": 1}, {"b": 2})
    assert pointers(differences) == ["/a", "/b"]
    assert differences[0].reason == "key absent" and differences[0].expected == 1
    assert differences[1].reason == "not expected" and differences[1].actual == 2


def test_a_list_reports_a_short_tail_and_a_long_tail() -> None:
    short = compare_products([1, 2, 3], [1, 2])
    assert pointers(short) == ["/2"] and short[0].reason == "item absent"
    long = compare_products([1], [1, 2])
    assert pointers(long) == ["/1"] and long[0].reason == "extra item"


def test_a_container_where_a_scalar_was_expected_is_one_difference() -> None:
    differences = compare_products([{"a": 1}], [[1]])
    assert pointers(differences) == ["/0"]
    assert differences[0].reason == "expected dict, got list"
    assert render_difference(differences[0]).startswith("/0 expect ")


def test_the_pointer_starts_where_the_caller_put_it() -> None:
    assert pointers(compare_products({"a": 1}, {"a": 2}, pointer="/exit/0")) == ["/exit/0/a"]


def test_to_dict_is_json_data() -> None:
    payload = compare_products({"t": "a"}, {"t": "b"})[0].to_dict()
    assert payload["pointer"] == "/t"
    assert payload["expected"] == '"a"' and payload["actual"] == '"b"'
    assert payload["reason"] == "values differ"
