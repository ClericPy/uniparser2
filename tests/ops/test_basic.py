"""Behaviour assertions for ``const`` (design doc 02 §6.5).

Type conversion is not an operator: ``str`` / ``int`` / ``float`` / ``bool`` / ``list`` /
``from_json`` are functions in the ``py`` allowlist, and their cases live in
``tests/ops/test_pyops.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import Ok, Outcome, Up2Error, compile_field, eval_field


def run(chain: Any, value: Any, *, products: tuple[str, ...] = ()) -> Outcome:
    compiled = compile_field(chain, products=products)
    return eval_field(compiled, value)


@pytest.mark.covers("const", "const")
def test_const_produces_literal_verbatim() -> None:
    assert run([["const", "article"]], None) == Ok("article")


@pytest.mark.covers("const", "const")
def test_const_never_treats_dollar_prefix_as_reference() -> None:
    assert run([["const", "$100"]], None) == Ok("$100")


@pytest.mark.covers("const", "const")
def test_const_accepts_containers() -> None:
    assert run([["const", {"a": [1, 2]}]], None) == Ok({"a": [1, 2]})


def test_const_rejects_third_slot() -> None:
    """``const`` is a 2-slot operator: 2 slots are written, and a third one ⇒ ``UP2-E1004``.

    The arity has to be exact.
    """
    with pytest.raises(Up2Error) as info:
        compile_field([["const", "article", "extra"]])
    assert info.value.diagnostic.code == "UP2-E1004"


def test_const_missing_value_is_schema_error() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["const"]])
    assert info.value.diagnostic.code == "UP2-E1004"
