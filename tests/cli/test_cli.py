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
        "node",
        "type",
    }
    # New syntax: slot semantics are declared by the operator, and `--json` must report them
    # together with the arity.
    assert {item["arity"] for item in payload} == {2, 3}
    assert all("action_slot" in item and item["slots"] for item in payload)
    # In-chain code is an optional capability: `--json` must expose what it depends on.
    code_item = next(item for item in payload if item["name"] == "code")
    assert code_item["requires"] == ["pydantic_monty"]
    assert code_item["slots"] == ["source"]


def test_ops_text_mentions_actions(capsys) -> None:
    assert main(["ops"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "normalize_space" in out
    # The new-syntax text output carries the slot roles (the accessor / selector of
    # `["css1","text","h1"]`).
    assert "slot2=function" in out
    assert "slot2=accessor" in out
    assert "slot3=selector" in out
    assert "slot2=source" in out  # code: a 2-slot operator has a single parameter


def test_ops_json_reports_the_parameter_slot_shape(capsys) -> None:
    """A chain writer must be able to see which writing slot 3 takes, without inferring the rule."""
    assert main(["ops", "--json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    actions = {
        (item["name"], action["name"]): action for item in payload for action in item["actions"]
    }
    assert actions[("py", "slice")]["param_form"] == "value"
    assert actions[("py", "replace")]["param_form"] == "array"
    assert actions[("py", "upper")]["param_form"] == "none"
    # A parameter the action slot itself provides does not count: `@<attribute>` fills `attr`.
    assert actions[("css1", "@<attribute>")]["param_form"] == "value"


def test_ops_text_reports_the_parameter_slot_shape(capsys) -> None:
    assert main(["ops"]) == EXIT_OK
    out = capsys.readouterr().out
    for form in ("value", "array", "none"):
        assert f"[slot3={form}]" in out
    # A single-action operator's parameter slot is slot 2, not slot 3: `code` takes the source
    # and `json` takes the expression itself.
    assert "[slot2=value]" in out
    assert "[slot2=source]" in out


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
    path = write_chain(tmp_path, [["py", "strip"], ["py", "upper"]])
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
    path = write_chain(tmp_path, [["py", "normalize_space"], ["py", "upper"]])
    code = main(["trial", str(path), "--input", "text=  a   b  ", "--json"])
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"state": "ok", "value": "A B"}


def test_trial_reads_input_from_file(tmp_path: Path, capsys) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("  hi  ", encoding="utf-8")
    path = write_chain(tmp_path, [["py", "strip"]])
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
    path = write_chain(tmp_path, [["py", "strip"]])
    assert main(["trial", str(path), "--input", "text=123", "--json"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["value"] == "123"


def test_trial_no_match_is_not_an_error(tmp_path: Path, capsys) -> None:
    path = write_chain(tmp_path, [["re", "search", r"\d+"]])
    code = main(["trial", str(path), "--input", "text=abc", "--json"])
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "ok"
    assert payload["value"] == ""


def test_trial_failed_exits_nonzero(tmp_path: Path, capsys) -> None:
    """A failed stage always fails the run: there is no configuration that degrades it."""
    path = write_chain(tmp_path, [["py", "int"]])
    code = main(["trial", str(path), "--input", "text=abc", "--json"])
    assert code == EXIT_FAILED
    assert json.loads(capsys.readouterr().out)["code"] == "UP2-E2005"


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


def test_trial_has_no_settlement_flags(tmp_path: Path) -> None:
    """The retired ``--on-missing`` / ``--on-error`` are gone, not silently ignored."""
    path = write_chain(tmp_path, [["py", "strip"]])
    for flag in ("--on-missing", "--on-error"):
        with pytest.raises(SystemExit) as info:
            main(["trial", str(path), "--input", "text=a", flag, "drop"])
        assert info.value.code == EXIT_USAGE


def test_trial_bad_product_syntax(tmp_path: Path) -> None:
    path = write_chain(tmp_path, [["py", "strip"]])
    assert main(["trial", str(path), "--input", "text=a", "--product", "n1"]) == EXIT_USAGE


# ---------------------------------------------------------------- story files (03 §2)


def _story(*, request: bool = True) -> dict[str, object]:
    body: list[object] = (
        [["udf", "fetch"], ["py", "getattr", "text"]] if request else [["py", "strip"]]
    )
    return {"nodes": {"records": body}}


def test_lint_accepts_a_story_file(tmp_path: Path, capsys) -> None:
    path = write_chain(tmp_path, _story(), name="site.json")
    assert main(["lint", str(path), "--json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True, "nodes": 1, "names": ["records"]}


def test_lint_reports_a_story_diagnostic(tmp_path: Path, capsys) -> None:
    broken = {"nodes": {"a": [["node", "gone"]]}}
    path = write_chain(tmp_path, broken, name="site.json")
    assert main(["lint", str(path), "--json"]) == EXIT_FAILED
    assert json.loads(capsys.readouterr().out)["code"] == "UP2-E1016"


def test_lint_names_the_nodes(tmp_path: Path, capsys) -> None:
    path = write_chain(tmp_path, _story(request=False), name="site.json")
    assert main(["lint", str(path)]) == EXIT_OK
    assert "nodes: records" in capsys.readouterr().out


def test_trial_finishes_a_story_without_requests(tmp_path: Path, capsys) -> None:
    path = write_chain(tmp_path, _story(request=False), name="site.json")
    assert main(["trial", str(path), "--input", "text=hi", "--json"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out) == {"state": "ok", "value": "hi"}


def test_trial_reports_a_missing_udf(tmp_path: Path, capsys) -> None:
    """A CLI has no host, so a story that fetches reports the missing function."""
    path = write_chain(tmp_path, _story(), name="site.json")
    assert main(["trial", str(path), "--input", "text=https://x/", "--json"]) == EXIT_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["code"] == "UP2-E1010"
    assert "fetch" in payload["message"]


def test_trial_refuses_chain_only_flags_for_a_story(tmp_path: Path) -> None:
    path = write_chain(tmp_path, _story(request=False), name="site.json")
    assert main(["trial", str(path), "--input", "text=x", "--product", "n1=1"]) == EXIT_USAGE
    # `--global` is a run override for a story too: it merges over the story's constants.
    assert main(["trial", str(path), "--input", "text=x", "--global", "a=1"]) == EXIT_OK
    assert main(["lint", str(path), "--product", "n1"]) == EXIT_USAGE


def test_trial_refuses_node_for_a_chain(tmp_path: Path) -> None:
    path = write_chain(tmp_path, [["py", "strip"]], name="chain.json")
    assert main(["trial", str(path), "--input", "text=x", "--node", "a"]) == EXIT_USAGE


# ---------------------------------------------------------------- the trace (06 §5.1)


def test_trial_trace_reports_the_events_of_a_chain(tmp_path: Path, capsys) -> None:
    path = write_chain(tmp_path, [["py", "urljoin", "$globals.base"]])
    code = main(
        [
            "trial",
            str(path),
            "--input",
            "text=page.html",
            "--global",
            "base=https://x/",
            "--trace",
            "--json",
        ]
    )
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "ok" and payload["value"] == "https://x/page.html"
    assert len(payload["trace"]) == 1
    event = payload["trace"][0]
    assert isinstance(event.pop("ms"), float)
    assert event == {
        "seq": 1,
        "node": None,  # a plain field chain is not inside a story
        "item": None,
        "field": None,
        "stage": 0,
        "op": "py",
        "action": "urljoin",
        "params": {"base": {"kind": "ref", "target": "globals.base"}},
        "input": {"type": "str", "preview": '"page.html"', "size": 11},
        "output": {"type": "str", "preview": '"https://x/page.html"', "size": 21},
        "state": "Ok",
        "detail": None,
    }


def test_trial_trace_ends_at_the_missing_udf(tmp_path: Path, capsys) -> None:
    """The pre-flight is before evaluation, so a missing udf leaves no stage events."""
    path = write_chain(tmp_path, _story(), name="site.json")
    code = main(["trial", str(path), "--input", "text=https://x/", "--trace", "--json"])
    assert code == EXIT_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "failed" and payload["code"] == "UP2-E1010"
    assert payload["trace"] == []


def test_trial_trace_is_one_line_per_event_without_json(tmp_path: Path, capsys) -> None:
    story = {"nodes": {"bad": [["py", "int"]]}}
    path = write_chain(tmp_path, story, name="site.json")
    assert main(["trial", str(path), "--input", "text=abc", "--trace"]) == EXIT_FAILED
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2  # the failing stage, then the run's state
    assert "py.int" in lines[0] and "Failed" in lines[0]
    assert lines[1].startswith("[failed] ")


def test_trial_trace_carries_the_failing_stage(tmp_path: Path, capsys) -> None:
    path = write_chain(tmp_path, [["py", "int"]])
    code = main(["trial", str(path), "--input", "text=abc", "--trace", "--json"])
    assert code == EXIT_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "failed" and payload["code"] == "UP2-E2005"
    event = payload["trace"][-1]
    assert event["state"] == "Failed"
    assert event["detail"]["code"] == "UP2-E2005"
    assert event["output"]["type"] == "null"


# ---------------------------------------------------- the store commands (04 §4, §7-S6/S7)

CHAIN = [["css1", "text", "h1"]]
OTHER_CHAIN = [["css1", "text", "h2"]]
DOMAIN = "ah.gov.cn"
KEY = "政府文件列表"


def store_home(monkeypatch, tmp_path: Path) -> Path:
    """``tmp_path`` is ``UP2_HOME`` (04 §4.1); the store kind stays whatever the case sets."""
    home = tmp_path / "home"
    monkeypatch.setenv("UP2_HOME", str(home))
    monkeypatch.delenv("UP2_STORE", raising=False)
    return home


def publish(tmp_path: Path, payload: object, *extra: str) -> int:
    path = write_chain(tmp_path, payload, name="chain.json")
    return main(["publish", str(path), "--domain", DOMAIN, "--key", KEY, *extra])


def test_publish_get_and_audit_end_to_end(tmp_path: Path, monkeypatch, capsys) -> None:
    store_home(monkeypatch, tmp_path)
    assert publish(tmp_path, CHAIN, "--actor", "llm:claude", "--note", "first", "--json") == EXIT_OK
    result = json.loads(capsys.readouterr().out)
    assert result["changed"] is True
    assert result["old_hash"] is None and result["audit_seq"] == 1

    assert main(["get", DOMAIN, KEY]) == EXIT_OK
    stored = json.loads(capsys.readouterr().out)
    assert stored["graph_hash"] == result["new_hash"]
    assert stored["graph"] == CHAIN
    assert (stored["status"], stored["source"]) == ("draft", "agent")
    assert stored["chain_id"] == result["chain_id"]

    assert main(["get", DOMAIN, KEY, "--graph"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out) == CHAIN

    assert main(["audit", DOMAIN, KEY, "--json"]) == EXIT_OK
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1
    assert rows[0]["actor"] == "llm:claude"
    assert rows[0]["note"] == "first"
    assert rows[0]["new_hash"] == result["new_hash"]


def test_re_publishing_the_same_graph_is_a_no_op(tmp_path: Path, monkeypatch, capsys) -> None:
    store_home(monkeypatch, tmp_path)
    assert publish(tmp_path, CHAIN, "--json") == EXIT_OK
    capsys.readouterr()
    assert publish(tmp_path, CHAIN, "--json") == EXIT_OK
    assert json.loads(capsys.readouterr().out)["changed"] is False
    assert main(["audit", DOMAIN, KEY, "--json"]) == EXIT_OK
    assert len(json.loads(capsys.readouterr().out)) == 1


def test_publish_refuses_a_bad_chain(tmp_path: Path, monkeypatch, capsys) -> None:
    store_home(monkeypatch, tmp_path)
    assert publish(tmp_path, [["nosuchoperator", "x", "y"]], "--json") == EXIT_FAILED
    assert json.loads(capsys.readouterr().out)["code"] == "UP2-E1001"
    assert main(["get", DOMAIN, KEY]) == EXIT_FAILED


def test_publish_skip_tests_without_a_note_is_refused(tmp_path: Path, monkeypatch, capsys) -> None:
    store_home(monkeypatch, tmp_path)
    assert publish(tmp_path, CHAIN, "--skip-tests", "--json") == EXIT_FAILED
    assert json.loads(capsys.readouterr().out)["code"] == "UP2-E3005"
    assert main(["get", DOMAIN, KEY]) == EXIT_FAILED


def test_publish_skip_tests_records_the_note(tmp_path: Path, monkeypatch, capsys) -> None:
    store_home(monkeypatch, tmp_path)
    assert publish(tmp_path, CHAIN, "--skip-tests", "--note", "samples not ready") == EXIT_OK
    capsys.readouterr()
    assert main(["audit", DOMAIN, KEY, "--json"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)[0]["note"] == "samples not ready"


def test_publish_needs_a_confirmation_to_overwrite_a_ready_chain(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    home = store_home(monkeypatch, tmp_path)
    assert publish(tmp_path, CHAIN) == EXIT_OK
    capsys.readouterr()
    path = home / "chains" / DOMAIN / f"{KEY}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["status"] = "ready"
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8", newline="\n")
    assert publish(tmp_path, OTHER_CHAIN) == EXIT_USAGE
    assert "confirm-overwrite" in capsys.readouterr().err
    assert publish(tmp_path, OTHER_CHAIN, "--confirm-overwrite", "--json") == EXIT_OK
    assert json.loads(capsys.readouterr().out)["changed"] is True
    assert main(["get", DOMAIN, KEY, "--graph"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out) == OTHER_CHAIN


def test_get_recompiles_what_it_read(tmp_path: Path, monkeypatch, capsys) -> None:
    """A stored chain is data: reading it back compiles it again (04 §1, 01 §8)."""
    home = store_home(monkeypatch, tmp_path)
    assert publish(tmp_path, CHAIN) == EXIT_OK
    capsys.readouterr()
    path = home / "chains" / DOMAIN / f"{KEY}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["graph"] = [["nosuchoperator", "x", "y"]]
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8", newline="\n")
    assert main(["get", DOMAIN, KEY]) == EXIT_FAILED
    assert "UP2-E1001" in capsys.readouterr().err


def test_an_unknown_key_is_not_found(tmp_path: Path, monkeypatch, capsys) -> None:
    store_home(monkeypatch, tmp_path)
    for command in (["get", DOMAIN, "nope"], ["audit", DOMAIN, "nope"]):
        assert main(command) == EXIT_FAILED
        assert "no chain" in capsys.readouterr().err


def test_the_store_kind_comes_from_the_environment(tmp_path: Path, monkeypatch, capsys) -> None:
    store_home(monkeypatch, tmp_path)
    for kind in ("file", "sqlite"):
        monkeypatch.setenv("UP2_STORE", kind)
        assert publish(tmp_path, CHAIN, "--json") == EXIT_OK
        assert json.loads(capsys.readouterr().out)["changed"] is True
        assert main(["get", DOMAIN, KEY]) == EXIT_OK
        capsys.readouterr()
    # The two stores are separate: the SQLite row is not visible to the file store.
    monkeypatch.setenv("UP2_STORE", "file")
    assert (tmp_path / "home" / "chains" / DOMAIN / f"{KEY}.json").is_file()
    assert (tmp_path / "home" / "store.sqlite3").is_file()
    monkeypatch.setenv("UP2_STORE", "mysql")
    assert publish(tmp_path, CHAIN) == EXIT_USAGE
    assert "UP2_STORE" in capsys.readouterr().err
