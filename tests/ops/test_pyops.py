"""The behaviour dictionary of ``py``'s 31 allowlisted functions (design doc 02 §6.4).

Design points:
- ``CASES`` is the behaviour dictionary (at least one ``input → output`` assertion per function);
- ``COVERS_PAIRS`` is the **source-visible** declaration ``up2 conformance --check`` reads;
- ``test_cover_declarations_match_cases`` pins the two together, so "declared as covered but never
  tested" cannot happen.

Two families used to be operators of their own and are now folded into this table (D-02-14 of
``02``):

- ``parse_time`` (the former ``time`` operator): the cases were moved over from the deleted
  ``tests/ops/test_timeparse.py``, including the three dateparser stand-in branches (missing
  dependency ``E2008`` / returns ``None`` / raises);
- ``str`` / ``int`` / ``float`` / ``bool`` / ``list`` / ``from_json`` (the former ``cast``
  operator): the cases were moved over from the ``cast`` assertions in ``tests/ops/test_basic.py``.

A stage always writes all 3 slots: ``["py", function, params]``, and a zero-parameter action writes
``""`` in slot 3 (the arity is exact).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest

from uniparser2 import (
    Failed,
    Missing,
    Ok,
    Outcome,
    Policy,
    Scope,
    Up2Error,
    compile_field,
    eval_field,
)
from uniparser2.core import registry
from uniparser2.ops import pyops

COVERS_PAIRS = (
    ("py", "strip"),
    ("py", "strip_tags"),
    ("py", "normalize_space"),
    ("py", "html_to_markdown"),
    ("py", "replace"),
    ("py", "split"),
    ("py", "join"),
    ("py", "upper"),
    ("py", "lower"),
    ("py", "slice"),
    ("py", "getitem"),
    ("py", "get"),
    ("py", "len"),
    ("py", "first"),
    ("py", "last"),
    ("py", "flatten"),
    ("py", "sort"),
    ("py", "uniq"),
    ("py", "urljoin"),
    ("py", "urlsplit"),
    ("py", "default"),
    ("py", "b64_encode"),
    ("py", "b64_decode"),
    ("py", "sha256"),
    ("py", "parse_time"),
    ("py", "strftime"),
    ("py", "str"),
    ("py", "int"),
    ("py", "float"),
    ("py", "bool"),
    ("py", "list"),
    ("py", "from_json"),
)

WHITELIST_SIZE = 32

_SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def ok(expected: Any) -> Callable[[Outcome], bool]:
    def check(outcome: Outcome) -> bool:
        return isinstance(outcome, Ok) and outcome.value == expected

    return check


def missing() -> Callable[[Outcome], bool]:
    return lambda outcome: isinstance(outcome, Missing)


def failed(code: str) -> Callable[[Outcome], bool]:
    return lambda outcome: isinstance(outcome, Failed) and outcome.code == code


def markdown_result(outcome: Outcome) -> bool:
    """Placeholder: ``html_to_markdown``'s expectation depends on the optional dependency.

    A dedicated branch handles it.
    """
    del outcome
    return True


CASES: tuple[tuple[str, object, object, Callable[[Outcome], bool]], ...] = (
    ("strip", "  a \n", (), ok("a")),
    ("strip_tags", "<b>a</b>c", (), ok("ac")),
    ("normalize_space", " a \n\t b ", (), ok("a b")),
    ("html_to_markdown", "<b>a</b>", (), markdown_result),
    ("replace", "a-b", ["-", "+"], ok("a+b")),
    ("split", "a,b", ",", ok(["a", "b"])),
    ("join", ["a", "b"], ",", ok("a,b")),
    ("upper", "ab", (), ok("AB")),
    ("lower", "AB", (), ok("ab")),
    ("slice", "abcdef", ":3", ok("abc")),
    ("getitem", [1, 2, 3], 1, ok(2)),
    ("get", {"a": 1}, "a", ok(1)),
    ("len", [1, 2], (), ok(2)),
    ("first", [1, 2], (), ok(1)),
    ("last", [1, 2], (), ok(2)),
    ("flatten", [[1], [2, 3]], (), ok([1, 2, 3])),
    ("sort", [3, 1, 2], {"key": "int"}, ok([1, 2, 3])),
    ("uniq", [1, 1, 2], (), ok([1, 2])),
    ("urljoin", "b", "/a/", ok("/a/b")),
    ("urlsplit", "https://x/y?z=1", "netloc", ok("x")),
    ("default", "", "fallback", ok("fallback")),
    ("b64_encode", "abc", (), ok("YWJj")),
    ("b64_decode", "YWJj", (), ok("abc")),
    ("sha256", "abc", (), ok(_SHA256_ABC)),
    ("parse_time", "2026-09-26 10:30:00", (), ok("2026-09-26 10:30:00")),
    ("strftime", "2026-09-26 10:30:00", "%Y/%m/%d", ok("2026/09/26")),
    ("str", 12, (), ok("12")),
    ("int", "42", (), ok(42)),
    ("float", "1.5", (), ok(1.5)),
    ("bool", "false", (), ok(False)),
    ("list", "[1,2]", (), ok([1, 2])),
    ("from_json", '{"a":1}', (), ok({"a": 1})),
)


def run(chain: Any, value: Any) -> Outcome:
    return eval_field(compile_field(chain), value, policy=Policy(on_missing="drop"))


def _chain(name: str, params: Any) -> list[Any]:
    """A zero-parameter action writes ``""`` in slot 3: ``py``'s arity is exactly 3.

    Anything else reports ``UP2-E1004``.
    """
    return [["py", name, "" if params == () else params]]


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
    assert len(pyops.functions()) == WHITELIST_SIZE
    assert declared == implemented == set(pyops.functions())


def test_alias_python_works() -> None:
    assert run([["python", "strip", ""]], " a ") == Ok("a")


@pytest.mark.parametrize(
    ("value", "checker"),
    [
        (12, failed("UP2-E2002")),
        (None, failed("UP2-E2002")),
    ],
)
def test_text_functions_reject_non_text(value: Any, checker: Callable[[Outcome], bool]) -> None:
    assert checker(run([["py", "upper", ""]], value))


def test_unknown_function_is_e1003() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "definitely_not_a_function", ""]])
    assert info.value.diagnostic.code == "UP2-E1003"


def test_default_swallows_missing() -> None:
    """``py.default`` is the only action that can catch ``MISSING`` (``accepts_missing``)."""
    chain = [["re", "search", r"\d+"], ["py", "default", "none"]]
    compiled = compile_field(chain)
    assert eval_field(compiled, "abc", policy=Policy(on_missing="drop")) == Ok("none")


def test_default_keeps_present_value() -> None:
    assert run([["py", "default", "none"]], "present") == Ok("present")


def test_getitem_out_of_range_is_missing() -> None:
    assert isinstance(run([["py", "getitem", 9]], [1]), Missing)


def test_get_missing_key_is_missing() -> None:
    assert isinstance(run([["py", "get", "z"]], {"a": 1}), Missing)


def test_first_on_empty_list_is_missing() -> None:
    assert isinstance(run([["py", "first", ""]], []), Missing)


def test_split_empty_separator_is_failed() -> None:
    outcome = run([["py", "split", ""]], "ab")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"


def test_zero_param_action_accepts_empty_placeholder() -> None:
    """Draft `04` writes "no parameters" as `["py","strip",""]`, and that must stay compatible."""
    assert run([["py", "strip", ""]], " a ") == Ok("a")


def test_param_on_zero_param_action_is_rejected() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "strip", "oops"]])
    assert info.value.diagnostic.code == "UP2-E1005"


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
        ([["py", "split", {"sep": ",", "maxsplit": {}}]], "/0/2/maxsplit"),
        ([["py", "getitem", {"index": {}}]], "/0/2/index"),
        ([["py", "get", {"key": {}}]], "/0/2/key"),
        ([["py", "replace", {"old": {}, "new": ""}]], "/0/2/old"),
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


def test_sort_key_enum_is_validated_at_compile_time() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "sort", {"key": {}}]])
    diagnostic = info.value.diagnostic
    assert diagnostic.code == "UP2-E1005"
    assert diagnostic.pointer == "/0/2/key"


def test_container_value_for_an_any_typed_parameter_still_compiles() -> None:
    """``py.default.value`` accepts any JSON value: a container is a value there, not a binding."""
    chain = [["ctx", "get", "locals.nope"], ["py", "default", {"a": 1}]]
    assert run(chain, "hi") == Ok({"a": 1})


def test_named_form_of_a_multi_parameter_action_is_unaffected() -> None:
    assert run([["py", "split", {"sep": ",", "maxsplit": 1}]], "a,b,c") == Ok(["a", "b,c"])


def test_reference_parameter_is_not_checked_at_compile_time() -> None:
    """A reference's value is only known at runtime, so compilation must not reject it."""
    assert compile_field([["py", "urljoin", "$globals.base_url"]]) is not None
    assert compile_field([["py", "replace", {"old": "$globals.a", "new": ""}]]) is not None


