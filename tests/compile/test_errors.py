"""Compile-time validation: error codes checked one by one (design doc 02 §7).

Every implemented ``UP2-E1xxx`` has at least one case.
"""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import Ref, Up2Error, compile_field
from uniparser2.core import registry
from uniparser2.core.registry import ActionSpec, Kind, Op, ParamSpec


def compile_error(chain: Any, *, products: tuple[str, ...] = ()) -> str:
    with pytest.raises(Up2Error) as info:
        compile_field(chain, products=products)
    return info.value.diagnostic.code


def test_e1001_unknown_operator() -> None:
    assert compile_error([["nope", "x"]]) == "UP2-E1001"


def test_e1001_fix_lists_available_operators() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["nope", "x"]])
    assert "py" in info.value.diagnostic.allowed


def test_e1002_unknown_action() -> None:
    assert compile_error([["re", "nope", "x"]]) == "UP2-E1002"


def test_e1003_unknown_py_function() -> None:
    assert compile_error([["py", "nope", ""]]) == "UP2-E1003"


def test_e1003_offers_whitelist() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "nope", ""]])
    assert "normalize_space" in info.value.diagnostic.allowed


def test_e1004_too_many_slots() -> None:
    assert compile_error([["re", "search", "a", "b"]]) == "UP2-E1004"


def test_e1004_too_few_slots() -> None:
    """A 3-slot operator missing one slot: the error must name the arity and the slot roles."""
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "strip"]])
    assert info.value.diagnostic.code == "UP2-E1004"
    assert "py needs 3 slots, got 2" in info.value.diagnostic.message
    assert "slot2=function, slot3=params" in info.value.diagnostic.fix


def test_e1004_arity_two_rejects_third_slot() -> None:
    assert compile_error([["const", "a", "b"]]) == "UP2-E1004"


def test_e1004_non_list_stage() -> None:
    assert compile_error([{"op": "py", "action": "strip"}]) == "UP2-E1004"


def test_e1005_missing_required_param() -> None:
    # Slot 3 of a 3-slot operator must be written out; ``null`` is the "no parameters"
    # placeholder (equivalent to the missing slot of the old syntax).
    assert compile_error([["re", "search", None]]) == "UP2-E1005"


def test_e1005_unknown_named_param() -> None:
    assert compile_error([["re", "group", {"pattern": "(a)", "oops": 1}]]) == "UP2-E1005"


def test_e1005_too_many_positional_args() -> None:
    assert compile_error([["py", "replace", ["a", "b", "c"]]]) == "UP2-E1005"


def test_e1005_unsupported_directive() -> None:
    assert compile_error([["py", "strip", {"$nope": "$locals.x"}]]) == "UP2-E1005"


def test_e1005_lit_directive_needs_single_param() -> None:
    assert compile_error([["py", "replace", {"$lit": "x"}]]) == "UP2-E1005"


def test_e1005_path_must_be_text() -> None:
    assert compile_error([["ctx", "get", 1]]) == "UP2-E1005"


def test_e1006_unknown_reference_root() -> None:
    assert compile_error([["py", "urljoin", "$nope.x"]]) == "UP2-E1006"


def test_e1006_malformed_reference() -> None:
    assert compile_error([["py", "urljoin", "$"]]) == "UP2-E1006"


def test_e1006_retired_item_root_is_unknown() -> None:
    """There is no iteration variable: the current element is the input of the sub-chain."""
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "urljoin", "$item.x"]])
    assert info.value.diagnostic.code == "UP2-E1006"
    assert "item" not in info.value.diagnostic.allowed


def test_e1006_lists_allowed_roots_and_products() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "urljoin", "$nope.x"]], products=("n1",))
    assert "n1" in info.value.diagnostic.allowed
    assert "globals" in info.value.diagnostic.allowed


def test_e1006_node_product_reference_is_allowed() -> None:
    compiled = compile_field([["py", "urljoin", "$n1.url"]], products=("n1",))
    base = compiled.stages[0].params["base"]
    assert isinstance(base, Ref)
    assert base.root == "n1"


def test_e1007_ref_kind_rejects_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    """L1 has no ref-only parameter; patch ``urljoin.base`` into REF to exercise the rule."""
    py_op = registry.get("py")
    assert py_op is not None
    original = py_op.actions["urljoin"]
    patched = ActionSpec(
        original.name,
        original.summary,
        (ParamSpec("base", Kind.REF),),
        original.requires,
    )
    monkeypatch.setattr(py_op, "actions", {**py_op.actions, "urljoin": patched})
    assert compile_error([["py", "urljoin", "/a/"]]) == "UP2-E1007"


