"""A story that fetches is answered from the request cache (change `cached-snapshot-runs`).

The runner **replays** and never reaches the network: a request with no cached answer is a miss, and
a miss is reported rather than fetched. The cache is the fixture, so a live sample becomes a
regression case as soon as its answers have been fetched once.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uniparser2.cli.main import EXIT_FAILED, EXIT_OK, main
from uniparser2.cli.samples import run_graph
from uniparser2.net import RequestCache, Response

DOMAIN = "local"
KEY = "demo"

STORY = {
    "nodes": {
        "record": {
            "title": [
                ["ctx", "dict", {"url": "obj"}],
                ["udf", "fetch"],
                ["py", "getattr", "text"],
                ["py", "upper"],
            ]
        }
    }
}
"""A story that fetches one page and reads its title."""

REQUEST = {"url": "https://example.com/page"}
ANSWER = "<html><title>hello</title></html>"


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")
    return path


def cached(cache: RequestCache, request: dict[str, Any] = REQUEST) -> RequestCache:
    """A cache holding the answer of one request."""
    cache.put(request, Response(text=ANSWER, url=str(request["url"])))
    return cache


def publish(tmp_path: Path, samples: Path, payload: object, *extra: str) -> int:
    """Publish a chain under the sample's identity, with the snapshot gate on."""
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


# ---------------------------------------------------------------- the runner


def test_a_story_runs_from_the_cache(tmp_path: Path) -> None:
    cache = cached(RequestCache(tmp_path))
    result = run_graph(STORY, "https://example.com/page", cache=cache)
    assert result.ok
    assert result.value == {"title": "<HTML><TITLE>HELLO</TITLE></HTML>"}


def test_a_miss_is_reported_and_nothing_is_fetched(tmp_path: Path) -> None:
    """A request the cache does not hold is a miss: the runner never reaches the network."""
    result = run_graph(STORY, "https://example.com/page", cache=RequestCache(tmp_path))
    assert not result.ok
    assert "not in the request cache" in result.error
    assert "example.com/page" in result.error


def test_without_a_cache_a_fetch_is_a_miss(tmp_path: Path) -> None:
    result = run_graph(STORY, "https://example.com/page")
    assert not result.ok
    assert "not in the request cache" in result.error


def test_a_udf_other_than_fetch_still_needs_a_host(tmp_path: Path) -> None:
    """The cache holds network answers, not the result of a host function."""
    story = {"nodes": {"store": [["udf", "store"]]}}
    result = run_graph(story, "x", cache=RequestCache(tmp_path))
    assert not result.ok
    assert "host function(s) store" in result.error


# ---------------------------------------------------------------- the commands


def test_snapshot_records_a_fetching_story(tmp_path: Path, capsys, monkeypatch) -> None:
    """`up2 snapshot` freezes a story that fetches, replaying the cached answer."""
    samples = tmp_path / "samples"
    directory = samples / DOMAIN / KEY / "a"
    directory.mkdir(parents=True)
    (directory / "input.txt").write_text("https://example.com/page", encoding="utf-8")
    path = write_json(tmp_path / "site.json", STORY)

    # The cache lives where the runner looks for it: the working directory's `.cache/requests/`.
    monkeypatch.chdir(tmp_path)
    cached(RequestCache())

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
    assert payload["value"] == {"title": "<HTML><TITLE>HELLO</TITLE></HTML>"}
    recorded = json.loads((directory / "expected.json").read_text(encoding="utf-8"))
    assert recorded == {"title": "<HTML><TITLE>HELLO</TITLE></HTML>"}


def test_snapshot_reports_a_miss(tmp_path: Path, capsys, monkeypatch) -> None:
    samples = tmp_path / "samples"
    directory = samples / DOMAIN / KEY / "a"
    directory.mkdir(parents=True)
    (directory / "input.txt").write_text("https://example.com/page", encoding="utf-8")
    path = write_json(tmp_path / "site.json", STORY)
    monkeypatch.chdir(tmp_path)

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
            ]
        )
        == EXIT_FAILED
    )
    assert "not in the request cache" in capsys.readouterr().err
    assert not (directory / "expected.json").exists()


def test_a_frozen_fetching_story_regresses_offline(tmp_path: Path, capsys, monkeypatch) -> None:
    """The whole point: the story is frozen once and regressed from the cache afterwards."""
    samples = tmp_path / "samples"
    directory = samples / DOMAIN / KEY / "a"
    directory.mkdir(parents=True)
    (directory / "input.txt").write_text("https://example.com/page", encoding="utf-8")
    path = write_json(tmp_path / "site.json", STORY)
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("UP2_HOME", str(home))
    monkeypatch.setenv("UP2_STORE", "file")
    cached(RequestCache())

    # Freeze it.
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
            ]
        )
        == EXIT_OK
    )
    capsys.readouterr()

    # Store the chain, so `up2 test` has something to regress.
    assert publish(tmp_path, samples, STORY, "--json") == EXIT_OK
    capsys.readouterr()

    # The cache is the only source of the answer: the regression passes without a network.
    assert main(["test", DOMAIN, KEY, "--tests-root", str(samples)]) == EXIT_OK
    assert "matches its samples" in capsys.readouterr().out

    # A changed page is caught: the cache answers with the old body, the product differs.
    (directory / "expected.json").write_text('{"title": "OTHER"}', encoding="utf-8")
    assert main(["test", DOMAIN, KEY, "--tests-root", str(samples)]) == EXIT_FAILED
    assert "/title" in capsys.readouterr().out
