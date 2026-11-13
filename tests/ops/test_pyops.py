"""The behaviour dictionary of ``py``'s 48 allowlisted functions (design doc 02 §6.4).

Design points:
- ``CASES`` is the behaviour dictionary (at least one ``input → output`` assertion per function);
- ``COVERS_PAIRS`` is the **source-visible** declaration ``up2 conformance --check`` reads;
- ``test_cover_declarations_match_cases`` pins the two together, so "declared as covered but never
  tested" cannot happen.

A parameter-less action omits slot 3 entirely (``["py","strip"]``; design D2 of
`simplify-dsl-syntax`); an action with parameters writes them in slot 3, as one positional array
when there are two or more. The old ``time`` / ``cast`` operators were folded into this table
(D-02-14 of ``02``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
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
from uniparser2.core import registry
from uniparser2.ops import pyops

COVERS_PAIRS = (
    ("py", "const"),
    ("py", "strip"),
    ("py", "normalize_space"),
    ("py", "html_to_markdown"),
    ("py", "replace"),
    ("py", "split"),
    ("py", "join"),
    ("py", "upper"),
    ("py", "lower"),
    ("py", "slice"),
    ("py", "getitem"),
    ("py", "getattr"),
    ("py", "len"),
    ("py", "first"),
    ("py", "last"),
    ("py", "flatten"),
    ("py", "sort"),
    ("py", "sort_desc"),
    ("py", "uniq"),
    ("py", "find_jsons"),
    ("py", "filter"),
    ("py", "sleep"),
    ("py", "between"),
    ("py", "urljoin"),
    ("py", "urlsplit"),
    ("py", "b64_encode"),
    ("py", "b64_decode"),
    ("py", "sha256"),
    ("py", "md5"),
    ("py", "strptime"),
    ("py", "strftime"),
    ("py", "from_timestamp"),
    ("py", "to_timestamp"),
    ("py", "str"),
    ("py", "int"),
    ("py", "float"),
    ("py", "bool"),
    ("py", "items"),
    ("py", "from_json"),
)

WHITELIST_SIZE = 48

_SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def ok(expected: Any) -> Callable[[Outcome], bool]:
    def check(outcome: Outcome) -> bool:
        return isinstance(outcome, Ok) and outcome.value == expected

    return check


def failed(code: str) -> Callable[[Outcome], bool]:
    return lambda outcome: isinstance(outcome, Failed) and outcome.code == code


def markdown_result(outcome: Outcome) -> bool:
    """Placeholder: ``html_to_markdown``'s expectation depends on the optional dependency.

    A dedicated branch handles it.
    """
    del outcome
    return True


class _HostResponse:
    """A stand-in host object: attributes are values, methods are not."""

    __slots__ = ("status", "text")

    def __init__(self, status: int = 200, text: str = "body") -> None:
        self.status = status
        self.text = text

    def json(self) -> Any:
        return {"status": self.status}


_HOST_RESPONSE = _HostResponse(200, "body")


CASES: tuple[tuple[str, object, object, Callable[[Outcome], bool]], ...] = (
    ("const", "ignored", {"$lit": "$100"}, ok("$100")),
    ("strip", "  a \n", (), ok("a")),
    ("strip", "xxaxx", "x", ok("a")),
    ("normalize_space", " a \n\t b ", (), ok("a b")),
    ("html_to_markdown", "<b>a</b>", (), markdown_result),
    ("replace", "a-b", ["-", "+"], ok("a+b")),
    ("split", "a,b", ",", ok(["a", "b"])),
    ("join", ["a", "b"], ",", ok("a,b")),
    ("upper", "ab", (), ok("AB")),
    ("lower", "AB", (), ok("ab")),
    ("slice", "abcdef", ":3", ok("abc")),
    ("getitem", [1, 2, 3], 1, ok(2)),
    ("getitem", {"a": 1}, "a", ok(1)),
    ("getitem", "abc", -1, ok("c")),
    ("len", [1, 2], (), ok(2)),
    ("first", [1, 2], (), ok(1)),
    ("last", [1, 2], (), ok(2)),
    ("flatten", [[1], [2, 3]], (), ok([1, 2, 3])),
    ("sort", [3, 1, 2], (), ok([1, 2, 3])),
    ("sort_desc", [1, 3, 2], (), ok([3, 2, 1])),
    ("uniq", [1, 1, 2], (), ok([1, 2])),
    ("filter", [0, 1, "", "a", None], (), ok([1, "a"])),
    ("filter", [0, 1, "", "a", None], False, ok([0, "", None])),
    ("sleep", "kept", 0, ok("kept")),
    ("between", 3, [1, 5], ok(True)),
    ("const", None, {"a": [1, 2]}, ok({"a": [1, 2]})),
    ("const", None, None, ok(None)),
    ("find_jsons", 'x{"a":1}y[2,3]z', (), ok([{"a": 1}, [2, 3]])),
    ("urljoin", "b", "/a/", ok("/a/b")),
    ("urlsplit", "https://x/y?z=1", "netloc", ok("x")),
    ("b64_encode", "abc", (), ok("YWJj")),
    ("b64_decode", "YWJj", (), ok("abc")),
    ("sha256", "abc", (), ok(_SHA256_ABC)),
    ("md5", "abc", (), ok("900150983cd24fb0d6963f7d28e17f72")),
    ("strptime", "2026-09-26 10:30:00", "%Y-%m-%d %H:%M:%S", ok(datetime(2026, 9, 26, 10, 30))),
    ("strftime", datetime(2026, 9, 26, 10, 30), "%Y/%m/%d", ok("2026/09/26")),
    (
        "from_timestamp",
        0,
        (),
        ok(datetime(1970, 1, 1, tzinfo=UTC)),
    ),
    (
        "to_timestamp",
        datetime(1970, 1, 1, tzinfo=UTC),
        (),
        ok(0),
    ),
    ("str", 12, (), ok("12")),
    ("int", "42", (), ok(42)),
    ("float", "1.5", (), ok(1.5)),
    ("bool", "false", (), ok(True)),
    ("items", {"a": 1, "b": 2}, (), ok([["a", 1], ["b", 2]])),
    ("from_json", '{"a":1}', (), ok({"a": 1})),
    ("getattr", _HOST_RESPONSE, "status", ok(200)),
)


def run(chain: Any, value: Any) -> Outcome:
    return eval_field(compile_field(chain), value)


def _chain(name: str, params: Any) -> list[Any]:
    """A parameter-less action omits slot 3 entirely (design D2)."""
    return [["py", name]] if params == () else [["py", name, params]]


@pytest.mark.parametrize(
    ("name", "value", "params", "checker"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_py_behaviour_dictionary(
    name: str, value: Any, params: Any, checker: Callable[[Outcome], bool]
) -> None:
    if name == "html_to_markdown":
        assert _markdown_acceptable(value, params)
        return
    outcome = run(_chain(name, params), value)
    assert checker(outcome), outcome


def _markdown_acceptable(value: Any, params: Any) -> bool:
    """Both paths must reach a definite conclusion.

    Either the conversion succeeds (Ok), or the dependency is missing (compile-time E1107 /
    runtime E2004).
    """
    try:
        outcome = run(_chain("html_to_markdown", params), value)
    except Up2Error as exc:
        return exc.diagnostic.code == "UP2-E1107"
    if isinstance(outcome, Ok):
        return "a" in str(outcome.value)
    return isinstance(outcome, Failed) and outcome.code == "UP2-E2004"


def test_cover_declarations_match_cases() -> None:
    declared = {pair[1] for pair in COVERS_PAIRS if pair[0] == "py"}
    implemented = {case[0] for case in CASES}
    assert declared == implemented
    assert len(pyops.functions()) == WHITELIST_SIZE
    # These two tables hold the text / collection / URL / time / conversion functions. The predicate
    # actions (`==` … `in`, `or`, `and`) have their behaviour cases in ``test_predicates.py``, and
    # "no allowlisted function is left without a case anywhere" is what ``up2 conformance --check``
    # audits; what this test guards is that neither table here names a function that does not exist.
    assert implemented <= set(pyops.functions())


def test_alias_python_works() -> None:
    assert run([["python", "strip"]], " a ") == Ok("a")


@pytest.mark.parametrize(
    ("value", "checker"),
    [
        (12, failed("UP2-E2002")),
        (None, failed("UP2-E2002")),
    ],
)
def test_text_functions_reject_non_text(value: Any, checker: Callable[[Outcome], bool]) -> None:
    assert checker(run([["py", "upper"]], value))


def test_sleep_rejects_a_negative_or_non_numeric_value() -> None:
    for bad in (-1, "2", True):
        with pytest.raises(Up2Error) as info:
            compile_field([["py", "sleep", bad]])
        assert info.value.diagnostic.code == "UP2-E1005"


def test_sleep_rejects_non_finite_numbers() -> None:
    """A reference can carry NaN/Infinity even though a literal cannot."""
    for bad in (float("nan"), float("inf"), float("-inf")):
        outcome = run([["py", "sleep", "$obj"]], bad)
        assert isinstance(outcome, Failed) and outcome.code == "UP2-E2002"


def test_filter_rejects_a_non_boolean_keep() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "filter", "yes"]])
    assert info.value.diagnostic.code == "UP2-E1005"


def test_filter_needs_a_list() -> None:
    outcome = run(_chain("filter", ()), "abc")
    assert isinstance(outcome, Failed) and outcome.code == "UP2-E2002"


def test_unknown_function_is_e1003() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "definitely_not_a_function", ""]])
    assert info.value.diagnostic.code == "UP2-E1003"


def test_getitem_is_the_only_subscript_action() -> None:
    """`get` was the dict-key twin of `getitem`; the catalogue keeps one subscript action."""
    names = pyops.functions()
    assert "getitem" in names
    assert "get" not in names


def test_getitem_computed_key_is_resolved_at_runtime() -> None:
    """`ref_or_literal` means the subscript may be computed: `$globals.key` picks the key."""
    chain = [["py", "getitem", "$globals.key"]]
    compiled = compile_field(chain)
    assert eval_field(compiled, {"a": 1}, scope=Scope(globals={"key": "a"})) == Ok(1)
    missed = eval_field(compiled, {"a": 1}, scope=Scope(globals={"key": "b"}))
    assert isinstance(missed, Failed)
    assert missed.code == "UP2-E2018"


@pytest.mark.parametrize(
    ("chain", "value", "code", "reason"),
    [
        (
            [["py", "getitem", "text"]],
            {"a": 1},
            "UP2-E2018",
            "KeyError: 'text' — the dict has no key",
        ),
        ([["py", "getitem", 9]], [1], "UP2-E2018", "IndexError: list index out of range"),
        ([["py", "getitem", 5]], "ab", "UP2-E2018", "IndexError: string index out of range"),
        (
            [["py", "getitem", "0"]],
            [1, 2],
            "UP2-E2002",
            "py.getitem cannot subscript list with str",
        ),
        ([["py", "getitem", 0]], 7, "UP2-E2002", "py.getitem cannot subscript int with int"),
    ],
)
def test_getitem_failure_paths(chain: Any, value: Any, code: str, reason: str) -> None:
    """A subscript that is not there is `UP2-E2018`; a wrong type of subscript is `UP2-E2002`."""
    outcome = run(chain, value)
    assert isinstance(outcome, Failed), outcome
    assert outcome.code == code
    assert outcome.reason.startswith(reason)
    assert outcome.fix


def test_getitem_out_of_range_is_e2018() -> None:
    outcome = run([["py", "getitem", 9]], [1])
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2018"
    assert "index 9" in outcome.reason


def test_getitem_missing_key_is_e2018() -> None:
    """The dict is there, the key is not: an error naming the key, not a `Missing` outcome."""
    outcome = run([["py", "getitem", "text"]], {"a": 1})
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2018"
    assert outcome.reason == "KeyError: 'text' — the dict has no key 'text'"


def test_first_on_empty_list_yields_none() -> None:
    assert run([["py", "first"]], []) == Ok(None)


# ---------------------------------------------------------------- getattr (host objects)


def test_getattr_reads_an_attribute_of_the_value_that_flows_in() -> None:
    response = _HostResponse(200, "body")
    assert run([["py", "getattr", "status"]], response) == Ok(200)
    assert run([["py", "getattr", "text"]], response) == Ok("body")


def test_getattr_absent_attribute_is_e2002_naming_the_class() -> None:
    outcome = run([["py", "getattr", "txet"]], _HostResponse())
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"
    assert outcome.reason.startswith(
        "AttributeError: '_HostResponse' object has no attribute 'txet'"
    )


def test_getattr_reads_a_callable_attribute_as_it_is() -> None:
    """`getattr` reads an attribute, it never calls one: a bound method is a value like any other.

    Whether a method is useful is the caller's judgement -- handing one to a ``udf`` is a real use.
    """
    outcome = run([["py", "getattr", "json"]], _HostResponse())
    assert isinstance(outcome, Ok)
    assert callable(outcome.value)


def test_getattr_on_a_value_without_attributes_is_e2002() -> None:
    outcome = run([["py", "getattr", "tag"]], 5)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"
    assert outcome.reason.startswith("AttributeError: 'int' object has no attribute 'tag'")


def test_getattr_name_must_be_a_scalar() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "getattr", {"ref_or_literal": "text"}]])
    assert info.value.diagnostic.code == "UP2-E1005"


def test_getattr_accepts_a_reference_as_the_name() -> None:
    """The parameter is `ref_or_literal`, so the attribute name may be computed."""
    chain = [["py", "getattr", "$globals.attr"]]
    compiled = compile_field(chain)
    response = _HostResponse(200, "body")
    assert eval_field(compiled, response, scope=Scope(globals={"attr": "text"})) == Ok("body")


def test_getattr_on_a_selectolax_node() -> None:
    """The real case: a node's own attributes are values, `.text` is a method."""
    pytest.importorskip("selectolax")
    from uniparser2.ops.htmldom import _html_parser

    tree = _html_parser()("<div id='a'><p>hi</p></div>")
    node = tree.css_first("div")
    assert run([["py", "getattr", "tag"]], node) == Ok("div")
    assert run([["py", "getattr", "attributes"]], node) == Ok({"id": "a"})
    parent = run([["py", "getattr", "parent"]], node)
    assert isinstance(parent, Ok)
    # `.text` is a method; reading it answers the bound method, and nothing calls it.
    method = run([["py", "getattr", "text"]], node)
    assert isinstance(method, Ok)
    assert callable(method.value)


