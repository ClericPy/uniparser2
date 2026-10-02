"""The story layer: compile a site bundle, then run it to its next suspension (design doc 03 §2-§5).

A **story** is a linear sequence of typed steps (`03` §2). Two things in it are not expressions but
control flow, and both live here rather than in an operator:

- a step whose ``type`` is ``Request`` / ``RequestBatch`` **suspends** the run, because the kernel
  performs no IO: the host sends the request(s) and sends the answer(s) back;
- ``next`` resolves which step receives those answers, and ``exit`` names the step whose products
  are the run's output.

The run loop is a **generator**: ``start`` compiles and drives to the first effect, ``run.next()``
reads it and ``run.send(answer)`` resumes. A generator keeps the interruptions out of the kernel's
data (no threads, no callbacks, still synchronous) while letting a fan-out whose receiving step is
itself a request nest correctly, since the nested suspension travels out through ``yield from``.

A ``Failed`` stage **raises** ``Up2Error`` carrying the stage's diagnostic: the effect vocabulary
has no failure member, and a run that could not produce a step's product must not hand the host a
plausible-looking effect.

A caller may pass a ``trace`` (`06` §5.1): every evaluated stage of every step is then recorded, the
step's name and its field-map key included, and every suspension is recorded as an effect event
carrying what the kernel handed the host. The trace is a debugging aid and never changes a run
(`03` §13 O6).
"""

from __future__ import annotations

import logging
from collections.abc import Generator, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Final, Literal

from .ast import CompiledField, Lit, Param
from .compile import compile_field, compile_field_map
from .errors import Failed, Missing, Up2Error, diag
from .evaluator import eval_field, resolve_params
from .export import pack
from .limits import MAX_STORY_STEPS
from .refs import RESERVED_ROOTS, Scope, is_ref_text, parse_ref
from .trace import EFFECT_BATCH, EFFECT_CALL, EFFECT_REQUEST, Trace, elapsed_ms, stamp
from .types import (
    UNREGISTERED_FIX,
    TypeConstructionError,
    UnknownTypeError,
    build_type,
    type_names,
)
from .values import type_name

logger = logging.getLogger("uniparser2")

REQUEST_TYPE: Final = "Request"
REQUEST_BATCH_TYPE: Final = "RequestBatch"
REQUEST_TYPES: Final = (REQUEST_TYPE, REQUEST_BATCH_TYPE)
LOCAL_PREFIX: Final = "_"
NEXT_KEY: Final = "next"
BATCH_ITEMS: Final = "items"
_PRODUCT_UNAVAILABLE: Final = object()
"""The value that travels beside "this step produced nothing" (a `Missing` product, `03` §9)."""
_BUNDLE_KEYS: Final = frozenset({"globals", "steps", "exit"})
_STEP_KEYS: Final = frozenset({"name", "type", "parse", "call", NEXT_KEY, "with"})
_UNVISITED: Final = 0
"""The flow node a walk has not reached yet."""
_ON_PATH: Final = 1
"""The flow node the walk is standing on: a step it enters again closes a loop."""
_WALKED: Final = 2
"""The flow node whose whole subtree the walk has already left -- it cannot close a loop."""

type Effect = (
    tuple[Literal["request"], Mapping[str, Any], str]
    | tuple[Literal["batch"], list[dict[str, Any]], str]
    | tuple[Literal["call"], str, Mapping[str, Any]]
    | tuple[Literal["done"], Any]
)
"""One suspension the host must answer, or the run's end (`03` §5).

``"request"`` / ``"batch"`` hand over the request(s) and the step that receives the answers;
``"call"`` hands over a host function and its arguments; ``"done"`` carries the run's output.
"""


@dataclass(frozen=True, slots=True)
class StoryStep:
    """One compiled step: what it runs, what it is called, and where its answers go."""

    name: str
    index: int
    type: str | None
    parse: CompiledField | Mapping[str, CompiledField] | None
    call: str | None
    with_: Mapping[str, Param]
    next: str | None
    pointer: str

    @property
    def is_request(self) -> bool:
        return self.type in REQUEST_TYPES


