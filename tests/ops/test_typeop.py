"""The ``type`` stage: a chain-tail validation against the host type registry (design doc 03 §3)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

from uniparser2 import Up2Error, register_type, run, unregister_type
from uniparser2.core import registry

COVERS_PAIRS = (("type", "check"),)


@dataclass
class _Article:
    url: str
    title: str
    pub_time: str = ""


def _bad_shape(**payload: Any) -> Any:
    del payload
    return {1, 2}


@pytest.fixture(autouse=True)
def _types() -> Iterator[None]:
    register_type("Article", _Article)
    register_type("BadShape", _bad_shape)
    yield
    for name in ("Article", "BadShape"):
        unregister_type(name)


def _story(chain: Any) -> dict[str, Any]:
    return {"nodes": {"a": chain}}


def _run_error(chain: Any) -> Any:
    with pytest.raises(Up2Error) as info:
        run(_story(chain), "a")
    return info.value.diagnostic


def test_the_operator_is_registered() -> None:
    instance = registry.get("type")
    assert instance is not None
    assert instance.arity == 2


def test_a_valid_shape_passes_and_stays_json() -> None:
    assert run(_story([["py", "const", {"url": "u", "title": "t"}], ["type", "Article"]]), "a") == {
        "url": "u",
        "title": "t",
    }


def test_a_missing_key_is_e2019() -> None:
    diagnostic = _run_error([["py", "const", {"url": "u"}], ["type", "Article"]])
    assert diagnostic.code == "UP2-E2019"
    assert "title" in diagnostic.message


def test_an_unregistered_name_is_e1011() -> None:
    assert _run_error([["py", "const", {}], ["type", "Gone"]]).code == "UP2-E1011"


def test_a_non_json_answer_is_e2003() -> None:
    assert _run_error([["py", "const", {"url": "u"}], ["type", "BadShape"]]).code == "UP2-E2003"


def test_the_stage_must_be_last() -> None:
    with pytest.raises(Up2Error) as info:
        run(_story([["type", "Article"], ["py", "strip"]]), "a")
    assert info.value.diagnostic.code == "UP2-E1005"


def test_a_field_map_node_is_wrapped_by_a_node_call() -> None:
    story = {
        "nodes": {
            "a": [["node", "fields"], ["type", "Article"]],
            "fields": {"url": [["py", "const", "u"]], "title": [["py", "const", "t"]]},
        }
    }
    assert run(story, "a") == {"url": "u", "title": "t"}