def test_the_identity_action_is_gone() -> None:
    """`py.id` was deleted with the identity stages (`03` §2): a chain reference spells identity."""
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "id", ""]])
    assert info.value.diagnostic.code == "UP2-E1003"


def test_split_empty_separator_is_failed() -> None:
    outcome = run([["py", "split", ""]], "ab")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"


def test_unknown_param_name_is_rejected() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "split", {"sep": ",", "nope": 1}]])
    assert info.value.diagnostic.code == "UP2-E1005"


def test_urlsplit_part_is_validated_at_compile_time() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "urlsplit", "nope"]])
    assert info.value.diagnostic.code == "UP2-E1005"


@pytest.mark.parametrize(
    ("chain", "pointer"),
    [
        ([["py", "urljoin", {"base": "https://example.com/news/"}]], "/0/2/base"),
        ([["py", "urljoin", []]], "/0/2/base"),
        ([["py", "slice", {"spec": "0:4"}]], "/0/2/spec"),
        ([["py", "split", {"sep": {}}]], "/0/2/sep"),
        ([["py", "getitem", {"at": {}}]], "/0/2/at"),
        ([["py", "replace", {"old": {}, "new": ""}]], "/0/2"),
        ([["py", "replace", [{}, ""]]], "/0/2/0"),
    ],
)
def test_scalar_parameter_rejects_a_container(chain: Any, pointer: str) -> None:
    """A container where the function needs a scalar fails at compile time, not at runtime."""
    with pytest.raises(Up2Error) as info:
        compile_field(chain)
    diagnostic = info.value.diagnostic
    assert diagnostic.code == "UP2-E1005"
    assert diagnostic.pointer == pointer
    assert diagnostic.fix