@dataclass(frozen=True, slots=True)
class CompiledStory:
    """A compiled bundle: the constants, the steps and the named exit."""

    globals: Mapping[str, Any]
    steps: tuple[StoryStep, ...]
    exit: str
    index: Mapping[str, int]
    source: Any


def compile_story(bundle: Any, /, *, pointer: str = "") -> CompiledStory:
    """Compile a story bundle; a bad bundle fails here, never halfway through a run (`N3`)."""
    if not isinstance(bundle, Mapping):
        raise _bad(f"a story must be a JSON object, got {type_name(bundle)}", pointer=pointer)
    unknown = sorted(str(key) for key in bundle if key not in _BUNDLE_KEYS)
    if unknown:
        raise _bad(
            f"unknown bundle keys: {', '.join(unknown)}",
            pointer=pointer,
            fix=(
                "a bundle carries `globals`, `steps` and `exit` — a parse rule is a step, so there "
                "is no `chains` table"
            ),
            allowed=tuple(sorted(_BUNDLE_KEYS)),
        )
    globals_map = _globals(bundle.get("globals"), pointer=f"{pointer}/globals")
    raw_steps = bundle.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise _bad(
            f"`steps` must be a non-empty array, got {type_name(raw_steps)}",
            pointer=f"{pointer}/steps",
            fix='declare at least one step: {"name": "records", "parse": {...}, "type": "Record"}',
        )
    if len(raw_steps) > MAX_STORY_STEPS:
        raise Up2Error(
            diag(
                "UP2-E1012",
                f"the story declares {len(raw_steps)} steps, over "
                f"MAX_STORY_STEPS={MAX_STORY_STEPS}",
                fix="split the flow into several stories, or fold steps into one field map",
                pointer=f"{pointer}/steps",
            )
        )
    names = _step_names(raw_steps, pointer=f"{pointer}/steps")
    steps = tuple(
        _compile_step(
            raw,
            name=name,
            index=position,
            names=names,
            pointer=f"{pointer}/steps/{position}",
        )
        for position, (raw, name) in enumerate(zip(raw_steps, names, strict=True))
    )
    exit_name = _exit_name(bundle.get("exit"), names, pointer=f"{pointer}/exit")
    _lint_flow(steps)
    logger.debug("compiled story: steps=%d exit=%s", len(steps), exit_name)
    return CompiledStory(
        globals=globals_map,
        steps=steps,
        exit=exit_name,
        index={name: position for position, name in enumerate(names)},
        source=bundle,
    )


def start(bundle: Any, value: Any = None, /, *, trace: Trace | None = None) -> StoryRun:
    """Compile a story and run it to the first suspension (`03` §5).

    ``trace`` is where the run records its events (`06` §5.1); a run without one records nothing.
    """
    return StoryRun(compile_story(bundle), value, trace=trace)


@dataclass(slots=True)
class _RunState:
    """What every step of one run shares: the story, its scope, the output and the trace."""

    story: CompiledStory
    scope: Scope
    output: list[Any]
    trace: Trace | None = None