def test_markdown_dependency_is_declared_per_action() -> None:
    report = {item.name: item for item in registry.report()}
    py_report = report["py"]
    by_name = {action.name: action for action in py_report.actions}
    assert by_name["html_to_markdown"].requires == ("html_to_markdown",)
    assert by_name["strip"].requires == ()


# ------------------------------------------------ time parsing (former time operator)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-09-26 10:30:00", "2026-09-26 10:30:00"),
        ("2026-09-26T10:30:00", "2026-09-26 10:30:00"),
        ("2026-09-26 10:30", "2026-09-26 10:30:00"),
        ("2026-09-26", "2026-09-26 00:00:00"),
        ("2026/09/26", "2026-09-26 00:00:00"),
        ("2026.09.26", "2026-09-26 00:00:00"),
        # The two rows below spell their CJK date units as escapes on purpose: those literal
        # characters are part of the format ``py.parse_time`` must match, and this file stays ASCII.
        ("2026\u5e749\u670826\u65e5", "2026-09-26 00:00:00"),
        ("2026\u5e749\u670826\u65e5 10:30", "2026-09-26 10:30:00"),
        ("20260926", "2026-09-26 00:00:00"),
        ("26/09/2026", "2026-09-26 00:00:00"),
        # Zone-bearing shapes: the two canonical feed timestamps (RSS 2.0 pubDate is RFC 822,
        # Atom updated is ISO 8601 with a zone). The offset is consumed, never applied, so every
        # row renders the same wall clock it wrote.
        ("2026-09-26T10:30:00Z", "2026-09-26 10:30:00"),
        ("2026-09-26T10:30:00+08:00", "2026-09-26 10:30:00"),
        ("2026-09-26T10:30:00+0800", "2026-09-26 10:30:00"),
        ("2026-09-26T10:30:00.000+08:00", "2026-09-26 10:30:00"),
        ("2026-09-26 10:30:00 +0800", "2026-09-26 10:30:00"),
        ("Sat, 26 Sep 2026 10:30:00 +0800", "2026-09-26 10:30:00"),
        ("Sat, 26 Sep 2026 10:30:00 GMT", "2026-09-26 10:30:00"),
    ],
)
def test_parse_time_stdlib_format_table(text: str, expected: str) -> None:
    assert run([["py", "parse_time", ""]], text) == Ok(expected)