def test_scalar_fix_shows_the_accepted_writing() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "urljoin", {"base": "x"}]])
    assert '["py", "urljoin", "…"]' in info.value.diagnostic.fix


@pytest.mark.parametrize(
    ("chain", "pointer"),
    [
        ([["py", "urljoin", 42]], "/0/2/base"),
        ([["py", "slice", 42]], "/0/2/spec"),
        ([["py", "split", 42]], "/0/2/sep"),
        ([["py", "replace", [42, "x"]]], "/0/2/0"),
        ([["py", "getattr", 42]], "/0/2/ref_or_literal"),
    ],
)
def test_a_wrong_typed_literal_fails_at_compile_time(chain: Any, pointer: str) -> None:
    """The value is a literal, so the compiler knows evaluation would reject it."""
    with pytest.raises(Up2Error) as info:
        compile_field(chain)
    diagnostic = info.value.diagnostic
    assert diagnostic.code == "UP2-E1005"
    assert diagnostic.pointer == pointer
    assert diagnostic.fix


@pytest.mark.parametrize(
    ("chain", "pointer"),
    [
        ([["py", "slice", "bogus"]], "/0/2/spec"),
        ([["py", "strptime", "%Q"]], "/0/2/format"),
    ],
)
def test_a_string_the_runtime_cannot_parse_fails_at_compile_time(chain: Any, pointer: str) -> None:
    """Parsed here with the runtime's own parser, so the two cannot drift apart."""
    with pytest.raises(Up2Error) as info:
        compile_field(chain)
    diagnostic = info.value.diagnostic
    assert diagnostic.code == "UP2-E1005"
    assert diagnostic.pointer == pointer
    assert diagnostic.fix


