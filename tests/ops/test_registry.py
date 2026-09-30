"""Registry and dependency probing (design doc 01 §7).

No test operator is registered here: ``up2 conformance --check`` treats the registry declarations
as the reference set, and registering one temporarily in a test would pollute it (E1107/E2004 are
driven through monkeypatch, see the runtime tests).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

import pytest

from uniparser2.core import registry
from uniparser2.core.errors import Ok, Outcome
from uniparser2.core.registry import ActionSpec, Call, Op


def test_names_include_aliases_and_canonical_names_do_not() -> None:
    assert "python" in registry.names()
    assert "py" in registry.names()
    assert "python" not in registry.canonical_names()
    assert "py" in registry.canonical_names()
    assert "jmespath" in registry.names()
    assert "jmespath" not in registry.canonical_names()


def test_declared_pairs_cover_all_l1_ops() -> None:
    pairs = registry.declared_pairs()
    ops = {op_name for op_name, _ in pairs}
    assert ops == {
        "const",
        "each",
        "css",
        "css1",
        "xpath",
        "json",
        "re",
        "py",
        "udf",
        "ctx",
        "code",
    }
    assert len(pairs) == 61
    assert len([pair for pair in pairs if pair[0] == "py"]) == 32
    assert len([pair for pair in pairs if pair[0] == "css"]) == 7
    assert len([pair for pair in pairs if pair[0] == "css1"]) == 7
    assert len([pair for pair in pairs if pair[0] == "xpath"]) == 3
    assert len([pair for pair in pairs if pair[0] == "re"]) == 3
    assert len([pair for pair in pairs if pair[0] == "ctx"]) == 4
    assert len([pair for pair in pairs if pair[0] == "json"]) == 1
    assert len([pair for pair in pairs if pair[0] == "const"]) == 1
    assert len([pair for pair in pairs if pair[0] == "each"]) == 1
    assert len([pair for pair in pairs if pair[0] == "udf"]) == 1
    assert len([pair for pair in pairs if pair[0] == "code"]) == 1
    assert ("re", "search") in pairs
    assert ("ctx", "map") in pairs
    assert ("const", "const") in pairs
    # `each` is a 2-slot operator with a single action, so its action name never appears in a chain
    # either; its argument is a field map, which the compiler compiles recursively.
    assert ("each", "each") in pairs
    # The former ``time`` operator has been folded into ``py``; the old ``json.$get`` action slot is
    # gone together with the 2-slot operator.
    assert ("py", "parse_time") in pairs
    assert ("py", "strftime") in pairs
    assert ("json", "get") in pairs
    # In-chain code has a single action ⇒ a 2-slot operator, so the action name never appears in a
    # chain.
    assert ("code", "run") in pairs
    # A dynamic action space declares contract coverage with *, not one name per function.
    assert ("udf", registry.DYNAMIC_ACTION_MARK) in pairs


def test_report_exposes_action_params_and_dependencies() -> None:
    report = {item.name: item for item in registry.report()}
    assert report["py"].arity == 3
    assert report["const"].arity == 2
    assert report["each"].arity == 2
    assert report["each"].slots == ("fields",)
    # Slot semantics are declared by the operator: a 3-slot operator always carries its action in
    # slot 2, and a 2-slot operator has no action slot at all.
    assert report["py"].action_slot == 1
    assert report["css"].action_slot == 1
    assert report["css"].slots == ("accessor", "selector")
    assert report["json"].action_slot is None
    assert report["json"].slots == ("jmespath path",)
    actions = {action.name: action for action in report["py"].actions}
    assert [param.name for param in actions["replace"].params] == ["old", "new"]
    assert actions["strip"].params == ()
    assert actions["default"].accepts_missing is True
    assert actions["strip"].accepts_missing is False


def test_report_dicts_is_json_shaped() -> None:
    payload = registry.report_dicts()
    assert payload
    first = payload[0]
    assert set(first) >= {
        "name",
        "aliases",
        "summary",
        "arity",
        "action_slot",
        "slots",
        "available",
        "actions",
    }
    assert isinstance(first["actions"], list)


def test_report_states_the_parameter_slot_shape() -> None:
    """The shape is derived from the parameters the action still has to fill."""
    report = {item.name: item for item in registry.report()}
    py_actions = {action.name: action for action in report["py"].actions}
    assert py_actions["slice"].param_form is registry.ParamForm.VALUE
    assert py_actions["split"].param_form is registry.ParamForm.NAMED
    assert py_actions["strip"].param_form is registry.ParamForm.NONE
    # The action slot provides `attr`, so only the selector is written in slot 3.
    css_actions = {action.name: action for action in report["css1"].actions}
    assert css_actions["@<attribute>"].param_form is registry.ParamForm.VALUE


def test_report_dicts_carries_the_parameter_slot_shape() -> None:
    payload = {item["name"]: item for item in registry.report_dicts()}
    actions = {action["name"]: action for action in payload["re"]["actions"]}
    assert actions["group"]["param_form"] == "named"
    assert actions["search"]["param_form"] == "value"


def test_missing_deps_detects_absent_module() -> None:
    assert registry.missing_deps(("definitely_not_installed_xyz",)) == (
        "definitely_not_installed_xyz",
    )
    assert registry.missing_deps(("json",)) == ()


def test_install_hints_map_modules_to_extras() -> None:
    assert registry.install_hints(("html_to_markdown",)) == ('uv add "uniparser2[md]"',)
    assert registry.install_hints(("unknown_pkg",)) == ("uv add unknown_pkg",)


def test_markdown_availability_is_reported() -> None:
    report = {item.name: item for item in registry.report()}
    action = {action.name: action for action in report["py"].actions}["html_to_markdown"]
    installed = not registry.missing_deps(("html_to_markdown",))
    assert action.available is installed


class _Colliding(Op):
    name = "py"
    aliases = ("__up2_test_alias__",)
    actions: ClassVar[Mapping[str, ActionSpec]] = {}

    def evaluate(self, call: Call) -> Outcome:
        del call
        return Ok(None)


def test_register_is_transactional_on_collision() -> None:
    """A duplicate name must be validated in full before anything is written.

    That way no alias can end up half-registered.
    """
    with pytest.raises(ValueError, match="already taken by"):
        registry.register(_Colliding)
    assert registry.get("__up2_test_alias__") is None
