"""The type registry: the host's type name → constructor table (design doc 03 §3).

A ``["type", name]`` stage validates a value against a **shape**, not a Python object: the host
registers a name → constructor pair, and the stage builds that constructor from the value at the
chain tail (``03`` §3.2). The constructor is a **validator**: it receives the JSON and the run
continues with the JSON (``03`` §3.3).

**Why the registration is not part of the bundle.** The registry is process-wide host state, exactly
like ``core.udfs``: the host installs its own vocabulary at start-up, and a story references it by
name only, so the bundle stays library-independent data (``03`` §3.1). Keeping it in the kernel also
keeps the check where the value exists — a name that no host registered fails at the stage that
declared it, with ``UP2-E1011`` naming the types that are registered.

**Built-in names need no registration** (``03`` §3.1): the JSON basics (``null`` / ``bool`` /
``str`` / ``int`` / ``float`` / ``list`` / ``dict``). ``list`` / ``dict`` are the product's own
kind, so they take it as it is (a dictionary product must keep its keys), while the scalar names go
through their Python constructor — the same coercion a host constructor would perform (``"int"`` on
``"2026"`` answers ``2026``).

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
    "call register_type(name, constructor) in the host before the run, or declare one of the names "
    "the kernel already knows (the JSON basics)"
)


class UnknownTypeError(Exception):
    """A step declares a ``type`` neither the host nor the built-ins register (``UP2-E1011``)."""

    def __init__(self, name: str) -> None:
        super().__init__(f"the type {name!r} is not registered")
        self.name = name


class TypeConstructionError(Exception):
    """A registered constructor rejected the product (``UP2-E2019``)."""

    def __init__(self, name: str, reason: str) -> None:
        super().__init__(reason)
        self.name = name
        self.reason = reason


def register_type(name: str, constructor: TypeConstructor) -> None:
    """Register (or replace) one type name. ``name`` is what a step writes as its ``type``.

    A registration **wins over the built-in names**, so a host may give ``dict`` or ``int`` a
    construction of its own (``03`` §3.1's closed set is what a step may declare with no
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


def get_type(name: str) -> TypeConstructor | None:
    """The constructor the **host** registered for ``name``, or ``None`` (built-ins included)."""
    return _TYPES.get(name)


def type_names() -> tuple[str, ...]:
    """Every name a step may declare today: the built-ins and the host's, sorted (`UP2-E1011`)."""
    return tuple(sorted(BUILTIN_TYPES | set(_TYPES)))


def build_type(name: str, product: Any) -> Any:
    """Build the declared type from the product at the step boundary (``03`` §3.2/§3.3).

    A dictionary product becomes ``Cls(**payload)`` and a list ``Cls(*items)``; anything else is
    handed to the constructor as it is, which is how a scalar-shaped type is validated. The caller
    checks that the result is still JSON: a constructor is a validator, not a container for objects.
    """
    constructor = _TYPES.get(name)
    if constructor is None:
        if name not in BUILTIN_TYPES:
            raise UnknownTypeError(name)
        return _builtin(name, product)
    try:
        return _call(constructor, product)
    except Exception as exc:  # any constructor failure is a coded failure of that step
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
    "build_type",
    "get_type",
    "register_type",
    "type_names",
    "unregister_type",
]