def test_a_coerced_parameter_is_not_a_rejection() -> None:
    """``join.sep`` coerces its value, so a number there is legal."""
    assert run([["py", "join", 42]], ["a", "b"]) == Ok("a42b")


def test_a_reference_for_a_scalar_parameter_is_still_deferred() -> None:
    """Only a literal is decidable at compile time; `$locals.x` is checked when it is read."""
    compile_field([["py", "getitem", "$locals.k"]])


def test_a_container_fallback_compiles_and_a_failure_is_not_caught() -> None:
    """``py.default.value`` accepts any JSON value; a failed stage is not a fallback case."""
    chain = [["ctx", "get", "locals.nope"], ["py", "or", [{"a": 1}]]]
    outcome = run(chain, "hi")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2001"
    assert run([["py", "const", ""], ["py", "or", [{"a": 1}]]], "hi") == Ok({"a": 1})


def test_reference_parameter_is_not_checked_at_compile_time() -> None:
    """A reference's value is only known at runtime, so compilation must not reject it."""
    assert compile_field([["py", "urljoin", "$globals.base_url"]]) is not None
    assert compile_field([["py", "replace", ["$globals.a", ""]]]) is not None


def test_markdown_dependency_is_declared_per_action() -> None:
    report = {item.name: item for item in registry.report()}
    py_report = report["py"]
    by_name = {action.name: action for action in py_report.actions}
    assert by_name["html_to_markdown"].requires == ("html_to_markdown",)
    assert by_name["strip"].requires == ()


