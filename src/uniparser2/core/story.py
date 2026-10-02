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
"""

from __future__ import annotations

import logging
from collections.abc import Generator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from .ast import CompiledField, Lit, Param
from .compile import compile_field, compile_field_map
from .errors import Failed, Missing, Up2Error, diag
from .evaluator import eval_field, resolve_params
from .export import pack
from .limits import MAX_STORY_STEPS
from .refs import RESERVED_ROOTS, Scope, is_ref_text, parse_ref
from .values import type_name

logger = logging.getLogger("uniparser2")

REQUEST_TYPE: Final = "Request"
REQUEST_BATCH_TYPE: Final = "RequestBatch"
REQUEST_TYPES: Final = (REQUEST_TYPE, REQUEST_BATCH_TYPE)
LOCAL_PREFIX: Final = "_"
NEXT_KEY: Final = "next"
BATCH_ITEMS: Final = "items"
_BUNDLE_KEYS: Final = frozenset({"globals", "steps", "exit"})
_STEP_KEYS: Final = frozenset({"name", "type", "parse", "call", NEXT_KEY, "with"})

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
    logger.debug("compiled story: steps=%d exit=%s", len(steps), exit_name)
    return CompiledStory(
        globals=globals_map,
        steps=steps,
        exit=exit_name,
        index={name: position for position, name in enumerate(names)},
        source=bundle,
    )


def start(bundle: Any, value: Any = None, /) -> StoryRun:
    """Compile a story and run it to the first suspension (`03` §5)."""
    return StoryRun(compile_story(bundle), value)


class StoryRun:
    """One run of one story: ``next()`` reads the current effect, ``send()`` resumes it.

    The answer to a suspension resumes **this same run** — there is no hand-off, so a story is one
    flow from its first request to its exit product.
    """

    __slots__ = ("_done", "_drive", "_effect", "_story", "_value")

    def __init__(self, story: CompiledStory, value: Any) -> None:
        self._story = story
        self._value = value
        self._drive = _drive(story, value)
        self._effect: Effect = next(self._drive)
        self._done = self._effect[0] == "done"

    @property
    def story(self) -> CompiledStory:
        """The compiled story this run executes."""
        return self._story

    @property
    def value(self) -> Any:
        """The value the run started from."""
        return self._value

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


def _drive(story: CompiledStory, value: Any) -> Generator[Effect, Any, None]:
    """The run loop: step through the bundle until it passes the last step."""
    products: dict[str, Any] = {}
    output: list[Any] = []
    pc = 0
    while pc < len(story.steps):
        pc, value = yield from _step_product(story, pc, value, products, output)
    yield ("done", output)


def _step_product(
    story: CompiledStory,
    pc: int,
    value: Any,
    products: dict[str, Any],
    output: list[Any],
) -> Generator[Effect, Any, tuple[int, Any]]:
    """Run the step at ``pc``, resolving every suspension it causes.

    Returns the program counter to continue at and the value that continuation takes as its input.
    A receiving step that itself produces a request is handled here, which is what makes a nested
    fan-out resume inside the same run.
    """
    step = story.steps[pc]
    if step.call is not None:
        product = yield ("call", step.call, _call_arguments(story, step, value, products))
    else:
        product = _parse_product(story, step, value, products)
    _check_product(step, product)
    products[step.name] = product
    if step.name == story.exit:
        output.append(product)
    if not step.is_request:
        return pc + 1, product

    if step.type == REQUEST_TYPE:
        request = _single_request(step, product)
        receiver = _receiver(story, step, product, position=0)
        answer = yield ("request", request, receiver)
        continued: tuple[int, Any] = yield from _step_product(
            story, story.index[receiver], answer, products, output
        )
        return continued

    tasks, receivers = _batch_tasks(story, step, product)
    answer = yield ("batch", tasks, step.next or "")
    answers = _batch_answers(step, tasks, answer)
    received_products: list[Any] = []
    continuations: list[int] = []
    for task_answer, receiver in zip(answers, receivers, strict=True):
        next_pc, received = yield from _step_product(
            story, story.index[receiver], task_answer, products, output
        )
        received_products.append(received)
        continuations.append(next_pc)
    # The run continues past **everything** the fan-out ran: with a per-task `next` the receiving
    # steps differ, so "the step after the default" could re-run a step that already answered.
    return max(continuations), received_products


def _check_product(step: StoryStep, product: Any) -> None:
    """A step product must be JSON (03 §3.3): an object may flow, but it stops at this boundary."""
    packed = pack(product)
    if isinstance(packed, Failed):
        raise _failed(step, packed.code, packed.reason, packed.fix)


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


def _parse_product(
    story: CompiledStory, step: StoryStep, value: Any, products: Mapping[str, Any]
) -> Any:
    """Evaluate a step's `parse`: a chain produces one value, a field map one dictionary."""
    scope = Scope(globals=story.globals, products=products, step_input=value)
    if isinstance(step.parse, Mapping):
        return _field_map_product(step, step.parse, value, scope)
    if step.parse is None:  # pragma: no cover - compile time guarantees parse or call
        raise _failed(step, "UP2-E1005", "the step has neither parse nor call", "declare one")
    outcome = eval_field(step.parse, value, scope=scope)
    if isinstance(outcome, Failed):
        raise _from_failed(step, outcome)
    if isinstance(outcome, Missing):
        # A missing value is not an error: the step produced nothing, and the value domain's only
        # "nothing" that can flow on is null (an open question in this change's design).
        return None
    return outcome.value


def _field_map_product(
    step: StoryStep,
    fields: Mapping[str, CompiledField],
    value: Any,
    scope: Scope,
) -> dict[str, Any]:
    """One dictionary from a field map: a `_` field is a local, a missing field is dropped."""
    row: dict[str, Any] = {}
    for name, chain in fields.items():
        outcome = eval_field(chain, value, scope=scope)
        if isinstance(outcome, Failed):
            raise _from_failed(step, outcome)
        if isinstance(outcome, Missing):
            continue
        if name.startswith(LOCAL_PREFIX):
            scope.write_local((name,), outcome.value)
        else:
            row[name] = outcome.value
    return row


def _call_arguments(
    story: CompiledStory, step: StoryStep, value: Any, products: Mapping[str, Any]
) -> dict[str, Any]:
    """Resolve a `call` step's `with` arguments (the same leaves as an operator's parameter)."""
    scope = Scope(globals=story.globals, products=products, step_input=value)
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


def _globals(raw: Any, *, pointer: str) -> Mapping[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise _bad(f"`globals` must be an object, got {type_name(raw)}", pointer=pointer)
    return dict(raw)


def _bad(message: str, *, pointer: str, fix: str = "", allowed: tuple[str, ...] = ()) -> Up2Error:
    return Up2Error(diag("UP2-E1005", message, fix=fix, pointer=pointer, allowed=allowed))


def _failed(step: StoryStep, code: str, reason: str, fix: str) -> Up2Error:
    return Up2Error(diag(code, reason, fix=fix, pointer=step.pointer))


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
