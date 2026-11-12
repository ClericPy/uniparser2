"""The SOP commands around the publish gate: the snapshot runner and ``up2 doctor`` (04 §6–§7).

``main(argv)`` is called directly, with no subprocess; the exit code is the assertion target. The
story cases exercise the **story executor** path of the runner, the field-chain cases the operator
path, and ``doctor`` runs against both stores.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from pathlib import Path

import pytest

from uniparser2.cli.main import EXIT_FAILED, EXIT_OK, EXIT_USAGE, main

DOMAIN = "local"
KEY = "demo"
STORY = {
    "nodes": {
        "record": {
            "title": [["py", "normalize_space"], ["py", "upper"]],
        }
    }
}
CHAIN = [["py", "normalize_space"], ["py", "upper"]]
INPUT = "  hello   world  "
EXPECTED = {"title": "HELLO WORLD"}


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")
    return path


def case_dir(root: Path, case: str = "a") -> Path:
    return root / DOMAIN / KEY / case


def make_case(
    root: Path, *, case: str = "a", text: str = INPUT, expected: object = EXPECTED
) -> Path:
    directory = case_dir(root, case)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "input.txt").write_text(text, encoding="utf-8", newline="\n")
    if expected is not None:
        write_json(directory / "expected.json", expected)
    return directory


def store_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str = "file") -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("UP2_HOME", str(home))
    monkeypatch.setenv("UP2_STORE", kind)
    return home


def publish(tmp_path: Path, samples: Path, payload: object, *extra: str) -> int:
    path = write_json(tmp_path / "chain.json", payload)
    return main(
        [
            "publish",
            str(path),
            "--domain",
            DOMAIN,
            "--key",
            KEY,
            "--tests-root",
            str(samples),
            *extra,
        ]
    )


# ---------------------------------------------------------------- the runner's two paths


@pytest.mark.covers("py", "normalize_space")
def test_a_story_case_passes_through_the_story_executor(tmp_path: Path, capsys) -> None:
    samples = tmp_path / "samples"
    make_case(samples, expected=None)
    path = write_json(tmp_path / "site.json", STORY)
    assert (
        main(
            [
                "snapshot",
                str(path),
                "--domain",
                DOMAIN,
                "--key",
                KEY,
                "--case",
                "a",
                "--accept",
                "--tests-root",
                str(samples),
                "--json",
            ]
        )
        == EXIT_OK
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["value"] == EXPECTED
    assert json.loads((case_dir(samples) / "expected.json").read_text(encoding="utf-8")) == EXPECTED


@pytest.mark.covers("py", "upper")
def test_a_field_chain_case_can_be_recorded_too(tmp_path: Path, capsys) -> None:
    samples = tmp_path / "samples"
    make_case(samples, expected=None)
    path = write_json(tmp_path / "chain.json", CHAIN)
    assert (
        main(
            [
                "snapshot",
                str(path),
                "--domain",
                DOMAIN,
                "--key",
                KEY,
                "--case",
                "a",
                "--accept",
                "--tests-root",
                str(samples),
                "--json",
            ]
        )
        == EXIT_OK
    )
    assert json.loads(capsys.readouterr().out)["value"] == "HELLO WORLD"


def test_snapshot_without_accept_writes_nothing(tmp_path: Path, capsys) -> None:
    """`--accept` is the only way a snapshot is written (04 §7-S4)."""
    samples = tmp_path / "samples"
    make_case(samples, expected=None)
    path = write_json(tmp_path / "site.json", STORY)
    code = main(
        [
            "snapshot",
            str(path),
            "--domain",
            DOMAIN,
            "--key",
            KEY,
            "--case",
            "a",
            "--tests-root",
            str(samples),
        ]
    )
    assert code == EXIT_USAGE
    assert "--accept" in capsys.readouterr().err
    assert not (case_dir(samples) / "expected.json").exists()


def test_snapshot_refuses_a_case_name_that_is_a_path(tmp_path: Path, capsys) -> None:
    """A case name is one directory name; `../x` must not reach outside the samples root."""
    samples = tmp_path / "samples"
    path = write_json(tmp_path / "site.json", STORY)
    code = main(
        [
            "snapshot",
            str(path),
            "--domain",
            DOMAIN,
            "--key",
            KEY,
            "--case",
            "../escape",
            "--accept",
            "--tests-root",
            str(samples),
        ]
    )
    assert code == EXIT_USAGE
    assert "case name" in capsys.readouterr().err
    assert not (tmp_path / "escape").exists()


def test_snapshot_refuses_a_story_that_fetches(tmp_path: Path, capsys) -> None:
    """A request the cache does not hold is a miss: the runner never reaches the network."""
    samples = tmp_path / "samples"
    make_case(samples, expected=None)
    story = {
        "nodes": {
            "rec": {
                "u": [
                    ["ctx", "dict", {"url": "obj"}],
                    ["udf", "fetch"],
                    ["py", "getattr", "text"],
                ],
            }
        }
    }
    path = write_json(tmp_path / "site.json", story)
    code = main(
        [
            "snapshot",
            str(path),
            "--domain",
            DOMAIN,
            "--key",
            KEY,
            "--case",
            "a",
            "--accept",
            "--tests-root",
            str(samples),
        ]
    )
    assert code == EXIT_FAILED
    assert "not in the request cache" in capsys.readouterr().err


# ---------------------------------------------------------------- G2 on publish


@pytest.mark.parametrize("kind", ["file", "sqlite"])
def test_publish_regresses_the_samples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, kind: str
) -> None:
    """A green set publishes; a red one is refused with the JSON Pointer difference, both stores."""
    home = store_home(monkeypatch, tmp_path, kind)
    samples = tmp_path / "samples"
    make_case(samples)
    assert publish(tmp_path, samples, STORY, "--json") == EXIT_OK
    first = json.loads(capsys.readouterr().out)
    assert first["changed"] is True

    # The page changed under the chain: the snapshot no longer matches.
    make_case(samples, expected={"title": "HELLO"})
    assert publish(tmp_path, samples, STORY, "--json") == EXIT_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["code"] == "UP2-E3005"
    assert "/title" in payload["message"]
    assert "up2 test" in payload["fix"]
    # The refusal wrote nothing: the chain still has exactly the one audit row it was published
    # with, and its fingerprint is unchanged.
    assert main(["audit", DOMAIN, KEY, "--json"]) == EXIT_OK
    rows = json.loads(capsys.readouterr().out)
    assert [row["new_hash"] for row in rows] == [first["new_hash"]]
    if kind == "file":
        assert (home / "chains" / DOMAIN / f"{KEY}.json").is_file()


def test_skip_tests_and_note_leave_the_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """G2's bypass is allowed, and the audit row records why (04 §6)."""
    store_home(monkeypatch, tmp_path)
    samples = tmp_path / "samples"
    make_case(samples, expected=[{"title": "WRONG"}])
    assert publish(tmp_path, samples, STORY, "--skip-tests", "--json") == EXIT_FAILED
    assert json.loads(capsys.readouterr().out)["code"] == "UP2-E3005"
    assert publish(tmp_path, samples, STORY, "--skip-tests", "--note", "page changed") == EXIT_OK
    capsys.readouterr()
    assert main(["audit", DOMAIN, KEY, "--json"]) == EXIT_OK
    rows = json.loads(capsys.readouterr().out)
    assert [row["note"] for row in rows] == ["page changed"]