class StoryRun:
    """One run of one story: ``next()`` reads the current effect, ``send()`` resumes it.

    The answer to a suspension resumes **this same run** — there is no hand-off, so a story is one
    flow from its first request to its exit product.

    One scope spans the whole run, so the run's materialization cache (`03` §6) lives exactly as
    long as the run does.
    """

    __slots__ = ("_done", "_drive", "_effect", "_state", "_value")

    def __init__(self, story: CompiledStory, value: Any, *, trace: Trace | None = None) -> None:
        self._value = value
        self._state = _RunState(
            story=story,
            scope=Scope(globals=story.globals, step_input=value),
            output=[],
            trace=trace,
        )
        self._drive = _drive(self._state, value)
        self._effect: Effect = next(self._drive)
        self._done = self._effect[0] == "done"

    @property
    def story(self) -> CompiledStory:
        """The compiled story this run executes."""
        return self._state.story

    @property
    def value(self) -> Any:
        """The value the run started from."""
        return self._value

    @property
    def scope(self) -> Scope:
        """The run's evaluation scope, which carries the run's materialization cache (`03` §6)."""
        return self._state.scope

    @property
    def trace(self) -> Trace | None:
        """The trace this run records into, or ``None`` when the caller asked for none."""
        return self._state.trace

    def next(self) -> Effect:
        """The current effect: the suspension the host must answer, or ``("done", product)``.

        Idempotent by design: the documented host loop reads the effect and then answers it.
        """
        return self._effect

    def send(self, answer: Any) -> Effect:
        """Resume the run with ``answer`` and return the next effect (or ``done``)."""
        if self._done:
            raise ValueError("the run is already done; there is no suspension to answer")
        self._effect = self._drive.send(answer)
        self._done = self._effect[0] == "done"
        return self._effect

    def close(self) -> None:
        """Release the run's generator (a run abandoned before ``done``)."""
        self._drive.close()


# ---------------------------------------------------------------- the run loop


def _drive(state: _RunState, value: Any) -> Generator[Effect, Any, None]:
    """The run loop: step through the bundle until it passes the last step.

    ``state.scope`` is the run's own scope, re-pointed at each step's input; it carries the run's
    materialization cache, so the cache lives exactly as long as the run (`03` §6).
    """
    pc = 0
    while pc < len(state.story.steps):
        pc, value, _ = yield from _step_product(state, pc, value)
    yield ("done", state.output)


def _step_product(
    state: _RunState,
    pc: int,
    value: Any,
    item: int | None = None,
) -> Generator[Effect, Any, tuple[int, Any, bool]]:
    """Run the step at ``pc``, resolving every suspension it causes.

    Returns the program counter to continue at, the value that continuation takes as its input, and
    whether the step produced a product at all (``False`` when its chain product was missing, `03`
    §9). A receiving step that itself produces a request is handled here, which is what makes a
    nested fan-out resume inside the same run.

    ``item`` is the fan-out result this evaluation belongs to (`06` §5.1): the position of a batch
    answer for a receiving step, and ``None`` for a step the linear flow reaches.
    """
    step = state.story.steps[pc]
    scope = state.scope
    trace = state.trace
    # `$in` names **this** step's input; a receiving step evaluated inside a fan-out sets it too,
    # which is why it is recorded here rather than by the loop that drives the run.
    scope.step_input = value
    if trace is not None:
        trace.enter(step.name, item=item)
    if step.call is not None:
        started_at = stamp(trace)
        arguments = _call_arguments(step, value, scope)
        _record_effect(
            trace,
            EFFECT_CALL,
            step=step.name,
            action=step.call,
            params=step.with_,
            incoming=value,
            handed_out=arguments,
            started_at=started_at,
        )
        product = yield ("call", step.call, arguments)
    else:
        product = _parse_product(step, value, scope, trace)
    if product is _PRODUCT_UNAVAILABLE:
        # A missing value is not a product (`03` §9): the step is skipped, exactly as a missing
        # field is absent from a field map — never `null` (`01` §4.2).
        return pc + 1, _PRODUCT_UNAVAILABLE, False
    product = _built_product(step, product)
    scope.products = {**scope.products, step.name: product}
    if step.name == state.story.exit:
        state.output.append(product)
    if not step.is_request:
        return pc + 1, product, True
    if step.type == REQUEST_TYPE:
        return (yield from _request_effect(state, step, value, product, item))
    return (yield from _batch_effect(state, step, value, product))