def test_parse_time_offset_is_consumed_not_applied() -> None:
    """A zone in the input must not shift the result: the wall clock is what comes back."""
    chain = [["py", "parse_time", ""]]
    assert run(chain, "2026-09-26T10:30:00Z") == Ok("2026-09-26 10:30:00")
    assert run(chain, "2026-09-26T10:30:00+08:00") == Ok("2026-09-26 10:30:00")


def test_parse_time_zone_bearing_shapes_agree_with_the_zone_less_shape() -> None:
    chain = [["py", "parse_time", ""]]
    texts = ("2026-09-26T10:30:00", "2026-09-26T10:30:00Z", "2026-09-26T10:30:00+00:00")
    assert {run(chain, text) for text in texts} == {Ok("2026-09-26 10:30:00")}


def test_parse_time_whitespace_is_trimmed() -> None:
    assert run([["py", "parse_time", ""]], "  2026-09-26  ") == Ok("2026-09-26 00:00:00")
    assert run([["py", "parse_time", ""]], "  2026-09-26T10:30:00Z  ") == Ok("2026-09-26 10:30:00")


def test_parse_time_explicit_format_param() -> None:
    chain = [["py", "parse_time", {"format": "%d.%m.%Y %H:%M"}]]
    assert run(chain, "26.09.2026 08:05") == Ok("2026-09-26 08:05:00")


