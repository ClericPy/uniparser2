"""Kernel boundaries and diagnostic branches (pushing ``core/`` coverage past the acceptance line).

Only **real error paths and diagnostic output** are tested here on purpose -- they are what users
and LLMs read, so they are worth pinning more than the happy paths (``05`` §4's "every error code
must have a case" is the same discipline).
"""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from typing import Any, ClassVar

import pytest

from uniparser2 import (
    Failed,
    Ok,
    Outcome,
    Ref,
    Scope,
    Up2Error,
    compile_field,
    dumps,
    eval_field,
    loads,
)
from uniparser2.core import registry, udfs, values
from uniparser2.core.ast import CompiledStage, Stage, parse_stage
from uniparser2.core.conformance import check
from uniparser2.core.refs import parse_path_text, parse_ref
from uniparser2.core.registry import ActionSpec, Call, Op

# ---------------------------------------------------------------- values diagnostics


def test_opaque_is_reported_as_opaque() -> None:
    class Node(values.Opaque):
        __slots__ = ()

    node = Node()
    assert values.type_name(node) == "opaque"
    assert values.preview(node) == "<opaque Node>"


def test_preview_truncates_long_values() -> None:
    text = values.preview("x" * 300, 10)
    assert text.startswith('"xxxxxxxxx') and text.endswith("...(+292)")


def test_preview_handles_unserialisable_values() -> None:
    """A host object is previewed as **type name plus repr** (03 §3.3: it may flow, never exit)."""
    assert values.preview({1, 2}) == "set {1, 2}"
    assert values.type_name({1, 2}) == "set"


def test_preview_of_a_host_object_names_its_class() -> None:
    class Response:
        def __repr__(self) -> str:
            return "<Response [200]>"

    response = Response()
    assert values.type_name(response) == "Response"
    assert values.preview(response) == "Response <Response [200]>"
    assert values.preview(response, 4).startswith("Resp...(+")
    assert values.is_json_value(response) is False


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_a_non_finite_float_is_not_a_json_value(bad: float) -> None:
    """JSON has no Infinity / NaN, so a product carrying one is not exportable."""
    from uniparser2.core.export import pack

    assert values.is_json_value(bad) is False
    assert values.is_json_value([1.0, bad]) is False
    assert values.is_json_value({"r": bad}) is False
    outcome = pack(bad)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2003"
    assert "finite" in (outcome.fix or "")


def test_a_finite_float_still_packs() -> None:
    from uniparser2.core.export import pack

    assert pack(1.5) == Ok(1.5)


# ---------------------------------------------------------------- ast shape and serialization


def test_ref_and_compiled_stage_expose_helpers() -> None:
    ref = parse_ref("$globals.base_url")
    assert str(ref) == "$globals.base_url"

    compiled = compile_field([["py", "strip"]])
    stage: CompiledStage = compiled.stages[0]
    assert stage.pointer == "/0"
    assert compiled.dumps() == '[["py","strip"]]'


def test_compile_field_accepts_already_compiled_field() -> None:
    """``compile_field`` is idempotent: an already compiled field chain must not error."""
    once = compile_field([["py", "strip"]])
    twice = compile_field(once)
    assert twice.stages == once.stages


def test_parse_stage_rejects_scalar_and_empty_chain() -> None:
    with pytest.raises(Up2Error) as scalar:
        parse_stage(5)
    assert scalar.value.diagnostic.code == "UP2-E1004"
    # `[]` is the identity, not a malformed chain: no stage is parsed and nothing is compiled.
    assert loads([]) == ()
    assert compile_field([]).stages == ()


def test_loads_rejects_stage_list_with_non_list_items() -> None:
    with pytest.raises(Up2Error) as info:
        loads([5])
    assert info.value.diagnostic.code == "UP2-E1004"


# ---------------------------------------------------------------- compile branches


def test_arity_is_checked_before_action_resolution() -> None:
    """Arity precedes action resolution: a short 3-slot stage reports E1004, not E1003/E1107."""
    with pytest.raises(Up2Error) as info:
        compile_field([["py"]])
    assert info.value.diagnostic.code == "UP2-E1004"
    assert info.value.diagnostic.pointer == "/0"