def _request_effect(
    state: _RunState,
    step: StoryStep,
    value: Any,
    product: Any,
    item: int | None,
) -> Generator[Effect, Any, tuple[int, Any, bool]]:
    """Hand one request over, then let the step `next` names continue the run (`03` §4.1).

    The receiving step may itself produce nothing: `next` names the step after it, so the run
    continues there instead of at a value that does not exist.
    """
    started_at = stamp(state.trace)
    request = _single_request(step, product)
    receiver = _receiver(state.story, step, product, position=0)
    _record_effect(
        state.trace,
        EFFECT_REQUEST,
        step=step.name,
        incoming=value,
        handed_out=request,
        started_at=started_at,
    )
    answer = yield ("request", request, receiver)
    return (yield from _step_product(state, state.story.index[receiver], answer, item))


def _batch_effect(
    state: _RunState, step: StoryStep, value: Any, product: Any
) -> Generator[Effect, Any, tuple[int, Any, bool]]:
    """Hand one batch of tasks over, then run the receiving step once per answer (`03` §4.1.1).

    The run continues past **everything** the fan-out ran: with a per-task `next` the receiving
    steps differ, so "the step after the default" could re-run a step that already answered.
    """
    started_at = stamp(state.trace)
    tasks, receivers = _batch_tasks(state.story, step, product)
    _record_effect(
        state.trace,
        EFFECT_BATCH,
        step=step.name,
        incoming=value,
        handed_out=tasks,
        started_at=started_at,
    )
    answer = yield ("batch", tasks, step.next or "")
    answers = _batch_answers(step, tasks, answer)
    received_products: list[Any] = []
    continuations: list[int] = []
    for position, (task_answer, receiver) in enumerate(zip(answers, receivers, strict=True)):
        next_pc, received, _ = yield from _step_product(
            state, state.story.index[receiver], task_answer, position
        )
        received_products.append(received)
        continuations.append(next_pc)
    return max(continuations), received_products, True


def _record_effect(
    trace: Trace | None,
    kind: str,
    *,
    step: str,
    incoming: Any,
    handed_out: Any,
    started_at: float,
    action: str | None = None,
    params: Mapping[str, Param] | None = None,
) -> None:
    """One suspension as a trace event; a run without a trace records nothing (`06` §5.1)."""
    if trace is None:
        return
    trace.effect(
        kind,
        step=step,
        action=action,
        params=params,
        incoming=incoming,
        handed_out=handed_out,
        ms=elapsed_ms(started_at),
    )


def _built_product(step: StoryStep, product: Any) -> Any:
    """The step boundary: the product must be JSON, and the declared type is built from it (§3.3).

    The product **continues as JSON** (``03`` §3.3): the JSON the constructor was handed is what the
    run carries on, so a validating container (a dataclass, a model) approves the shape without ever
    becoming the product — the constructor is a validator, not a place to put an object.

    An unregistered `type` is `UP2-E1011` and a constructor that refuses the product is `UP2-E2019`;
    either way the run stops **at this step**, which is the one that declared the shape.
    """
    if step.type is not None:
        try:
            built = build_type(step.type, product)
        except UnknownTypeError as exc:
            raise _failed(
                step,
                "UP2-E1011",
                f"the step declares type {exc.name!r}, which no host registered",
                UNREGISTERED_FIX,
                allowed=type_names(),
            ) from exc
        except TypeConstructionError as exc:
            raise _failed(
                step,
                "UP2-E2019",
                f"the type {exc.name!r} rejected the step product: {exc.reason}",
                "match the product's shape to the constructor, or fix the constructor",
            ) from exc
        carried = pack(built)
        # A constructor that answered a container rather than a JSON value (a dataclass, a pydantic
        # model) approved the payload it was handed: the run carries that JSON on, not the Python
        # object (`03` §3.3). A JSON answer is the product as it is; one that carries anything else
        # is left for `pack` below to refuse.
        product = built if not isinstance(carried, Failed) else _same_json(built, product)
    packed = pack(product)
    if isinstance(packed, Failed):
        raise _failed(step, packed.code, packed.reason, packed.fix)
    return product


