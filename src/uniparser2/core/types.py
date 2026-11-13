"""The type registry: the host's type name → constructor table (design doc 03 §3).

A ``["type", name]`` stage builds a **shape**, not a Python object graph: the host registers a
name → constructor pair, and the stage constructs that type from the value at its position in the
chain (``03`` §3.2). The constructor is a **constructor**: whatever it answers is what the chain
carries on, so a container answer flows as a host object and the run's exit (``pack``) is the only
place JSON is required (``03`` §3.3).

**Why the registration is not part of the bundle.** The registry is host state, exactly like
``core.udfs``: the host installs its own vocabulary at start-up, and a story references it by name
only, so the bundle stays library-independent data (``03`` §3.1). Keeping it in the kernel also
keeps the check where the value exists — a name that no host registered fails at the stage that
declared it, with ``UP2-E1011`` naming the types that are registered.

**A run may carry its own table.** ``run(..., types={...})`` merges an overlay over the process-wide
one for that run only, the same way ``udfs={...}`` does; the overlay reaches the stage through
:attr:`core.refs.Scope.types`. Two runs in one process may therefore resolve one name differently.

**Built-in names need no registration** (``03`` §3.1): the JSON basics (``null`` / ``bool`` /
``str`` / ``int`` / ``float`` / ``list`` / ``dict``). ``list`` / ``dict`` take the value as it is (a
dictionary value must keep its keys), while the scalar names go through their Python constructor —
the same coercion a host constructor would perform (``"int"`` on ``"2026"`` answers ``2026``).

The module is **pure dictionary operations + one call**: no third-party import, no file read, no IO.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Final

type TypeConstructor = Callable[..., Any]
"""A registered constructor: a class (``Cls(**payload)``) or any callable of the product's parts."""

_TYPES: dict[str, TypeConstructor] = {}

BUILTIN_TYPES: Final[frozenset[str]] = frozenset(
    {"null", "bool", "str", "int", "float", "list", "dict"}
)
"""The names no host has to register (``03`` §3.1); a registration may shadow one deliberately."""

_SCALARS: Final[Mapping[str, Callable[[Any], Any]]] = {
    "bool": bool,
    "str": str,
    "int": int,
    "float": float,
}

UNREGISTERED_FIX: Final = (
    "call register_type(name, constructor) in the host, pass types={...} to run(), or declare one "
    "of the names the kernel already knows (the JSON basics)"
)


class UnknownTypeError(Exception):
    """A `type` stage declares a name neither the host nor the built-ins register.

    The failure is ``UP2-E1011``, naming the declared type and the names that are registered.
    """

    def __init__(self, name: str, known: tuple[str, ...] = ()) -> None:
        detail = f"the type {name!r} is not registered"
        if known:
            detail = f"{detail}; the registered names are: {', '.join(known)}"
        super().__init__(detail)
        self.name = name
        self.known = known


class TypeConstructionError(Exception):
    """A registered constructor rejected the product (``UP2-E2019``)."""

    def __init__(self, name: str, reason: str) -> None:
        super().__init__(reason)
        self.name = name
        self.reason = reason


def register_type(name: str, constructor: TypeConstructor) -> None:
    """Register (or replace) one type name. ``name`` is what a chain tail writes as its ``type``.

    A registration **wins over the built-in names**, so a host may give ``dict`` or ``int`` a
    construction of its own (``03`` §3.1's closed set is what a chain tail may declare with no
    registration, not a list the host cannot touch).
    """
    if not name.strip() or not callable(constructor):
        raise ValueError(
            f"register_type needs a non-empty name and a callable constructor, got {name!r}"
        )
    _TYPES[name] = constructor


def unregister_type(name: str) -> bool:
    """Remove one host-registered name; return whether it was really removed."""
    return _TYPES.pop(name, None) is not None


def all_types() -> dict[str, TypeConstructor]:
    """A copy of the process-wide table, for a run to merge its overlay over."""
    return dict(_TYPES)


def _effective(table: Mapping[str, TypeConstructor] | None) -> Mapping[str, TypeConstructor]:
    """The table a lookup reads: the run's own (already merged), or the process-wide one."""
    return _TYPES if table is None else table


def get_type(
    name: str, *, table: Mapping[str, TypeConstructor] | None = None
) -> TypeConstructor | None:
    """The constructor registered for ``name``, or ``None`` (built-ins included)."""
    return _effective(table).get(name)


def type_names(table: Mapping[str, TypeConstructor] | None = None) -> tuple[str, ...]:
    """Every name a `type` stage may declare today: the built-ins and the effective table's, sorted.

    The list is what ``UP2-E1011`` reports.
    """
    return tuple(sorted(BUILTIN_TYPES | set(_effective(table))))


def build_type(
    name: str,
    product: Any,
    /,
    *,
    table: Mapping[str, TypeConstructor] | None = None,
) -> Any:
    """Build the declared type from the value at a `type` stage (``03`` §3.2/§3.3).

    A dictionary value becomes ``Cls(**payload)`` and a list ``Cls(*items)``; anything else is
    handed to the constructor as it is, which is how a scalar-shaped type is built. The answer
    **is** the chain's new value — the caller carries it on; only the exit requires JSON.

    A built-in scalar name is a constructor too (``int("2026")``), so **every** refusal -- a host
    constructor raising and a built-in conversion failing alike -- is ``TypeConstructionError``
    (``UP2-E2019``); an unrepresentable value must not surface as an operator defect.
    """
    effective = _effective(table)
    constructor = effective.get(name)
    if constructor is None and name not in BUILTIN_TYPES:
        raise UnknownTypeError(name, type_names(effective))
    try:
        return _builtin(name, product) if constructor is None else _call(constructor, product)
    except Exception as exc:  # any constructor failure is a coded failure of that stage
        raise TypeConstructionError(name, f"{exc.__class__.__name__}: {exc}") from exc


def _call(constructor: TypeConstructor, product: Any) -> Any:
    """One constructor call: `Cls(**payload)` for a dict, `Cls(*items)` for a list (03 §3.2)."""
    match product:
        case Mapping():
            return constructor(**product)
        case list():
            return constructor(*product)
        case _:
            return constructor(product)


def _builtin(name: str, product: Any) -> Any:
    """A built-in name: `null` answers nothing, a scalar converts, a container is its own shape."""
    if name == "null":
        return None
    converter = _SCALARS.get(name)
    return product if converter is None else converter(product)


__all__ = [
    "BUILTIN_TYPES",
    "UNREGISTERED_FIX",
    "TypeConstructionError",
    "TypeConstructor",
    "UnknownTypeError",
    "all_types",
    "build_type",
    "get_type",
    "register_type",
    "type_names",
    "unregister_type",
]
