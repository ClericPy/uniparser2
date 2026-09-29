"""Operator registry (design doc 01 §7, 02 §1-§4).

Three disciplines:
1. **Explicit registration** (the ``@op`` decorator), never implicit discovery through
   ``__subclasses__`` -- a subclass that was never imported would silently vanish from the
   registry.
2. **Probe dependencies, do not import them** (``importlib.util.find_spec``). An operator whose
   dependency is missing **keeps its declaration** but is marked unavailable, which is what makes
   ``UP2-E1107`` and an install command possible (more diagnostic value than dropping out of the
   registry).
3. **Actions are a table** (``actions``), not if/else scattered around; that table drives
   validation, the capability report, and ``up2 conformance --check``.
"""

from __future__ import annotations

import importlib.util
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar, Final

from .ast import MAX_STAGE_LEN, Param
from .errors import Outcome, Up2Error, diag
from .refs import Scope


class Kind(StrEnum):
    """How a parameter is resolved (02 §3.2). Ambiguity exists only in ``REF_OR_LITERAL``."""

    REF = "ref"
    LITERAL = "literal"
    REF_OR_LITERAL = "ref_or_literal"


class ParamForm(StrEnum):
    """How slot 3 of an action is written, from the parameters it still has to fill (02 §4)."""

    NONE = "none"
    VALUE = "value"
    NAMED = "named"


@dataclass(frozen=True, slots=True)
class ParamSpec:
    """The declaration of one named parameter."""

    name: str
    kind: Kind
    required: bool = True
    default: Any = None


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """The declaration of one action.

    ``requires`` holds **action-level** dependencies (``py.html_to_markdown``, for example).
    """

    name: str
    summary: str = ""
    params: tuple[ParamSpec, ...] = ()
    requires: tuple[str, ...] = ()
    accepts_missing: bool = False


@dataclass(frozen=True, slots=True)
class ParamReport:
    name: str
    kind: str
    required: bool
    default: Any = None


@dataclass(frozen=True, slots=True)
class ActionReport:
    name: str
    summary: str
    available: bool
    requires: tuple[str, ...]
    missing: tuple[str, ...]
    accepts_missing: bool
    params: tuple[ParamReport, ...]
    param_form: ParamForm


@dataclass(frozen=True, slots=True)
class OpReport:
    name: str
    aliases: tuple[str, ...]
    summary: str
    arity: int
    action_slot: int | None
    slots: tuple[str, ...]
    available: bool
    requires: tuple[str, ...]
    missing: tuple[str, ...]
    actions: tuple[ActionReport, ...]


@dataclass(frozen=True, slots=True)
class Call:
    """Every input of one operator call.

    A context object rather than a long parameter list, so fields can be added later.
    """

    value: Any
    action: str
    params: Mapping[str, Any]
    payload: Any
    scope: Scope


class Op(ABC):
    """Operator base class. A subclass only declares the ``actions`` table and ``evaluate``."""

    name: ClassVar[str] = ""
    aliases: ClassVar[tuple[str, ...]] = ()
    summary: ClassVar[str] = ""
    requires: ClassVar[tuple[str, ...]] = ()
    dynamic_actions: ClassVar[bool] = False
    """The action space is decided by the host (the function names of ``udf``, for example).

    Conformance declares its contract coverage with ``*``.
    """
    arity: ClassVar[int] = 3
    """Stage length, which **must be exactly equal** (2 or 3 slots)."""
    slot_roles: ClassVar[tuple[str, ...]] = ("action", "parameter")
    """The **role names** of slot 2 / slot 3, printed by ``up2 ops`` and by error hints.

    Length = ``arity - 1``.

    The slot shape is **uniform across all operators** (see design doc 02 §1): slot 2 = action (the
    action enum declared by that operator), slot 3 = parameter (selector / regex / XPath / function
    argument, any value); an operator with a single action is written with two slots only.
    """
    actions: ClassVar[Mapping[str, ActionSpec]] = {}

    @property
    def action_slot(self) -> int | None:
        """The slot carrying the action (0-based): slot 2 for a 3-slot operator, none for 2."""
        return 1 if self.arity == MAX_STAGE_LEN else None

    @property
    def param_slot(self) -> int:
        """The slot carrying the parameter (0-based): slot 3 for a 3-slot operator, slot 2 for 2."""
        return self.arity - 1

    def resolve_action(self, action_text: Any, *, pointer: str = "") -> str:
        """Action text -> canonical action name.

        The text comes from the :attr:`action_slot` position; an operator whose ``action_slot`` is
        ``None`` receives ``None``. ``pointer`` is the JSON Pointer of the action slot (such as
        ``/0/1``), used to locate the diagnostic. By default the text must be present in the action
        table (the reserved action set is a closed enum).
        """
        text = action_text if isinstance(action_text, str) else repr(action_text)
        if text not in self.actions:
            raise Up2Error(
                diag(
                    "UP2-E1002",
                    f"operator {self.name!r} does not know action {text!r}",
                    fix="use one of the following legal actions",
                    pointer=pointer,
                    allowed=tuple(sorted(self.actions)),
                )
            )
        return text

    def params_source(self, action_text: Any, param_text: Any) -> Any:
        """Where the parameters come from: by default the raw **parameter slot** text."""
        del action_text
        return param_text

    def action_spec(self, action: str) -> ActionSpec:
        """Return the schema of an action.

        Operators with a dynamic action space override it instead of using the static table.
        """
        return self.actions[action]

    def action_params(self, action: str, action_text: Any) -> Mapping[str, Param]:
        """**Parameters carried by the action slot itself**.

        ``css``'s ``@href`` binds ``href`` to ``attr``, for example. The returned keys are supplied
        by the action slot; the parameter slot only covers the remaining parameters.
        """
        del action, action_text
        return {}

    def dynamic_action_summary(self) -> str:
        """The description a ``dynamic_actions`` operator shows to ``up2 ops``."""
        return "registered by the host (register_udf / entry points)"

    def precompile(self, action: str, params: Mapping[str, Param], *, pointer: str = "") -> Any:
        """Precompile; only unresolved literals and references are visible. No product by default.

        ``pointer`` is the **JSON Pointer prefix of the parameter slot** (such as ``/0/1``), which
        lets an operator build a diagnostic location precise down to the parameter name
        (``/0/1/pattern``).
        """
        del action, params, pointer
        return None

    @abstractmethod
    def evaluate(self, call: Call) -> Outcome:
        """Evaluate. ``call.params`` holds **resolved** values (the references are already read)."""