def _same_json(built: Any, product: Any) -> Any:
    """The JSON a validating container approved, rebuilt from its own output (`03` §3.3).

    A dataclass (or a model) answers an object, which cannot be a product; what it **approved** is
    the payload it was handed, and that is what the run carries on. The mapping is rebuilt from the
    dataclass's own fields, and the payload's nested structures are preserved (a list stays a list),
    so the result is the JSON the constructor validated. A dataclass that answers a field the
    payload does not carry is not that payload: `pack` refuses the extra key at the same step
    (`UP2-E2003`).
    """
    if is_dataclass(built) and not isinstance(built, type):
        fields_of = {field.name: getattr(built, field.name) for field in fields(built)}
        return {key: _same_json(fields_of[key], source) for key, source in _items_of(product)}
    return built


def _items_of(product: Any) -> Any:
    """The key/value pairs of a mapping product; an empty view when the product is not a mapping."""
    return product.items() if isinstance(product, Mapping) else ()


def _single_request(step: StoryStep, product: Any) -> dict[str, Any]:
    """One request: the product without the kernel's own `next` key."""
    if not isinstance(product, Mapping):
        raise _failed(
            step,
            "UP2-E2005",
            f"the step declares type Request, but its product is {type_name(product)}",
            "build the request as a field map with a url key",
        )
    return _without_next(product)


def _batch_tasks(
    story: CompiledStory, step: StoryStep, product: Any
) -> tuple[list[dict[str, Any]], list[str]]:
    """Every task of a batch: what the host sees, and the receiving step of each one."""
    items = product.get(BATCH_ITEMS) if isinstance(product, Mapping) else None
    if not isinstance(items, list):
        raise _failed(
            step,
            "UP2-E2005",
            f"the step declares type {REQUEST_BATCH_TYPE}, but its product is "
            f"{type_name(product)} without an `items` list",
            'build the batch as {"items": [...]}, one request object per task',
        )
    tasks: list[dict[str, Any]] = []
    receivers: list[str] = []
    for position, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise _failed(
                step,
                "UP2-E2005",
                f"task {position} of the batch is {type_name(item)}, not a request object",
                "write every task as an object with a url key",
            )
        tasks.append(_without_next(item))
        receivers.append(_receiver(story, step, item, position=position))
    return tasks, receivers


def _without_next(task: Mapping[str, Any]) -> dict[str, Any]:
    """A task as the host sees it: the routing key is the kernel's, not the host's."""
    stripped = dict(task)
    stripped.pop(NEXT_KEY, None)
    return stripped


def _receiver(
    story: CompiledStory, step: StoryStep, task: Mapping[str, Any], *, position: int
) -> str:
    """The step that receives one answer: the task's own `next`, else the step's default."""
    name = task.get(NEXT_KEY) or step.next or ""
    if name not in story.index:
        raise _failed(
            step,
            "UP2-E1016",
            f"task {position} routes to {name!r}, which is not a step of this story",
            "point the task at a declared step",
        )
    return name


def _batch_answers(step: StoryStep, tasks: Sequence[Mapping[str, Any]], answer: Any) -> list[Any]:
    """The host's answers, one per task; a mismatched answer is a host bug, not a chain failure."""
    answers = list(answer) if _is_sequence(answer) else [answer]
    if len(answers) != len(tasks):
        raise ValueError(
            f"the batch of step {step.name!r} has {len(tasks)} tasks, so send() needs {len(tasks)} "
            f"answers in order, got {len(answers)}"
        )
    return answers


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


# ---------------------------------------------------------------- one step's work