def test_e1012_too_many_steps() -> None:
    chain = [["py", "strip", ""]] * 33
    assert compile_error(chain) == "UP2-E1012"


def test_e1013_nested_quantifier() -> None:
    assert compile_error([["re", "search", "(a+)+"]]) == "UP2-E1013"


def test_e1014_cross_node_local_reference() -> None:
    assert compile_error([["py", "urljoin", "$n1._local"]], products=("n1",)) == "UP2-E1014"


def test_e1014_same_node_local_reference_is_fine() -> None:
    compiled = compile_field([["ctx", "get", "locals._x"]])
    assert compiled.stages[0].action == "get"


def test_e1015_write_globals() -> None:
    assert compile_error([["ctx", "set", "globals.x"]]) == "UP2-E1015"


def test_e1005_unsupported_directive_at_depth() -> None:
    """A `$`-prefixed single-key object is a directive at depth too; `$lit` is the only one."""
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "or", [{"$price": 1}, "x"]]])
    assert info.value.diagnostic.code == "UP2-E1005"
    assert "$lit" in info.value.diagnostic.fix


def test_e1006_fix_names_the_literal_escape() -> None:
    """Typing `$100` needs the way out, not only the list of reserved roots."""
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "default", "$100"]])
    assert info.value.diagnostic.code == "UP2-E1006"
    assert "$lit" in info.value.diagnostic.fix


def test_e1005_a_dollar_prefixed_ctx_path_is_told_to_drop_it() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["ctx", "get", "$locals.k"]])
    assert info.value.diagnostic.code == "UP2-E1005"
    assert "without `$`" in info.value.diagnostic.fix
    assert "locals.k" in info.value.diagnostic.fix


def test_e1015_a_dollar_prefixed_write_path_is_told_to_drop_it() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["ctx", "set", "$locals.k"]])
    assert info.value.diagnostic.code == "UP2-E1015"
    assert "without `$`" in info.value.diagnostic.fix
    assert "locals.k" in info.value.diagnostic.fix


def _fake_missing_deps(instance: Op, action: str) -> tuple[str, ...]:
    del instance, action
    return ("html_to_markdown",)


def test_e1107_missing_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "action_missing_deps", _fake_missing_deps)
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "html_to_markdown", ""]])
    assert info.value.diagnostic.code == "UP2-E1107"
    assert any("uniparser2[md]" in hint for hint in info.value.diagnostic.allowed)


def test_diag_rejects_unknown_code() -> None:
    from uniparser2.core.errors import diag

    # It must be assembled: a literal `UP2-E` + 4 digits in the source would be read by the
    # conformance scan as a declaration that the code is already covered.
    with pytest.raises(ValueError, match="unknown error code"):
        diag("UP2-E" + "9999", "x")


def test_every_implemented_code_is_in_table() -> None:
    from uniparser2.core.errors import CODES

    assert all(code.startswith("UP2-E") for code in CODES)
    assert "UP2-E1007" in CODES


def _pointer_of(chain: Any) -> str:
    with pytest.raises(Up2Error) as info:
        compile_field(chain)
    return info.value.diagnostic.pointer


def test_pointer_shape_is_uniform_across_operators() -> None:
    """The JSON Pointer shape of a diagnostic is uniform (a direct payoff of the uniform slot
    order; pinned here against regression).

    - **action-slot** errors (unknown enum member / function outside the allowlist) always point
      at slot 2 ⇒ ``/0/1``
    - **parameter-slot** errors always point at the specific parameter in slot 3 ⇒
      ``/0/2/<parameter name>``
    """
    assert _pointer_of([["re", "nope", "x"]]) == "/0/1"
    assert _pointer_of([["py", "nope", ""]]) == "/0/1"
    assert _pointer_of([["re", "search", "("]]) == "/0/2/pattern"
    assert _pointer_of([["re", "group", {"pattern": "a", "group": 9}]]) == "/0/2/group"
    assert _pointer_of([["ctx", "set", "globals.x"]]) == "/0/2/path"


def test_pointer_shape_for_selector_operators() -> None:
    """``css`` / ``xpath`` put the parameter in slot 3 ⇒ ``/0/2/...``.

    A selector-first form must fail immediately.
    """
    pytest.importorskip("selectolax")
    assert _pointer_of([["css", "@", "h1"]]) == "/0/1"  # `@` with no attribute: action-slot error
    assert _pointer_of([["css", "text", "!!!"]]) == "/0/2/selector"


def test_pointer_shape_for_xpath() -> None:
    pytest.importorskip("lxml")
    assert _pointer_of([["xpath", "nope", "//a"]]) == "/0/1"
    assert _pointer_of([["xpath", "text", "//dc:creator"]]) == "/0/2/expr"