_REGISTRY: dict[str, Op] = {}

DYNAMIC_ACTION_MARK: Final = "*"
"""The action placeholder of a ``dynamic_actions`` operator in conformance.

It is produced by ``declared_actions``.
"""

INSTALL_HINTS: dict[str, str] = {
    "selectolax": 'uv add "uniparser2[html]"',
    "lxml": 'uv add "uniparser2[xml]"',
    "jmespath": 'uv add "uniparser2[json]"',
    "dateparser": 'uv add "uniparser2[time]"',
    "html_to_markdown": 'uv add "uniparser2[md]"',
    "pywebview": 'uv add "uniparser2[ui]"',
    "pydantic_monty": 'uv add "uniparser2[code]"',
}


def install_hints(modules: Iterable[str]) -> tuple[str, ...]:
    """Install commands for missing dependencies (the ``allowed`` of ``UP2-E1107``)."""
    hints = [INSTALL_HINTS.get(module, f"uv add {module}") for module in modules]
    return tuple(dict.fromkeys(hints))


def register(op_cls: type[Op]) -> type[Op]:
    """Register an operator class (name + aliases). **Two phases**: validate, then fill the table.

    Validating everything before writing anything keeps a half-finished registration from
    polluting the registry. A duplicate name is a programming error and raises immediately
    (following the "transactional injection" stance of essence §A10).
    """
    instance = op_cls()
    registered_names = (instance.name, *instance.aliases)
    if not instance.name:
        raise ValueError(f"{op_cls.__name__} does not declare name")
    for name in registered_names:
        if not name:
            raise ValueError(f"{op_cls.__name__} has an empty alias")
        existing = _REGISTRY.get(name)
        if existing is not None and type(existing) is not op_cls:
            raise ValueError(
                f"operator name {name!r} is already taken by {type(existing).__name__}"
            )
    for name in registered_names:
        _REGISTRY[name] = instance
    return op_cls


def op(name: str, /, *, aliases: Sequence[str] = ()) -> Callable[[type[Op]], type[Op]]:
    """``@op("re")``: declare the name/aliases and register."""

    def decorate(cls: type[Op]) -> type[Op]:
        cls.name = name
        cls.aliases = tuple(aliases)
        return register(cls)

    return decorate


def get(name: str) -> Op | None:
    """Get an operator instance by name or alias."""
    return _REGISTRY.get(name)


def names() -> tuple[str, ...]:
    """Every resolvable name (aliases included), sorted."""
    return tuple(sorted(_REGISTRY))


def canonical_names() -> tuple[str, ...]:
    """Canonical operator names (aliases excluded), sorted."""
    return tuple(sorted({instance.name for instance in _REGISTRY.values()}))


def declared_actions() -> dict[str, tuple[str, ...]]:
    """Canonical operator name -> action names (sorted). One of the conformance reference sets.

    The action space of a ``dynamic_actions`` operator (``udf``) is decided by the host, so it is
    declared here as ``*``: what is required of it is that "the contract has cases" (an
    unregistered name raises ``UP2-E1010``, a registered one can be called), not one case per
    function name.
    """
    return {
        instance.name: (
            (DYNAMIC_ACTION_MARK,) if instance.dynamic_actions else tuple(sorted(instance.actions))
        )
        for instance in _unique_ops()
    }