def test_parse_time_explicit_format_mismatch_is_e2007() -> None:
    chain = [["py", "parse_time", {"format": "%Y-%m-%d"}]]
    outcome = run(chain, "26/09/2026")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2007"
    assert "format" in outcome.fix


def test_parse_time_unparsable_text_is_e2007() -> None:
    """With the engine installed, text nothing can read stays a coded failure."""
    pytest.importorskip("dateparser")
    outcome = run([["py", "parse_time", ""]], "not a timestamp at all")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2007"
    assert "format" in outcome.fix


def test_parse_time_natural_language_without_lang_is_detected() -> None:
    """The engine is reached with no parameter at all (the language is detected)."""
    pytest.importorskip("dateparser")
    assert run([["py", "parse_time", ""]], "24 septembre 2026") == Ok("2026-09-24 00:00:00")
    assert run([["py", "parse_time", ""]], "24. September 2026") == Ok("2026-09-24 00:00:00")


def test_parse_time_empty_text_is_missing() -> None:
    assert isinstance(run([["py", "parse_time", ""]], "   "), Missing)


def test_parse_time_none_value_is_missing() -> None:
    assert isinstance(run([["py", "parse_time", ""]], None), Missing)


def test_parse_time_non_text_input_is_type_failure() -> None:
    outcome = run([["py", "parse_time", ""]], 20260926)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


@pytest.mark.parametrize("fmt", ["%Q", "%Y%Q", "%Q%Y"])
def test_parse_time_invalid_format_is_schema_error(fmt: str) -> None:
    """A directive `strptime` does not know is a compile-time schema error.

    The check must not depend on the platform: glibc's `strftime` passes an unknown directive
    through while the Windows CRT raises, so validating with `strftime` rejected the chain on
    Windows and accepted it on Linux — this test runs on Linux in CI, where that was caught.

    A stray `%` (`"%"`, `"100%"`) is deliberately not in this list: 3.12's `strptime` reads it as a
    literal (measured) and 3.13 added the `stray % in format` error, so the verdict follows the
    interpreter on purpose — the check asks the same `strptime` the operator runs.
    """
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "parse_time", {"format": fmt}]])
    assert info.value.diagnostic.code == "UP2-E1005"


@pytest.mark.parametrize("fmt", ["%Y-%m-%d %H:%M:%S", "%d/%b/%Y:%H:%M:%S %z", "%%"])
def test_parse_time_valid_format_still_compiles(fmt: str) -> None:
    """The stricter probe must not reject a format `strptime` accepts.

    Validating with `strftime` used to reject `%T` and `%-d` on Windows although `strptime` reads
    them, so the probe now asks the parser instead of the formatter.
    """
    compile_field([["py", "parse_time", {"format": fmt}]])


def test_parse_time_lang_with_machine_format_does_not_need_dateparser() -> None:
    """A lang is given but the text is a machine format.

    The stdlib then succeeds and dateparser is never hit.
    """
    assert run([["py", "parse_time", "en"]], "2026-09-26") == Ok("2026-09-26 00:00:00")