def _parse_product(step: StoryStep, value: Any, scope: Scope, trace: Trace | None) -> Any:
    """Evaluate a step's `parse`: a chain produces one value, a field map one dictionary.

    ``scope`` is the run's scope, from which this step's field chains see the run's materialization
    cache (`03` §6) and the products the run has recorded so far.
    """
    if isinstance(step.parse, Mapping):
        return _field_map_product(step, step.parse, value, scope, trace)
    if step.parse is None:  # pragma: no cover - compile time guarantees parse or call
        raise _failed(step, "UP2-E1005", "the step has neither parse nor call", "declare one")
    outcome = eval_field(step.parse, value, scope=scope, trace=trace)
    if isinstance(outcome, Failed):
        raise _from_failed(step, outcome)
    if isinstance(outcome, Missing):
        # A missing value is not an error and not a product (`03` §9): the step is skipped, the same
        # way a missing field is absent from a field map (`01` §4.2).
        return _PRODUCT_UNAVAILABLE
    return outcome.value


def _field_map_product(
    step: StoryStep,
    fields: Mapping[str, CompiledField],
    value: Any,
    scope: Scope,
    trace: Trace | None,
) -> dict[str, Any]:
    """One dictionary from a field map: a `_` field is a local, a missing field is dropped.

    Every chain of the map was compiled with its own field name, which is what the trace reports as
    `field` (`06` §5.1), so the two fields of one map stay apart.
    """
    row: dict[str, Any] = {}
    for name, chain in fields.items():
        outcome = eval_field(chain, value, scope=scope, trace=trace)
        if isinstance(outcome, Failed):
            raise _from_failed(step, outcome)
        if isinstance(outcome, Missing):
            continue
        if name.startswith(LOCAL_PREFIX):
            scope.write_local((name,), outcome.value)
        else:
            row[name] = outcome.value
    return row


def _call_arguments(step: StoryStep, value: Any, scope: Scope) -> dict[str, Any]:
    """Resolve a `call` step's `with` arguments (the same leaves as an operator's parameter)."""
    resolved = resolve_params(step.with_, scope)
    if isinstance(resolved, Mapping):
        return dict(resolved)
    if isinstance(resolved, Failed):
        raise _from_failed(step, resolved)
    raise _failed(step, "UP2-E2005", "a call argument is missing", "make it present first")


# ---------------------------------------------------------------- compile time


def _compile_step(
    raw: Any,
    *,
    name: str,
    index: int,
    names: tuple[str, ...],
    pointer: str,
) -> StoryStep:
    if not isinstance(raw, Mapping):
        raise _bad(f"step {index} must be an object, got {type_name(raw)}", pointer=pointer)
    unknown = sorted(str(key) for key in raw if key not in _STEP_KEYS)
    if unknown:
        raise _bad(
            f"unknown step keys: {', '.join(unknown)}",
            pointer=pointer,
            fix="a step carries name / type / parse / call / next / with",
            allowed=tuple(sorted(_STEP_KEYS)),
        )
    declared_type = raw.get("type")
    if declared_type is not None and (not isinstance(declared_type, str) or not declared_type):
        raise _bad(
            f"`type` must be a non-empty string, got {declared_type!r}",
            pointer=f"{pointer}/type",
        )
    parse = raw.get("parse")
    call = raw.get("call")
    if (parse is None) == (call is None):
        raise _bad(
            "a step declares exactly one of `parse` and `call`",
            pointer=pointer,
            fix='write "parse": {...} for extraction, or "call": "host.fn" for a host function',
        )
    if "with" in raw and call is None:
        raise _bad("`with` only belongs to a `call` step", pointer=f"{pointer}/with")
    if call is not None and (not isinstance(call, str) or not call):
        raise _bad(f"`call` must name a host function, got {call!r}", pointer=f"{pointer}/call")
    others = tuple(item for item in names if item != name)
    compiled_parse: CompiledField | Mapping[str, CompiledField] | None = None
    if parse is not None:
        compiled_parse = (
            compile_field_map("parse", parse, products=others, pointer=f"{pointer}/parse")
            if isinstance(parse, Mapping)
            else compile_field(parse, products=others, pointer=f"{pointer}/parse")
        )
    return StoryStep(
        name=name,
        index=index,
        type=declared_type,
        parse=compiled_parse,
        call=call,
        with_=_with_of(raw, pointer=pointer),
        next=_next_of(raw, declared_type, names, pointer=pointer),
        pointer=pointer,
    )