def test_publish_without_samples_has_nothing_to_regress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """An empty set is green by definition: the chain may be stored before the samples exist."""
    store_home(monkeypatch, tmp_path)
    samples = tmp_path / "samples"
    assert publish(tmp_path, samples, STORY, "--json") == EXIT_OK
    assert json.loads(capsys.readouterr().out)["changed"] is True


def test_a_case_without_a_snapshot_fails_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """A case that carries an input but no snapshot has nothing to regress, so it is not a pass."""
    store_home(monkeypatch, tmp_path)
    samples = tmp_path / "samples"
    make_case(samples, expected=None)
    assert publish(tmp_path, samples, STORY, "--json") == EXIT_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert payload["code"] == "UP2-E3005"
    assert "expected.json" in payload["message"]


# ---------------------------------------------------------------- up2 test


def test_test_reports_every_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    store_home(monkeypatch, tmp_path)
    samples = tmp_path / "samples"
    make_case(samples, case="a")
    make_case(samples, case="b", text="  other  ", expected={"title": "OTHER"})
    assert publish(tmp_path, samples, STORY) == EXIT_OK
    capsys.readouterr()
    assert main(["test", DOMAIN, KEY, "--tests-root", str(samples), "--json"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["ok"] is True

    make_case(samples, case="b", text="  other  ", expected={"title": "OTHER"})
    make_case(samples, case="a", expected={"title": "hello world"})
    assert main(["test", DOMAIN, KEY, "--tests-root", str(samples), "--json"]) == EXIT_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert [item["case"] for item in payload["failures"]] == ["a"]
    assert payload["failures"][0]["differences"][0]["pointer"] == "/title"


def test_test_can_run_one_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    store_home(monkeypatch, tmp_path)
    samples = tmp_path / "samples"
    make_case(samples, case="a")
    make_case(samples, case="b")
    assert publish(tmp_path, samples, STORY) == EXIT_OK
    capsys.readouterr()
    assert main(["test", DOMAIN, KEY, "--case", "a", "--tests-root", str(samples)]) == EXIT_OK
    assert "matches its samples" in capsys.readouterr().out
    # Only the case that is asked for is regressed.
    make_case(samples, case="b", expected=[{"title": "NOPE"}])
    assert main(["test", DOMAIN, KEY, "--case", "a", "--tests-root", str(samples)]) == EXIT_OK
    assert main(["test", DOMAIN, KEY, "--case", "b", "--tests-root", str(samples)]) == EXIT_FAILED


def test_test_prints_the_pointer_in_text_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    store_home(monkeypatch, tmp_path)
    samples = tmp_path / "samples"
    make_case(samples)
    assert publish(tmp_path, samples, STORY) == EXIT_OK
    capsys.readouterr()
    make_case(samples, expected={"title": "HELLO"})
    assert main(["test", DOMAIN, KEY, "--tests-root", str(samples)]) == EXIT_FAILED
    out = capsys.readouterr().out
    assert "/title" in out and "expect" in out


def test_test_without_a_chain_is_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    store_home(monkeypatch, tmp_path)
    assert main(["test", DOMAIN, "nope"]) == EXIT_FAILED
    assert "no chain" in capsys.readouterr().err


def test_test_recompiles_the_stored_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """A hand-edited stored chain is reported by the compiler once, not once per case (01 §8)."""
    home = store_home(monkeypatch, tmp_path)
    samples = tmp_path / "samples"
    make_case(samples)
    assert publish(tmp_path, samples, STORY) == EXIT_OK
    capsys.readouterr()
    path = home / "chains" / DOMAIN / f"{KEY}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["graph"] = [["nosuchoperator", "x", "y"]]
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8", newline="\n")
    assert main(["test", DOMAIN, KEY, "--tests-root", str(samples), "--json"]) == EXIT_FAILED
    assert json.loads(capsys.readouterr().out)["code"] == "UP2-E1001"


# ---------------------------------------------------------------- up2 doctor


@pytest.mark.parametrize("kind", ["file", "sqlite"])
def test_doctor_detects_and_fixes_a_chain_without_an_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, kind: str
) -> None:
    """`007` §3 acceptance item 3, on both stores."""
    home = store_home(monkeypatch, tmp_path, kind)
    assert publish(tmp_path, tmp_path / "samples", STORY, "--json") == EXIT_OK
    chain_id = json.loads(capsys.readouterr().out)["chain_id"]
    if kind == "sqlite":
        with contextlib.closing(sqlite3.connect(home / "store.sqlite3")) as conn:
            conn.execute("DELETE FROM template_audit")
            conn.commit()
    else:
        (home / "audit" / DOMAIN / f"{KEY}.jsonl").unlink()

    assert main(["doctor", "--json"]) == EXIT_FAILED
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert chain_id in report["findings"][0]["message"]
    assert report["fixed"] == []

    assert main(["doctor", "--fix", "--json"]) == EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True and report["remaining"] == []
    assert report["fixed"][0]["chain_id"] == chain_id
    assert report["fixed"][0]["actor"] == "doctor"
    assert report["fixed"][0]["old_hash"] is None
    assert "no audit row" in report["fixed"][0]["note"]


def test_doctor_is_quiet_on_a_healthy_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    store_home(monkeypatch, tmp_path)
    assert publish(tmp_path, tmp_path / "samples", STORY) == EXIT_OK
    capsys.readouterr()
    assert main(["doctor"]) == EXIT_OK
    assert "no inconsistency" in capsys.readouterr().out


def test_doctor_cannot_fix_an_orphan_audit_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """`--fix` writes a missing audit row; an audit row without a chain is left as a finding."""
    home = store_home(monkeypatch, tmp_path)
    assert publish(tmp_path, tmp_path / "samples", STORY) == EXIT_OK
    capsys.readouterr()
    (home / "chains" / DOMAIN / f"{KEY}.json").unlink()
    assert main(["doctor", "--fix", "--json"]) == EXIT_FAILED
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False and report["fixed"] == []
    assert "no chain" in report["remaining"][0]["message"]
