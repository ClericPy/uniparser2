"""The cross-operator invariants: one place where a claim that spans operators is executed.

`up2 conformance` answers "does every declared `(operator, action)` have a case?". It cannot answer
"does the engine actually behave the way `01` says at the level **above** an operator" — and that
gap is how `type` came to be documented as a chain-tail JSON validator: each operator's own tests
agreed with the (wrong) spec, and nothing checked the rule that crosses them.

Every claim `01`/`02`/`03` make about *how a value flows* belongs here as an executable assertion,
so a spec line that no longer describes the engine turns red in one obvious place.

The rule for adding one: if a fact is stated in `docs/specs/` about something that involves **two or
more operators, or a boundary between layers**, it needs a case here — not only a case in the
operator's own file.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

from uniparser2 import (
    Failed,
    Ok,
    Up2Error,
    compile_field,
    eval_field,
    register_type,
    register_udf,
    run,
    unregister_type,
    unregister_udf,
)

COVERS_PAIRS: tuple[tuple[str, str], ...] = ()
"""This module asserts cross-operator rules, not one `(operator, action)` pair."""


@dataclass
class _Record:
    """A host object: not JSON, so it can only flow while the chain carries values as they are."""

    title: str
    size: int = 0


@pytest.fixture(autouse=True)
def _host_vocabulary() -> Iterator[None]:
    register_type("Record", _Record)
    register_udf("build", lambda: _Record(title="hi"))
    yield
    unregister_type("Record")
    unregister_udf("build")


# ---------------------------------------------------------------- a host object may flow


def _via_udf() -> Any:
    """A `udf` answers a host object.

    The function is registered **without an argument** so that ``["udf","build"]`` is a nullary call
    and the stage's value is the host object it answers, not the string it was handed. A udf that
    takes the DTO would overwrite the value with its own answer, which is the point: the value a
    stage carries is whatever the operator put there, whoever produced it.
    """
    return ["udf", "build"]


def _via_type() -> Any:
    """A `type` stage builds a host object."""
    return ["type", "Record"]


def _via_node() -> Any:
    """A `node` call hands back what the called node produced."""
    return ["node", "producer"]


PRODUCERS = pytest.mark.parametrize(
    ("producer", "story_extra"),
    [
        pytest.param(_via_udf(), {}, id="udf"),
        pytest.param(_via_type(), {}, id="type"),
        pytest.param(
            _via_node(),
            {"producer": [["py", "const", {"title": "hi"}], ["type", "Record"]]},
            id="node",
        ),
    ],
)


@PRODUCERS
def test_a_host_object_reaches_a_later_stage(
    producer: list[Any], story_extra: dict[str, Any]
) -> None:
    """`01` §4: a value that flows may be a host object — whichever operator produced it.

    This is the invariant `type` broke: it substituted the payload, so its object could not be read
    by a later stage while a `udf`'s could.
    """
    chain = [["py", "const", {"title": "hi"}], producer, ["py", "getattr", "title"]]
    story = {"nodes": {**story_extra, "a": chain}}
    assert run(story, "a") == "hi"


@PRODUCERS
def test_a_host_object_may_be_read_by_a_reference(
    producer: list[Any], story_extra: dict[str, Any]
) -> None:
    """A dotted reference walks a host object by attribute (`03` §8): the object was kept."""
    story = {
        "nodes": {
            **story_extra,
            "a": [
                ["py", "const", {"title": "hi"}],
                producer,
                ["ctx", "set", "locals._o"],
                ["ctx", "get", "locals._o.title"],
            ],
        }
    }
    assert run(story, "a") == "hi"


@PRODUCERS
def test_only_the_run_exit_requires_json(producer: list[Any], story_extra: dict[str, Any]) -> None:
    """A host object flows freely; the **exit** is the one place that packs it (`01` N5)."""
    story = {"nodes": {**story_extra, "a": [["py", "const", {"title": "hi"}], producer]}}
    with pytest.raises(Up2Error) as info:
        run(story, "a")
    assert info.value.diagnostic.code == "UP2-E2003"


def test_pack_is_called_at_one_place_only() -> None:
    """The exit is the single packing point (`01` N5): no operator and no stage packs.

    A source-level assertion on purpose — the point of the invariant is *where* the call is, and a
    behavioural test cannot tell "packed once" from "packed twice with the same answer".
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "uniparser2"
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "export.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("from", "import", "#")):
                continue
            if "pack(" in stripped and "packed" not in stripped:
                offenders.append(f"{path.relative_to(root)}:{number} {stripped}")
    assert offenders == [], f"only the run exit may pack, found: {offenders}"


# ---------------------------------------------------------------- an operator does no IO


def test_no_operator_performs_io_on_the_evaluate_path() -> None:
    """`01` I5: an operator's **evaluate** path is side-effect-free and IO-free.

    The rule binds evaluation, not start-up: `ops/code.py` resolves which engine binary to use in a
    lazily-cached probe (`_worker_binary`), which is allowed by I5's wording; what may never happen
    is a disk or network access *while a stage evaluates*. A behaviour test cannot see this, so the
    assertion reads the source: every function whose name starts with `evaluate` / `precompile` is
    scanned for an IO call.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "uniparser2" / "ops"
    banned_calls = {"open", "urlopen", "urlretrieve", "getenv", "mkdir"}
    # `scope.write_text` is `ctx`'s in-memory setter, not a file write: the receiver decides.
    fs_methods = {"write_text", "read_text", "unlink", "mkdir"}
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith(("evaluate", "precompile")):
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                name = ""
                if isinstance(inner.func, ast.Name):
                    name = inner.func.id
                elif isinstance(inner.func, ast.Attribute):
                    name = inner.func.attr
                receiver = ""
                if isinstance(inner.func, ast.Attribute):
                    receiver = ast.unparse(inner.func.value)
                if name in banned_calls or (name in fs_methods and "scope" not in receiver):
                    offenders.append(f"{path.name}:{inner.lineno} {node.name} calls {name}")
    assert offenders == [], f"an evaluate path may not touch the outside world, found: {offenders}"


# ---------------------------------------------------------------- the chain is data


def test_a_chain_round_trips_whatever_an_operator_adds() -> None:
    """`01` N2: `dumps(loads(x))` is a fixed point, for **every** registered operator.

    Drive it off the registry rather than a hand-written list: a new operator is covered the moment
    it is declared, which is the property the hand-written `tests/serialization` list lacks.
    """
    from uniparser2 import dumps, loads
    from uniparser2.core import registry

    checked = 0
    for item in registry.report():
        for action in item.actions:
            chain = [[str(item.name), str(action.name)]]
            once = dumps(loads(chain))
            assert dumps(loads(once)) == once, f"{item.name}.{action.name} is not a fixed point"
            checked += 1
    assert checked >= 12, "the registry reported fewer pairs than the operator set"


# ---------------------------------------------------------------- a query that matched nothing


def test_every_action_answers_a_value_or_a_failure_never_a_third_state() -> None:
    """`01` §4: only `Ok` and `Failed` exist, and an `Outcome` is always one of the two."""

    matched = compile_field([["css1", "text", "h1.none"]])
    outcome = eval_field(matched, "<html><body></body></html>")
    assert isinstance(outcome, (Ok, Failed))
    assert isinstance(outcome, Ok)