def _next_of(
    raw: Mapping[str, Any], declared_type: str | None, names: tuple[str, ...], *, pointer: str
) -> str | None:
    """`next` is required on a request step and refused everywhere else (`03` §4.1)."""
    declared = raw.get(NEXT_KEY)
    if declared_type not in REQUEST_TYPES:
        if declared is not None:
            raise _bad(
                f"`next` belongs to a Request / RequestBatch step, and this step's type is "
                f"{declared_type!r}",
                pointer=f"{pointer}/{NEXT_KEY}",
            )
        return None
    if not isinstance(declared, str) or not declared:
        raise _bad(
            f"a step whose type is {declared_type} must declare `next`, naming the step that "
            "receives the responses",
            pointer=f"{pointer}/{NEXT_KEY}",
            fix="name a step of this story",
            allowed=names,
        )
    if declared not in names:
        raise Up2Error(
            diag(
                "UP2-E1016",
                f"`next` names {declared!r}, which is not a step of this story",
                fix="name a declared step",
                pointer=f"{pointer}/{NEXT_KEY}",
                allowed=names,
            )
        )
    return declared


def _with_of(raw: Mapping[str, Any], *, pointer: str) -> Mapping[str, Param]:
    """A `call`'s arguments: a mapping of name to a `ref_or_literal` leaf (`03` §13 O2)."""
    declared = raw.get("with")
    if declared is None:
        return {}
    if not isinstance(declared, Mapping):
        raise _bad(
            f"`with` must be an object of arguments, got {type_name(declared)}",
            pointer=f"{pointer}/with",
        )
    return {
        str(key): parse_ref(item, pointer=f"{pointer}/with/{key}")
        if is_ref_text(item)
        else Lit(item)
        for key, item in declared.items()
    }


def _step_names(raw_steps: list[Any], *, pointer: str) -> tuple[str, ...]:
    """Every step's name: non-empty, unique, and not a reserved reference root (`UP2-E1009`)."""
    names: list[str] = []
    for position, raw in enumerate(raw_steps):
        where = f"{pointer}/{position}"
        if not isinstance(raw, Mapping):
            raise _bad(f"step {position} must be an object, got {type_name(raw)}", pointer=where)
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise _bad(
                f"every step declares a non-empty `name`, got {name!r}",
                pointer=f"{where}/name",
                fix='name the step, e.g. "records"',
            )
        if name in RESERVED_ROOTS:
            raise Up2Error(
                diag(
                    "UP2-E1009",
                    f"the step name {name!r} is a reserved reference root",
                    fix="rename the step; the reserved roots are used by references",
                    pointer=f"{where}/name",
                    allowed=RESERVED_ROOTS,
                )
            )
        if name in names:
            raise Up2Error(
                diag(
                    "UP2-E1009",
                    f"the step name {name!r} is declared twice",
                    fix="give every step a unique name",
                    pointer=f"{where}/name",
                )
            )
        names.append(name)
    return tuple(names)