def test_lit_directive_escapes_dollar_literal() -> None:
    """``{"$lit": ...}`` keeps a ``$``-prefixed string in literal semantics (not a reference)."""
    from uniparser2.core.ast import Lit

    compiled = compile_field([["py", "urljoin", {"$lit": "$weird"}]])
    assert compiled.stages[0].params["base"] == Lit("$weird")


def test_lit_directive_escapes_inside_a_container() -> None:
    """The escape is not slot-only: a nested object must become a literal, not leak as data."""
    from uniparser2.core.ast import Lit

    in_array = compile_field([["py", "or", [{"$lit": "$a"}, "fallback"]]])
    assert in_array.stages[0].params["operands"] == [Lit("$a"), Lit("fallback")]
    in_object = compile_field([["py", "or", [{"a": {"$lit": "$k"}}]]])
    assert in_object.stages[0].params["operands"] == [{"a": Lit("$k")}]
    deep = compile_field([["py", "or", [{"a": {"b": [{"$lit": "$c"}]}}]]])
    assert deep.stages[0].params["operands"] == [{"a": {"b": [Lit("$c")]}}]


def test_an_escaped_container_keeps_its_own_dollars() -> None:
    """Quoting a literal object must not resolve anything inside it."""
    from uniparser2.core.ast import Lit

    quoted = compile_field([["py", "or", [{"$lit": {"a": "$x"}}]]])
    assert quoted.stages[0].params["operands"] == [Lit({"a": "$x"})]


def test_the_escaped_dollar_reaches_the_result() -> None:
    """The old failure was silent: the dict itself came back where the string was meant."""
    result = eval_field(compile_field([["py", "or", [{"$lit": "plain"}, "b"]]]), "")
    assert isinstance(result, Ok)
    assert result.value == "plain"


def test_ref_kind_success_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """L1 has no ref-only parameter; patch one in to cover the REF slot accepting a reference."""
    from uniparser2.core.registry import Kind, ParamSpec

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
    compiled = compile_field([["py", "urljoin", "$globals.base"]], products=())
    base = compiled.stages[0].params["base"]
    assert isinstance(base, Ref)
    assert eval_field(compiled, "page", scope=Scope(globals={"base": "https://x/"})) == Ok(
        "https://x/page"
    )


def test_lit_cannot_fill_a_ref_only_parameter(monkeypatch: pytest.MonkeyPatch) -> None:
    """A `ref` parameter has no literal branch, so the slot-level escape cannot fill it."""
    from uniparser2.core.registry import Kind, ParamSpec

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
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "urljoin", {"$lit": "x"}]])
    assert info.value.diagnostic.code == "UP2-E1007"


def test_list_valued_reference_param_descends(monkeypatch: pytest.MonkeyPatch) -> None:
    """References inside a container are resolved one by one (``_resolve_param`` list branch)."""

    outcome = eval_field(
        compile_field([["py", "or", ["$globals.x"]]]),
        "",
        scope=Scope(globals={"x": 1}),
    )
    assert outcome == Ok(1)


def test_reference_inside_list_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    def tag(value: Any, **kwargs: Any) -> Any:
        return kwargs

    monkeypatch.setattr(registry, "action_missing_deps", lambda instance, action: ())
    udfs.register_udf("up2_test_edge_tag2", tag)
    try:
        with pytest.raises(Up2Error) as info:
            compile_field([["py", "or", ["$nope.x"]]])
    finally:
        udfs.unregister_udf("up2_test_edge_tag2")
    assert info.value.diagnostic.code == "UP2-E1006"


# ---------------------------------------------------------------- refs error branches


@pytest.mark.parametrize(
    "text",
    ["$", "$globals.", "$.a", "$globals..a"],
)
def test_bad_reference_shapes_are_rejected(text: str) -> None:
    with pytest.raises(Up2Error) as info:
        parse_ref(text)
    assert info.value.diagnostic.code == "UP2-E1006"


def test_bad_path_text_is_rejected() -> None:
    with pytest.raises(Up2Error) as info:
        parse_path_text("")
    assert info.value.diagnostic.code == "UP2-E1005"
    with pytest.raises(Up2Error) as dotted:
        parse_path_text("locals..a")
    assert dotted.value.diagnostic.code == "UP2-E1005"