def declared_pairs() -> frozenset[tuple[str, str]]:
    """All declared ``(operator, action)`` pairs. Conformance uses them to compute the uncovered."""
    return frozenset(
        (op_name, action) for op_name, actions in declared_actions().items() for action in actions
    )


def missing_deps(names_to_check: Iterable[str]) -> tuple[str, ...]:
    """Probe for missing dependencies (without triggering an import)."""
    missing: list[str] = []
    for module in names_to_check:
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append(module)
    return tuple(missing)


def op_missing_deps(instance: Op) -> tuple[str, ...]:
    """Operator-level missing dependencies (any missing ``requires`` entry makes it unavailable)."""
    return missing_deps(instance.requires)


def action_missing_deps(instance: Op, action: str) -> tuple[str, ...]:
    """The missing dependencies of an action (operator level + action level)."""
    spec = instance.actions.get(action)
    per_action = spec.requires if spec is not None else ()
    return tuple(dict.fromkeys((*op_missing_deps(instance), *missing_deps(per_action))))


def action_available(instance: Op, action: str) -> bool:
    return not action_missing_deps(instance, action)


def _unique_ops() -> tuple[Op, ...]:
    seen: dict[int, Op] = {}
    for instance in _REGISTRY.values():
        seen.setdefault(id(instance), instance)
    return tuple(seen[key] for key in sorted(seen))


def _param_form(instance: Op, action: str) -> ParamForm:
    """The shape of slot 3, from the parameters the action still has to fill.

    The subtraction mirrors compilation: a parameter the action slot itself provides (``css``'s
    ``@<attribute>`` providing ``attr``) is never written in slot 3.
    """
    spec = instance.action_spec(action)
    preset = instance.action_params(action, action)
    active = [param for param in spec.params if param.name not in preset]
    if not active:
        return ParamForm.NONE
    if len(active) == 1:
        return ParamForm.VALUE
    return ParamForm.NAMED


def report() -> tuple[OpReport, ...]:
    """The data source of ``up2 ops``: the operators' self-reported capabilities.

    An LLM should read it before drafting a chain.
    """
    reports: list[OpReport] = []
    for instance in sorted(_unique_ops(), key=lambda item: item.name):
        op_missing = op_missing_deps(instance)
        actions: list[ActionReport] = []
        if instance.dynamic_actions:
            actions.append(
                ActionReport(
                    name=DYNAMIC_ACTION_MARK,
                    summary=instance.dynamic_action_summary(),
                    available=not op_missing,
                    requires=instance.requires,
                    missing=op_missing,
                    accepts_missing=False,
                    params=(),
                    param_form=_param_form(instance, DYNAMIC_ACTION_MARK),
                )
            )
        for action_name in sorted(instance.actions):
            spec = instance.actions[action_name]
            action_missing = tuple(dict.fromkeys((*op_missing, *missing_deps(spec.requires))))
            actions.append(
                ActionReport(
                    name=spec.name,
                    summary=spec.summary,
                    available=not action_missing,
                    requires=tuple(dict.fromkeys((*instance.requires, *spec.requires))),
                    missing=action_missing,
                    accepts_missing=spec.accepts_missing,
                    params=tuple(
                        ParamReport(
                            name=param.name,
                            kind=str(param.kind),
                            required=param.required,
                            default=param.default,
                        )
                        for param in spec.params
                    ),
                    param_form=_param_form(instance, action_name),
                )
            )
        reports.append(
            OpReport(
                name=instance.name,
                aliases=tuple(instance.aliases),
                summary=instance.summary,
                arity=instance.arity,
                action_slot=instance.action_slot,
                slots=instance.slot_roles,
                available=not op_missing,
                requires=instance.requires,
                missing=op_missing,
                actions=tuple(actions),
            )
        )
    return tuple(reports)


def report_dicts() -> list[dict[str, Any]]:
    """A JSON-friendly form of ``report()``."""
    payload: list[dict[str, Any]] = []
    for item in report():
        payload.append(
            {
                "name": item.name,
                "aliases": list(item.aliases),
                "summary": item.summary,
                "arity": item.arity,
                "action_slot": item.action_slot,
                "slots": list(item.slots),
                "available": item.available,
                "requires": list(item.requires),
                "missing": list(item.missing),
                "actions": [
                    {
                        "name": action.name,
                        "summary": action.summary,
                        "available": action.available,
                        "requires": list(action.requires),
                        "missing": list(action.missing),
                        "accepts_missing": action.accepts_missing,
                        "param_form": str(action.param_form),
                        "params": [
                            {
                                "name": param.name,
                                "kind": param.kind,
                                "required": param.required,
                                "default": param.default,
                            }
                            for param in action.params
                        ],
                    }
                    for action in item.actions
                ],
            }
        )
    return payload