def _exit_name(raw: Any, names: tuple[str, ...], *, pointer: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise _bad(
            f"`exit` must name the step whose products are the run's output, got {raw!r}",
            pointer=pointer,
            fix="name a step of this story; with jumps the last step is not unique",
            allowed=names,
        )
    if raw not in names:
        raise Up2Error(
            diag(
                "UP2-E1016",
                f"`exit` names {raw!r}, which is not a step of this story",
                fix="name a declared step",
                pointer=pointer,
                allowed=names,
            )
        )
    return raw


def _lint_flow(steps: tuple[StoryStep, ...]) -> None:
    """Reject a story whose steps can lead the run back into a step it is already executing (`L12`).

    The run's only way forward is the program counter: the step after this one, or the step a
    request's `next` names. Both are drawn in one graph, over the steps and from the first one, and
    a node the walk enters twice is a loop the run can take -- a story the host would have to
    interrupt rather than finish. Every backward `next` the samples use (a fan-out whose answers
    are parsed by a step written earlier, the task-override pattern) is accepted: its target cannot
    reach the jumping step again, so no node is entered twice.
    """
    walk = _LoopWalk(steps)
    for position in range(len(steps)):
        closed = walk.enter(position)
        if closed is not None:
            raise _cycle(steps, closed)


class _LoopWalk:
    """One depth-first walk of a story's flow: the positions of the first loop found, or ``None``.

    ``flow`` holds the program counter's own edge per step (see ``_lint_flow``); ``path`` is the
    steps the walk is currently standing on, so a successor already on it closes a loop and a
    successor it has left cannot.
    """

    __slots__ = ("_colour", "_flow", "_index", "_path")

    def __init__(self, steps: tuple[StoryStep, ...]) -> None:
        self._flow = [
            [step.next]
            if step.next is not None
            else ([steps[position + 1].name] if position + 1 < len(steps) else [])
            for position, step in enumerate(steps)
        ]
        self._index = {step.name: position for position, step in enumerate(steps)}
        self._colour = [_UNVISITED] * len(steps)
        self._path: list[int] = []

    def enter(self, node: int) -> list[int] | None:
        """Walk ``node`` unless it has been walked already; the loop's positions, or ``None``."""
        if self._colour[node] != _UNVISITED:
            return None
        return self._walk(node)

    def _walk(self, node: int) -> list[int] | None:
        self._colour[node] = _ON_PATH
        self._path.append(node)
        loop = self._first_loop(node)
        self._path.pop()
        self._colour[node] = _WALKED
        return loop

    def _first_loop(self, node: int) -> list[int] | None:
        """The loop one of ``node``'s successors closes, in travel order, or ``None``."""
        for successor in self._flow[node]:
            target = self._index[successor]
            if self._colour[target] == _ON_PATH:
                return [*self._path[self._path.index(target) :], target]
            closed = self._walk(target) if self._colour[target] == _UNVISITED else None
            if closed is not None:
                return closed
        return None


def _cycle(steps: tuple[StoryStep, ...], closed: list[int]) -> Up2Error:
    """The diagnostic for one loop: where it closes, and every step the run passes in order."""
    loop = [steps[position] for position in sorted(set(closed))]
    travel = " -> ".join([*(step.name for step in loop), loop[0].name])
    # The pointer names the backward jump: of the loop's jumps, the one latest in array order is the
    # one that runs into the region it came from -- the transition to break.
    jumper = [step for step in loop if step.next is not None][-1]
    return Up2Error(
        diag(
            "UP2-E1017",
            f"the flow of this story closes a loop: {travel}",
            fix=(
                f"point `next` at a step that runs after {jumper.name!r}, or take the step that "
                "closes the loop out of it"
            ),
            pointer=f"{jumper.pointer}/{NEXT_KEY}",
        )
    )


def _globals(raw: Any, *, pointer: str) -> Mapping[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise _bad(f"`globals` must be an object, got {type_name(raw)}", pointer=pointer)
    return dict(raw)


def _bad(message: str, *, pointer: str, fix: str = "", allowed: tuple[str, ...] = ()) -> Up2Error:
    return Up2Error(diag("UP2-E1005", message, fix=fix, pointer=pointer, allowed=allowed))


def _failed(
    step: StoryStep,
    code: str,
    reason: str,
    fix: str,
    *,
    allowed: tuple[str, ...] = (),
) -> Up2Error:
    return Up2Error(diag(code, reason, fix=fix, pointer=step.pointer, allowed=allowed))


def _from_failed(step: StoryStep, failed: Failed) -> Up2Error:
    """A step that cannot produce its product stops the run with the stage's own diagnostic."""
    return Up2Error(diag(failed.code, failed.reason, fix=failed.fix, pointer=step.pointer))


__all__ = [
    "CompiledStory",
    "Effect",
    "StoryRun",
    "StoryStep",
    "compile_story",
    "start",
]