def test_write_text_refuses_non_writable_root() -> None:
    with pytest.raises(ValueError, match="is not a writable path"):
        Scope().write_text("globals.base", 1)


def test_delete_local_with_non_dict_intermediate_returns_false() -> None:
    scope = Scope(locals={"a": 1})
    assert scope.delete_text("locals.a.b") is False
    assert scope.locals == {"a": 1}


# ---------------------------------------------------------------- the scope lineage


def test_a_child_scope_reads_outward() -> None:
    """One iteration of ``each`` reads the calling scope's locals, including a nested path."""
    outer = Scope(locals={"nested": {"n": 1}})
    inner = outer.child()
    assert inner.read_text("locals.nested.n") == Ok(1)


def test_a_child_scope_shadows_and_does_not_write_outward() -> None:
    outer = Scope(locals={"k": "outer"})
    inner = outer.child()
    inner.write_text("locals.k", "inner")
    assert inner.read_text("locals.k") == Ok("inner")
    assert outer.read_text("locals.k") == Ok("outer")


def test_an_owned_name_does_not_fall_through() -> None:
    """When the inner scope owns the first segment, a deeper miss stays a miss."""
    outer = Scope(locals={"k": {"n": 1}})
    inner = outer.child()
    inner.write_text("locals.k", 5)
    assert isinstance(inner.read_text("locals.k.n"), Failed)


def test_the_scope_view_merges_the_chain() -> None:
    outer = Scope(locals={"a": 1, "b": 2})
    inner = outer.child()
    inner.write_text("locals.b", 3)
    assert inner.json_view()["locals"] == {"a": 1, "b": 3}


def test_a_product_root_whose_value_is_none_is_present() -> None:
    """``None`` is a value: a product table entry of ``None`` must not read as "no such root"."""
    scope = Scope(products={"n": None})
    assert scope.read(parse_ref("$n")) == Ok(None)
    missing = scope.read(parse_ref("$m"))
    assert isinstance(missing, Failed)
    assert missing.code == "UP2-E2001"


def test_a_try_directive_has_exactly_two_slots() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["try", "skip", "extra"], ["py", "strip"]])
    assert info.value.diagnostic.code == "UP2-E1004"
    assert info.value.diagnostic.pointer == "/0"


# ---------------------------------------------------------------- evaluator outcomes


def test_a_query_that_matched_nothing_flows_on() -> None:
    """A no-match is a value, so the chain continues with it."""
    chain = [["re", "search", r"\d+"], ["py", "strip"]]
    assert eval_field(compile_field(chain), "abc") == Ok("")


def test_an_input_text_over_the_cap_is_e2013(monkeypatch: pytest.MonkeyPatch) -> None:
    """The input size limit is checked before any operator sees the text (01 §9)."""
    from uniparser2.core import limits

    monkeypatch.setattr(limits, "MAX_TEXT_BYTES", 8)
    compiled = compile_field([["py", "strip"]])
    outcome = eval_field(compiled, "x" * 9)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2013"
    assert "MAX_TEXT_BYTES" in outcome.reason
    assert eval_field(compiled, "x" * 8) == Ok("x" * 8)


def test_a_field_map_entry_checks_the_same_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from uniparser2.core import limits
    from uniparser2.core.evaluator import eval_field_map

    monkeypatch.setattr(limits, "MAX_TEXT_BYTES", 4)
    outcome = eval_field_map(
        {"a": compile_field([["py", "strip"]])},
        "xxxxx",
        scope=Scope(),
        run_chain=lambda chain, value, scope: eval_field(chain, value, scope=scope),
    )
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2013"


def test_failed_short_circuits_the_rest_of_the_chain() -> None:
    """A failed stage stops the chain and is reported with its own code (never settled)."""
    # The former ``cast`` operator has been merged into ``py``: ``["py","int"]`` is its
    # equivalent spelling.
    chain = [["py", "int"], ["py", "strip"]]
    outcome = eval_field(compile_field(chain), "not-a-number")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"