# ------------------------------------------------ time parsing (former time operator)


def test_strftime_renders_another_layout() -> None:
    assert run(
        [["py", "strptime", "%Y-%m-%d %H:%M:%S"], ["py", "strftime", "%Y/%m/%d"]],
        "2026-09-24 15:30:00",
    ) == Ok("2026/09/24")
    assert run([["py", "strftime", "%d.%m.%Y %H:%M"]], datetime(2026, 9, 24, 15, 30)) == Ok(
        "24.09.2026 15:30"
    )
    assert run([["py", "strftime", "100%% done"]], datetime(2026, 9, 24)) == Ok("100% done")


def test_strftime_non_text_receiver_is_type_failure() -> None:
    outcome = run([["py", "strftime", "%Y/%m/%d"]], 20260924)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


@pytest.mark.parametrize(
    "layout",
    [
        "%B",
        "%a",
        "%A",
        "%b",
        "%p",
        "%c",
        "%x",
        "%X",
        "%Z",
        "%e",
        "%k",
        "%l",
        "%G",
        "%V",
        "%s",
        "%Q",
        "100%",
    ],
)
def test_strftime_rejected_layouts(layout: str) -> None:
    """Every rejected family is a compile-time schema error, with a reason in the fix line."""
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "strftime", layout]])
    assert info.value.diagnostic.code == "UP2-E1005"
    assert info.value.diagnostic.fix