def test_parse_time_natural_language_without_dateparser_is_e2008(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The missing engine is a coded error, with and without an explicit language."""

    def boom() -> Any:
        raise ImportError("no dateparser")

    monkeypatch.setattr(pyops, "_import_dateparser", boom)
    for chain in ([["py", "parse_time", ""]], [["py", "parse_time", "en"]]):
        outcome = run(chain, "3pm the day before yesterday")
        assert isinstance(outcome, Failed)
        assert outcome.code == "UP2-E2008"
        assert "uniparser2[time]" in outcome.fix


def test_parse_time_detection_passes_the_documented_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no parameters the engine detects the language, and reads dates day first."""
    seen: dict[str, Any] = {}

    def parse(text: str, languages: Any = None, settings: Any = None) -> datetime | None:
        seen["languages"] = languages
        seen["settings"] = settings
        return datetime(2026, 9, 24, 15, 0, 0) if "day before yesterday" in text else None

    monkeypatch.setattr(pyops, "_import_dateparser", lambda: parse)
    assert run([["py", "parse_time", ""]], "3pm the day before yesterday") == Ok(
        "2026-09-24 15:00:00"
    )
    assert seen["languages"] is None
    assert seen["settings"] == {"DATE_ORDER": "DMY"}


def test_parse_time_lang_restricts_the_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    def parse(text: str, languages: Any = None, settings: Any = None) -> datetime | None:
        assert languages == ["en"]
        return datetime(2026, 9, 24, 15, 0, 0)

    monkeypatch.setattr(pyops, "_import_dateparser", lambda: parse)
    assert run([["py", "parse_time", "en"]], "3pm the day before yesterday") == Ok(
        "2026-09-24 15:00:00"
    )


def test_parse_time_date_order_reaches_the_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """`date_order` is passed through, so a time-bearing ambiguous date follows the chain."""
    seen: dict[str, Any] = {}

    def parse(text: str, languages: Any = None, settings: Any = None) -> datetime | None:
        seen["settings"] = settings
        return datetime(2026, 3, 4, 15, 30, 0)

    monkeypatch.setattr(pyops, "_import_dateparser", lambda: parse)
    assert run([["py", "parse_time", {"date_order": "MDY"}]], "03/04/2026 15:30") == Ok(
        "2026-03-04 15:30:00"
    )
    assert seen["settings"] == {"DATE_ORDER": "MDY"}


def test_parse_time_now_pins_the_base_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """`now` is handed to the engine as the relative base, as a literal or from the environment."""
    seen: dict[str, Any] = {}

    def parse(text: str, languages: Any = None, settings: Any = None) -> datetime | None:
        seen["settings"] = settings
        return datetime(2026, 1, 2, 12, 0, 0)

    monkeypatch.setattr(pyops, "_import_dateparser", lambda: parse)
    assert run([["py", "parse_time", {"now": "2026-01-01 12:00:00"}]], "tomorrow") == Ok(
        "2026-01-02 12:00:00"
    )
    assert seen["settings"]["RELATIVE_BASE"] == datetime(2026, 1, 1, 12, 0, 0)

    compiled = compile_field([["py", "parse_time", {"now": "$globals.now"}]])
    outcome = eval_field(compiled, "tomorrow", scope=Scope(globals={"now": "2026-01-01 12:00:00"}))
    assert outcome == Ok("2026-01-02 12:00:00")
    assert seen["settings"]["RELATIVE_BASE"] == datetime(2026, 1, 1, 12, 0, 0)


def test_parse_time_dateparser_returning_none_is_e2007(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pyops, "_import_dateparser", lambda: lambda text, **kw: None)
    outcome = run([["py", "parse_time", "en"]], "a time nobody can parse")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2007"


def test_parse_time_dateparser_raising_is_e2007(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(text: str, **kwargs: Any) -> Any:
        raise RuntimeError("dateparser internal error")

    monkeypatch.setattr(pyops, "_import_dateparser", lambda: boom)
    outcome = run([["py", "parse_time", "en"]], "3pm the day before yesterday")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2007"
    # The engine's own failure carries a fix line too (it used to be empty).
    assert outcome.fix


@pytest.mark.parametrize(
    ("params", "pointer"),
    [
        ({"format": "%Y-%m-%d", "lang": "en"}, "/0/2/lang"),
        ({"date_order": "YDM"}, "/0/2/date_order"),
        ({"now": "next tuesday"}, "/0/2/now"),
    ],
)
def test_parse_time_compile_time_rejections(params: dict[str, Any], pointer: str) -> None:
    """A combination or a value that cannot have the intended effect fails before the run."""
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "parse_time", params]])
    assert info.value.diagnostic.code == "UP2-E1005"
    assert info.value.diagnostic.pointer == pointer
    assert info.value.diagnostic.fix


@pytest.mark.parametrize(
    ("order", "expected"),
    [(None, "2026-04-03"), ("DMY", "2026-04-03"), ("MDY", "2026-03-04"), ("YMD", "2026-04-03")],
)
def test_parse_time_date_order_orders_the_table_pair(order: str | None, expected: str) -> None:
    """A plain ambiguous date is decided by the table, in the requested order."""
    if order is None:
        chain: list[Any] = [["py", "parse_time", ""]]
    else:
        chain = [["py", "parse_time", {"date_order": order}]]
    assert run(chain, "03/04/2026") == Ok(f"{expected} 00:00:00")