def test_system_errors_are_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """System exceptions such as ``OSError`` / ``KeyboardInterrupt`` must keep propagating."""

    def boom(self: Op, call: Call) -> Outcome:
        raise OSError("disk exploded")

    from uniparser2.ops.pyops import Py

    monkeypatch.setattr(Py, "evaluate", boom)
    with pytest.raises(OSError, match="disk exploded"):
        eval_field(compile_field([["py", "strip"]]), " a ")


# ---------------------------------------------------------------- registry boundaries


def test_register_requires_name_and_non_empty_alias() -> None:
    class NoName(Op):
        actions: ClassVar[Mapping[str, ActionSpec]] = {}

        def evaluate(self, call: Call) -> Outcome:
            del call
            return Ok(None)

    with pytest.raises(ValueError, match="does not declare name"):
        registry.register(NoName)

    class EmptyAlias(NoName):
        name = "up2_test_no_alias"
        aliases = ("",)

    with pytest.raises(ValueError, match="has an empty alias"):
        registry.register(EmptyAlias)


def test_missing_deps_survives_broken_find_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(name: str) -> Any:
        raise ValueError(f"bad spec for {name}")

    monkeypatch.setattr(importlib.util, "find_spec", boom)
    assert registry.missing_deps(("whatever",)) == ("whatever",)


def test_op_missing_deps_requires_all(monkeypatch: pytest.MonkeyPatch) -> None:
    xpath = registry.get("xpath")
    assert xpath is not None
    monkeypatch.setattr(registry, "missing_deps", lambda names: tuple(names))
    assert registry.op_missing_deps(xpath) == xpath.requires


def test_action_available_helper() -> None:
    py_op = registry.get("py")
    assert py_op is not None
    assert registry.action_available(py_op, "strip") is True


def test_base_dynamic_action_summary_is_available() -> None:
    py_op = registry.get("py")
    assert py_op is not None
    assert "registered by the host" in py_op.dynamic_action_summary()


def test_register_udf_validates_arguments() -> None:
    with pytest.raises(ValueError, match="register_udf"):
        udfs.register_udf("", lambda value: value)
    # Pass a non-callable object through an Any variable: mypy/ty/pyright all accept it, so no
    # checker-specific ignore syntax is needed.
    not_callable: Any = "not-callable"
    with pytest.raises(ValueError, match="register_udf"):
        udfs.register_udf("name", not_callable)


# ---------------------------------------------------------------- conformance report


def test_report_renders_all_problem_kinds() -> None:
    report = check(
        covered_pairs=[("gone", "x")],
        covered_codes=["UP2-E1001", "UP2-E" + "9999"],
        declared_pairs=[("py", "strip")],
        declared_codes=["UP2-E1001", "UP2-E2002"],
    )
    text = report.render()
    assert "uncovered (operator, action)" in text
    assert "orphan cases" in text
    assert "error codes without cases" in text
    assert "orphan error codes" in text
    assert "FAIL" in text
    assert report.ok is False


def test_report_renders_pass() -> None:
    report = check(covered_pairs=[], covered_codes=[], declared_pairs=[], declared_codes=[])
    assert "PASS" in report.render()
    assert report.ok is True


# ---------------------------------------------------------------- serialization edge inputs


def test_dumps_accepts_raw_stage_lists() -> None:
    """``Stage`` keeps only the raw slots: ``slot1`` is the 2nd slot, ``slot2`` is the 3rd."""
    assert dumps([Stage(op="py", slot1="strip", slot2=None, length=2)]) == '[["py","strip"]]'
    assert dumps([Stage(op="py", slot1="strip", slot2="", length=3)]) == '[["py","strip",""]]'


def test_a_datetime_product_names_strftime() -> None:
    """A datetime is internal; the exit names the operator that renders it (design D14)."""
    from datetime import datetime

    from uniparser2.core.export import pack

    outcome = pack(datetime(2026, 9, 24, 15, 30))
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2003"
    assert "strftime" in outcome.fix


def test_a_nested_datetime_product_still_names_strftime() -> None:
    from datetime import datetime

    from uniparser2.core.export import pack

    outcome = pack({"when": [datetime(2026, 9, 24)]})
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2003"
    assert "strftime" in outcome.fix