@pytest.mark.parametrize("layout", ["%Y/%m/%d", "%Y-W%W", "%H:%M:%S", "%Y%m%d%H%M%S", "100%%"])
def test_strftime_accepted_layouts(layout: str) -> None:
    compile_field([["py", "strftime", layout]])


def test_strftime_rendering_ignores_the_locale() -> None:
    """The allowlist has no locale-decided name, so the same layout renders the same text."""
    import locale

    saved = locale.setlocale(locale.LC_TIME)
    try:
        locale.setlocale(locale.LC_TIME, "C")
        under_c = run(
            [["py", "strptime", "%Y-%m-%d %H:%M:%S"], ["py", "strftime", "%Y/%m/%d %H:%M:%S"]],
            "2026-09-24 15:30:00",
        )
        try:
            locale.setlocale(locale.LC_TIME, "")
        except locale.Error:
            pytest.skip("the system locale is unavailable on this machine")
        under_system = run(
            [["py", "strptime", "%Y-%m-%d %H:%M:%S"], ["py", "strftime", "%Y/%m/%d %H:%M:%S"]],
            "2026-09-24 15:30:00",
        )
    finally:
        locale.setlocale(locale.LC_TIME, saved)
    assert under_c == under_system == Ok("2026/09/24 15:30:00")


# ------------------------------------------------ type conversion (former cast operator)


def test_py_str_uses_json_text_for_containers() -> None:
    assert run([["py", "str"]], 12) == Ok("12")
    assert run([["py", "str"]], True) == Ok("true")
    assert run([["py", "str"]], None) == Ok("")
    assert run([["py", "str"]], [1, 2]) == Ok("[1,2]")


def test_py_int_is_strict() -> None:
    assert run([["py", "int"]], "42") == Ok(42)
    assert run([["py", "int"]], 3.9) == Ok(3)
    outcome = run([["py", "int"]], "x")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"
    assert outcome.reason.startswith("py.int conversion failed: ")


def test_py_int_of_infinity_is_a_conversion_failure_not_an_operator_defect() -> None:
    """A non-finite value can arrive through a reference; it is data, not a broken operator."""
    outcome = run([["py", "int"]], float("inf"))
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"
    assert "infinity" in outcome.reason


def test_py_float_parses_text() -> None:
    assert run([["py", "float"]], "1.5") == Ok(1.5)