def test_parse_time_plain_and_time_bearing_writings_agree() -> None:
    """The same writing must not change meaning because a time part follows it (design D3).

    The plain form is read by the table, the time-bearing one by the engine; both follow
    ``date_order``, whose default is day first.
    """
    pytest.importorskip("dateparser")
    assert run([["py", "parse_time", ""]], "03/04/2026") == Ok("2026-04-03 00:00:00")
    assert run([["py", "parse_time", ""]], "03/04/2026 15:30") == Ok("2026-04-03 15:30:00")
    assert run([["py", "parse_time", {"date_order": "MDY"}]], "03/04/2026") == Ok(
        "2026-03-04 00:00:00"
    )
    assert run([["py", "parse_time", {"date_order": "MDY"}]], "03/04/2026 15:30") == Ok(
        "2026-03-04 15:30:00"
    )


def test_real_dateparser_when_installed() -> None:
    pytest.importorskip("dateparser")
    assert run([["py", "parse_time", "en"]], "September 26, 2026") == Ok("2026-09-26 00:00:00")


def test_strftime_renders_another_layout() -> None:
    assert run([["py", "strftime", "%Y/%m/%d"]], "2026-09-24 15:30:00") == Ok("2026/09/24")
    assert run([["py", "strftime", "%d.%m.%Y %H:%M"]], "2026-09-24 15:30:00") == Ok(
        "24.09.2026 15:30"
    )
    assert run([["py", "strftime", "100%% done"]], "2026-09-24 15:30:00") == Ok("100% done")


def test_strftime_requires_the_canonical_shape() -> None:
    outcome = run([["py", "strftime", "%Y/%m/%d"]], "24 septembre 2026")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2007"
    assert "parse_time" in outcome.fix


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
        "%z",
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
        under_c = run([["py", "strftime", "%Y/%m/%d %H:%M:%S"]], "2026-09-24 15:30:00")
        try:
            locale.setlocale(locale.LC_TIME, "")
        except locale.Error:
            pytest.skip("the system locale is unavailable on this machine")
        under_system = run([["py", "strftime", "%Y/%m/%d %H:%M:%S"]], "2026-09-24 15:30:00")
    finally:
        locale.setlocale(locale.LC_TIME, saved)
    assert under_c == under_system == Ok("2026/09/24 15:30:00")


def test_parse_time_output_constant_is_documented_format() -> None:
    assert pyops.TIME_FORMAT == "%Y-%m-%d %H:%M:%S"


# ------------------------------------------------ type conversion (former cast operator)


def test_py_str_uses_json_text_for_containers() -> None:
    assert run([["py", "str", ""]], 12) == Ok("12")
    assert run([["py", "str", ""]], True) == Ok("true")
    assert run([["py", "str", ""]], None) == Ok("")
    assert run([["py", "str", ""]], [1, 2]) == Ok("[1,2]")


def test_py_int_is_strict() -> None:
    assert run([["py", "int", ""]], "42") == Ok(42)
    assert run([["py", "int", ""]], 3.9) == Ok(3)
    outcome = run([["py", "int", ""]], "x")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"
    assert outcome.reason.startswith("py.int conversion failed: ")


def test_py_float_parses_text() -> None:
    assert run([["py", "float", ""]], "1.5") == Ok(1.5)


def test_py_bool_knows_falsey_text() -> None:
    assert run([["py", "bool", ""]], "false") == Ok(False)
    assert run([["py", "bool", ""]], "NO") == Ok(False)
    assert run([["py", "bool", ""]], "yes") == Ok(True)
    assert run([["py", "bool", ""]], 0) == Ok(False)
    assert run([["py", "bool", ""]], []) == Ok(False)
    assert run([["py", "bool", ""]], None) == Ok(False)


def test_py_list_parses_json_array() -> None:
    assert run([["py", "list", ""]], "[1,2]") == Ok([1, 2])
    assert run([["py", "list", ""]], [3]) == Ok([3])


def test_py_from_json_parses_any_json_text() -> None:
    assert run([["py", "from_json", ""]], '{"a":1}') == Ok({"a": 1})


def test_py_from_json_failure_is_failed_not_exception() -> None:
    outcome = run([["py", "from_json", ""]], "{oops")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"
