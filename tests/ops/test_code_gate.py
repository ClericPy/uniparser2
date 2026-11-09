"""``code`` capability gate and packaging boundary (needs no sandbox runtime).

These cases are the only ones that run when the sandbox is **not installed**: `code` must be
unavailable at compile time (``UP2-E1107``), and the `all` extra must not drag it in along the way.
Behaviour cases live in ``test_code.py`` (the whole module skips when the dependency is missing).
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

import uniparser2 as up2
from uniparser2.core import registry

_CODE_OP = registry.get("code")
assert _CODE_OP is not None
_MISSING = registry.op_missing_deps(_CODE_OP)

_ROOT = Path(__file__).resolve().parents[2]


def _code(src: str, **extra: Any) -> Any:
    return [["code", {"src": src, **extra}]]


def _compile_error(chain: Any) -> tuple[str, str]:
    with pytest.raises(up2.Up2Error) as info:
        up2.compile_field(chain)
    return info.value.diagnostic.code, info.value.diagnostic.pointer


def test_code_extra_exists_and_is_not_in_all() -> None:
    """`code` is a standalone extra and **does not go into `all`**.

    Installing everything should not hand out code execution as a side effect.
    """
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    assert any(item.startswith("pydantic-monty") for item in extras["code"])
    assert "code" not in extras["all"][0]


def test_missing_dependency_blocks_at_compile_time(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_missing(instance: object, action: str) -> tuple[str, ...]:
        del instance, action
        return ("pydantic_monty",)  # pretend the sandbox runtime is not installed

    monkeypatch.setattr(registry, "action_missing_deps", fake_missing)
    code, _ = _compile_error(_code("len(obj)"))
    assert code == "UP2-E1107"
    with pytest.raises(up2.Up2Error) as info:
        up2.compile_field(_code("len(obj)"))
    assert any("uniparser2[code]" in hint for hint in info.value.diagnostic.allowed)


def test_operator_is_registered_with_single_action() -> None:
    instance = registry.get("code")
    assert instance is not None
    assert instance.arity == 2
    assert instance.slot_roles == ("source",)
    assert tuple(instance.actions) == ("run",)
    assert instance.requires == ("pydantic_monty",)


def test_ops_json_reports_availability(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The capability report must state availability **truthfully**.

    Installed is true; a missing dependency is false plus the list of who is missing.
    """
    from uniparser2.cli.main import main

    assert main(["ops", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    item = next(entry for entry in payload if entry["name"] == "code")
    assert item["available"] is (not _MISSING)
    assert item["requires"] == ["pydantic_monty"]
    assert item["missing"] == list(_MISSING)

    def fake_missing(instance: object) -> tuple[str, ...]:
        del instance
        return ("pydantic_monty",)

    # Operator-level availability looks at the operator's own dependency gate (the per-action entry
    # point is action_missing_deps).
    monkeypatch.setattr(registry, "op_missing_deps", fake_missing)
    monkeypatch.setattr(
        registry, "action_missing_deps", lambda instance, action: fake_missing(instance)
    )
    assert main(["ops", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    item = next(entry for entry in payload if entry["name"] == "code")
    assert item["available"] is False
    assert item["missing"] == ["pydantic_monty"]
    # The human-readable path must flag it too, not only --json.
    assert main(["ops"]) == 0
    assert "[unavailable]" in capsys.readouterr().out


def test_worker_binary_prefers_the_env_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """D8: by default pin the binary wrapped with the runtime **inside the environment**.

    It never searches `PATH` on its own. An explicit host configuration wins; when neither is
    present, the choice goes back to the upstream resolution order (``None`` is returned).
    """
    from types import SimpleNamespace

    from uniparser2.ops import code as code_op

    assert code_op.reset_policy().binary_path is None
    default = code_op._worker_binary()
    assert default is None or default.endswith(("monty.exe", "monty"))

    assert code_op.configure(binary_path="/custom/monty").binary_path == "/custom/monty"
    assert code_op._worker_binary() == "/custom/monty"
    code_op.reset_policy()

    monkeypatch.setattr(code_op, "sysconfig", SimpleNamespace(get_path=lambda name: None))
    assert code_op._worker_binary() is None