def test_py_from_json_parses_any_json_text() -> None:
    assert run([["py", "from_json"]], '{"a":1}') == Ok({"a": 1})


def test_py_from_json_is_strict_about_non_json_constants() -> None:
    """`NaN` / `Infinity` are not JSON, so the boundary refuses them instead of leaking a float."""
    for text in ("NaN", "Infinity", "-Infinity", '{"a": NaN}'):
        outcome = run([["py", "from_json"]], text)
        assert isinstance(outcome, Failed), text
        assert outcome.code == "UP2-E2005", text


def test_a_non_finite_timezone_is_a_type_failure() -> None:
    chain = [["py", "strptime", "%Y-%m-%d"], ["py", "to_timestamp", "$locals.tz"]]
    scope = Scope(locals={"tz": float("nan")})
    outcome = eval_field(compile_field(chain), "2026-01-01", scope=scope)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"
    assert "finite" in outcome.reason


def test_call_positional_const_answers_its_one_argument() -> None:
    """The sandbox mount uses the positional form; `const` is the one function without a value."""
    assert pyops.call_positional("const", [42], Scope()) == Ok(42)
    too_many = pyops.call_positional("const", [1, 2], Scope())
    assert isinstance(too_many, Failed)
    assert too_many.code == "UP2-E2002"


def test_py_from_json_failure_is_failed_not_exception() -> None:
    outcome = run([["py", "from_json"]], "{oops")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"


def test_strftime_renders_an_offset_for_an_aware_value() -> None:
    from datetime import timedelta, timezone

    aware = datetime(2026, 9, 24, 15, 30, tzinfo=timezone(timedelta(hours=8)))
    chain = [["py", "strftime", "%Y-%m-%dT%H:%M:%S%z"]]
    assert run(chain, aware) == Ok("2026-09-24T15:30:00+0800")
    assert run([["py", "strftime", "%z"]], datetime(2026, 9, 24)) == Ok("")


def test_timestamp_tz_rules() -> None:
    from datetime import timedelta, timezone

    plus_eight = timezone(timedelta(hours=8))
    assert run([["py", "from_timestamp", 8]], 0) == Ok(datetime(1970, 1, 1, 8, tzinfo=plus_eight))
    aware = datetime(1970, 1, 1, 8, tzinfo=plus_eight)
    assert run([["py", "to_timestamp"]], aware) == Ok(0)
    outcome = run([["py", "to_timestamp", 9]], aware)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"
    assert run([["py", "to_timestamp"]], datetime(1970, 1, 1)) == Ok(0)


def test_find_jsons_survives_an_unmatched_brace() -> None:
    """The donor implementation loops forever here; the single pass simply finds nothing."""
    assert run([["py", "find_jsons"]], '{unclosed and "a { b') == Ok([])


def test_between_is_half_open() -> None:
    assert run([["py", "between", [1, 5]]], 1) == Ok(True)
    assert run([["py", "between", [1, 5]]], 5) == Ok(False)


def test_from_timestamp_out_of_range_is_a_value_error() -> None:
    outcome = run([["py", "from_timestamp"]], 10**30)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"
    assert "milliseconds" in outcome.fix


def test_find_jsons_recovers_from_a_prose_quote() -> None:
    """An unmatched double quote in surrounding prose must not hide the JSON on later lines."""
    assert run([["py", "find_jsons"]], 'He said "hi\n{"a": 1}') == Ok([{"a": 1}])


def test_to_timestamp_floors_a_pre_epoch_fraction() -> None:
    """An aware and a naive value agree: the fraction is dropped, so both answer -1."""

    aware = datetime(1969, 12, 31, 23, 59, 59, 500000, tzinfo=UTC)
    naive = datetime(1969, 12, 31, 23, 59, 59, 500000)
    assert run([["py", "to_timestamp"]], aware) == Ok(-1)
    assert run([["py", "to_timestamp"]], naive) == Ok(-1)
