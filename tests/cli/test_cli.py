"""End-to-end for the ``up2`` command (design doc 04 §7-S0–S3).

``main(argv)`` is called directly, with no subprocess; the exit code is the assertion target.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from uniparser2.cli.main import EXIT_FAILED, EXIT_OK, EXIT_USAGE, main

TESTS_ROOT = Path(__file__).resolve().parents[1]


def write_chain(tmp_path: Path, payload: object, name: str = "chain.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_version_flag(capsys) -> None:
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    assert "uniparser2" in capsys.readouterr().out


def test_no_command_prints_help() -> None:
    assert main([]) == EXIT_USAGE


def test_ops_json_lists_operators(capsys) -> None:
    assert main(["ops", "--json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    names = {item["name"] for item in payload}
    assert names == {
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
    # New syntax: slot semantics are declared by the operator, and `--json` must report them
    # together with the arity.
    assert {item["arity"] for item in payload} == {2, 3}
    assert all("action_slot" in item and item["slots"] for item in payload)
    # In-chain code is an optional capability: `--json` must expose what it depends on.
    code_item = next(item for item in payload if item["name"] == "code")
    assert code_item["requires"] == ["pydantic_monty"]
    assert code_item["slots"] == ["source & inputs"]


def test_ops_text_mentions_actions(capsys) -> None:
    assert main(["ops"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "normalize_space" in out
    # The new-syntax text output carries the slot roles (the accessor / selector of
    # `["css1","text","h1"]`).
    assert "slot2=function" in out
    assert "slot2=accessor" in out
    assert "slot3=selector" in out
    assert "slot2=source & inputs" in out  # code: a 2-slot operator has a single parameter


def test_ops_json_reports_the_parameter_slot_shape(capsys) -> None:
    """A chain writer must be able to see which writing slot 3 takes, without inferring the rule."""
    assert main(["ops", "--json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    actions = {
        (item["name"], action["name"]): action for item in payload for action in item["actions"]
    }
    assert actions[("py", "slice")]["param_form"] == "value"
    assert actions[("py", "split")]["param_form"] == "named"
    assert actions[("py", "strip")]["param_form"] == "none"
    # A parameter the action slot itself provides does not count: `@<attribute>` fills `attr`.
    assert actions[("css1", "@<attribute>")]["param_form"] == "value"


def test_ops_text_reports_the_parameter_slot_shape(capsys) -> None:
    assert main(["ops"]) == EXIT_OK
    out = capsys.readouterr().out
    for form in ("value", "named", "none"):
        assert f"[slot3={form}]" in out
    # A 2-slot operator's parameter slot is slot 2, not slot 3: `code` takes a named object
    # (`src` / `inputs`) and `json` takes the value itself.
    assert "[slot2=named]" in out
    assert "[slot2=value]" in out


def test_conformance_check_passes(capsys) -> None:
    code = main(["conformance", "--check", "--tests-root", str(TESTS_ROOT)])
    assert code == EXIT_OK, capsys.readouterr().out


def test_conformance_json_shape(capsys) -> None:
    assert main(["conformance", "--json", "--tests-root", str(TESTS_ROOT)]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["declared_pairs"] == payload["covered_pairs"]


def test_conformance_missing_tests_root() -> None:
    assert main(["conformance", "--tests-root", "no_such_dir"]) == EXIT_USAGE


def test_lint_ok(tmp_path: Path, capsys) -> None:
    path = write_chain(tmp_path, [["py", "strip", ""], ["py", "upper", ""]])
    assert main(["lint", str(path)]) == EXIT_OK
    assert "OK" in capsys.readouterr().out


def test_lint_reports_code_on_bad_chain(tmp_path: Path, capsys) -> None:
    path = write_chain(tmp_path, [["nope", "x"]])
    assert main(["lint", str(path), "--json"]) == EXIT_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["code"] == "UP2-E1001"


def test_lint_bad_json_is_usage_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    assert main(["lint", str(path)]) == EXIT_USAGE


def test_trial_runs_chain_with_input(tmp_path: Path, capsys) -> None:
    path = write_chain(tmp_path, [["py", "normalize_space", ""], ["py", "upper", ""]])
    code = main(["trial", str(path), "--input", "text=  a   b  ", "--json"])
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"state": "ok", "value": "A B"}


def test_trial_reads_input_from_file(tmp_path: Path, capsys) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("  hi  ", encoding="utf-8")
    path = write_chain(tmp_path, [["py", "strip", ""]])
    assert main(["trial", str(path), "--input", f"text=@{sample}", "--json"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["value"] == "hi"


def test_trial_uses_globals_reference(tmp_path: Path, capsys) -> None:
    path = write_chain(tmp_path, [["py", "urljoin", "$globals.base"]])
    code = main(
        [
            "trial",
            str(path),
            "--input",
            "text=page.html",
            "--global",
            "base=https://x/",
            "--json",
        ]
    )
    assert code == EXIT_OK
    assert json.loads(capsys.readouterr().out)["value"] == "https://x/page.html"


def test_trial_keeps_numeric_input_as_text(tmp_path: Path, capsys) -> None:
    """``--input text=123`` must not silently become an int (or ``py.strip`` would fail)."""
    path = write_chain(tmp_path, [["py", "strip", ""]])
    assert main(["trial", str(path), "--input", "text=123", "--json"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["value"] == "123"


def test_trial_missing_is_not_an_error(tmp_path: Path, capsys) -> None:
    path = write_chain(tmp_path, [["re", "search", r"\d+"]])
    code = main(["trial", str(path), "--input", "text=abc", "--on-missing", "drop", "--json"])
    assert code == EXIT_OK
    assert json.loads(capsys.readouterr().out)["state"] == "missing"


def test_trial_failed_exits_nonzero(tmp_path: Path, capsys) -> None:
    path = write_chain(tmp_path, [["re", "search", r"\d+"]])
    code = main(["trial", str(path), "--input", "text=abc", "--on-missing", "raise", "--json"])
    assert code == EXIT_FAILED
    assert json.loads(capsys.readouterr().out)["code"] == "UP2-E2015"


def test_trial_products_reference(tmp_path: Path, capsys) -> None:
    path = write_chain(tmp_path, [["py", "urljoin", "$n1.url"]])
    code = main(
        [
            "trial",
            str(path),
            "--input",
            "text=page.html",
            "--product",
            'n1={"url":"https://x/"}',
            "--json",
        ]
    )
    assert code == EXIT_OK
    assert json.loads(capsys.readouterr().out)["value"] == "https://x/page.html"


def test_trial_bad_policy_is_usage_error(tmp_path: Path) -> None:
    """An illegal policy is blocked by argparse choices (``parser.error`` -> ``SystemExit(2)``)."""
    path = write_chain(tmp_path, [["py", "strip", ""]])
    with pytest.raises(SystemExit) as info:
        main(["trial", str(path), "--input", "text=a", "--on-missing", "nope"])
    assert info.value.code == EXIT_USAGE


def test_trial_bad_product_syntax(tmp_path: Path) -> None:
    path = write_chain(tmp_path, [["py", "strip", ""]])
    assert main(["trial", str(path), "--input", "text=a", "--product", "n1"]) == EXIT_USAGE
