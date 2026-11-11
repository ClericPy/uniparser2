"""The **snapshot runner**: the IO side of the published-chain regression (`04` §6 G2, §7-S4/S5).

A **sample case** is a directory below the samples root (`05` §3 puts it in the repository, so a
snapshot travels with the code through CI)::

    <samples-root>/<root_domain>/<tpl_key>/<case>/input.txt      # the run's input
    <samples-root>/<root_domain>/<tpl_key>/<case>/expected.json  # the recorded product

The runner **walks every case of one key**, runs it through the executor the chain shape selects
(the story executor for a bundle carrying ``steps``, the field evaluator for a field chain), and
compares the product with the recorded one **structurally**. A difference is a JSON Pointer
difference (`core.export.compare_products`), never a text diff, so a failure says which value under
which path changed.

``up2 snapshot`` is the only thing that writes a snapshot (`04` §7-S4), and it writes one only when
``--accept`` was passed: recording a wrong product "because it ran once" is the failure mode that
rule exists to prevent.

**A story that fetches is answered from the request cache** (`uniparser2.net`): the runner replays
the cached answers, so a live sample can be frozen and regressed **offline**. A request with no
cached answer is a **miss** — the runner reports it and stops, because the CLI never reaches the
network: a host fetches, the runner replays.

The file layout lives here rather than in ``store/``: `05` §3 puts ``samples/`` in the repository
("samples are part of a chain's behavioral contract and must travel with the code through CI") and
leaves ``$UP2_HOME/samples`` to temporary, not-yet-committed samples, so the CLI layer that already
reads chain files owns this IO too.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from uniparser2 import Failed, Up2Error, compile_field, compile_story, eval_field, pack, run
from uniparser2.core.errors import diag
from uniparser2.core.export import ProductDifference, render_difference
from uniparser2.core.values import dumps_json, loads_json
from uniparser2.net import RequestCache

INPUT_NAME: Final = "input.txt"
EXPECTED_NAME: Final = "expected.json"
DEFAULT_SAMPLES_ROOT: Final = Path("samples")
"""Where a case lives by default: the repository's own `samples/` directory (`05` §3)."""

CASE_NAME_RULE: Final = r"^[\w\u4e00-\u9fff][\w\u4e00-\u9fff.-]{0,63}$"
"""A case name is a directory name: one path component, no traversal (`04` §2's key rule)."""

_CASE_NAME_PATTERN: Final = re.compile(CASE_NAME_RULE)


@dataclass(frozen=True, slots=True)
class SampleCase:
    """One sample case on disk: its name and the directory holding ``input.txt``."""

    name: str
    path: Path

    @property
    def input_path(self) -> Path:
        """``input.txt``: the run's input (`04` §7-S0)."""
        return self.path / INPUT_NAME

    @property
    def expected_path(self) -> Path:
        """``expected.json``: the recorded product (`04` §7-S4)."""
        return self.path / EXPECTED_NAME


@dataclass(frozen=True, slots=True)
class GraphRun:
    """The outcome of running a graph over one input: a product, or why there is none."""

    value: Any = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass(frozen=True, slots=True)
class RegressionFailure:
    """One case whose product no longer matches its snapshot (`04` §6 G2)."""

    case: str
    error: str = ""
    differences: list[ProductDifference] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """The failure as JSON data (``up2 test --json``)."""
        payload: dict[str, Any] = {"case": self.case}
        if self.error:
            payload["error"] = self.error
        if self.differences:
            payload["differences"] = [item.to_dict() for item in self.differences]
        return payload


def case_directory(root: Path, root_domain: str, tpl_key: str, case: str) -> Path:
    """Where one case lives: ``<root>/<root_domain>/<tpl_key>/<case>`` (`04` §4.1, §7-S0)."""
    return root / root_domain / tpl_key / case


def check_case_name(case: str) -> str | None:
    """A case name is one path component; anything else is a usage error (`04` §2's rule)."""
    if _CASE_NAME_PATTERN.fullmatch(case) is None:
        return (
            f"a case name must match {CASE_NAME_RULE} (one directory name, no path separators), "
            f"got {case!r}"
        )
    return None


def find_cases(root: Path, root_domain: str, tpl_key: str) -> list[SampleCase]:
    """Every case of one key that carries ``input.txt``, in name order (`04` §6 G2)."""
    directory = root / root_domain / tpl_key
    if not directory.is_dir():
        return []
    return sorted(
        (
            SampleCase(name=child.name, path=child)
            for child in directory.iterdir()
            if child.is_dir() and (child / INPUT_NAME).is_file()
        ),
        key=lambda item: item.name,
    )


def read_input(case: SampleCase) -> tuple[Any, str | None]:
    """The case's input, as text; a snapshot of a binary input is not this runner's business."""
    try:
        return case.input_path.read_text(encoding="utf-8"), None
    except OSError as exc:
        return None, f"cannot read the sample input {case.input_path}: {exc}"


def read_expected(case: SampleCase) -> tuple[Any, str | None]:
    """The recorded product of one case; a missing or broken snapshot is a plain error.

    Strict JSON: a snapshot carrying ``Infinity`` is a broken snapshot, not the value ``inf``.
    """
    try:
        text = case.expected_path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"no expected product at {case.expected_path}: {exc}"
    try:
        return loads_json(text, subject=str(case.expected_path)), None
    except Up2Error as exc:
        return None, str(exc)


def record_expected(case: SampleCase, product: Any) -> str | None:
    """Write ``expected.json`` for one case: the **only** way a snapshot is written (`04` §7-S4)."""
    try:
        text = dumps_json(product, indent=2, sort_keys=True, subject="the product") + "\n"
    except Up2Error as exc:
        return str(exc)
    try:
        case.path.mkdir(parents=True, exist_ok=True)
        case.expected_path.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        return f"cannot write the snapshot {case.expected_path}: {exc}"
    return None


def run_graph(graph: Any, value: Any, *, cache: RequestCache | None = None) -> GraphRun:
    """Run a chain over one input through the executor its shape selects (`03` §2, §5).

    A story runs to its collected product through the story executor; a field chain through the
    field evaluator. Both are synchronous and IO-free: a story that suspends on a ``Request`` is
    answered from the **request cache**, and a request with no cached answer is a miss -- the
    runner never reaches the network (`03` §4.1).
    """
    if isinstance(graph, Mapping) and "nodes" in graph:
        return _run_story(graph, value, cache)
    return _run_field(graph, value)


def _run_field(graph: Any, value: Any) -> GraphRun:
    """A field chain: compile, evaluate, and pack the product through the single exit (`N5`)."""
    try:
        compiled = compile_field(graph, products=())
    except Up2Error as exc:
        return GraphRun(error=str(exc.diagnostic))
    outcome = eval_field(compiled, value)
    if isinstance(outcome, Failed):
        return GraphRun(error=f"{outcome.reason} {outcome.fix}".rstrip())
    return _packed(outcome.value)


def _run_story(graph: Any, value: Any, cache: RequestCache | None) -> GraphRun:
    """A story bundle: run it, answering `fetch` from the request cache (`03` §4.1).

    A story may use other host functions; a snapshot runner has no host for them, so it reports
    that before the run instead of failing halfway through. A request with no cached answer is a
    **miss**: the runner never reaches the network.
    """
    try:
        story = compile_story(graph)
    except Up2Error as exc:
        return GraphRun(error=str(exc.diagnostic))
    extra = sorted(story.udf_names - {"fetch"})
    if extra:
        return GraphRun(
            error=(
                f"the story calls host function(s) {', '.join(extra)}; a snapshot runner only "
                "answers `fetch` from the request cache"
            )
        )

    def cached_fetch(request: Any) -> Any:
        key = _request_mapping(request)
        if cache is None:
            raise _CacheMissError(_miss(key, None))
        found = cache.get(key)
        if found is None:
            raise _CacheMissError(_miss(key, cache))
        return found

    try:
        product = run(graph, input=value, udfs={"fetch": cached_fetch})
    except _CacheMissError as exc:
        return GraphRun(error=str(exc))
    except Up2Error as exc:
        return GraphRun(error=str(exc.diagnostic))
    return _packed(product)


class _CacheMissError(Up2Error):
    """Internal: a fetch with no cached answer, carried out as a coded diagnostic.

    A host function's exception would become `UP2-E2099` ("operator raised"); this one is the
    runner's own answer, so it is an `Up2Error` and reaches `run_graph` as it is.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            diag(
                "UP2-E2005",
                message,
                fix="run the sample's host once from the same directory to fill the cache",
            )
        )


def _request_mapping(request: Any) -> Mapping[str, Any]:
    """One request as the cache sees it: a request object with a `url`."""
    if isinstance(request, Mapping):
        return request
    raise _CacheMissError(
        f"fetch needs a request object, got {type(request).__name__}; "
        'build one with ["ctx","dict",{"url":"obj"}]'
    )


def _miss(request: Mapping[str, Any], cache: RequestCache | None) -> str:
    """The message for a request the cache does not hold: the runner never fetches it.

    The message names the cache directory, because the usual cause is looking in the wrong place:
    the cache is relative to the working directory the command ran in.
    """
    url = request.get("url")
    where = cache.root if cache is not None else RequestCache().root
    return (
        f"the request {url!r} is not in the request cache ({where}); run the sample's host once "
        "from the same directory to fill it (a snapshot runner never reaches the network)"
    )


def _packed(value: Any) -> GraphRun:
    """The single exit (`N5`): a product that cannot leave a chain is not a snapshot."""
    packed = pack(value)
    if isinstance(packed, Failed):
        return GraphRun(error=f"{packed.reason} {packed.fix}".rstrip())
    return GraphRun(value=value)


def failure_line(failure: RegressionFailure) -> str:
    """One failed case as a readable line: the case name plus each pointer difference."""
    if failure.error:
        return f"{failure.case}: {failure.error}"
    return "; ".join(f"{failure.case} {render_difference(item)}" for item in failure.differences)


def regression_message(failures: list[RegressionFailure]) -> str:
    """G2's refusal message, carrying the JSON Pointer difference (`04` §6, §5.1 E3005)."""
    return f"the snapshot regression failed for {len(failures)} case(s): " + " | ".join(
        failure_line(item) for item in failures
    )


__all__ = [
    "CASE_NAME_RULE",
    "DEFAULT_SAMPLES_ROOT",
    "EXPECTED_NAME",
    "INPUT_NAME",
    "GraphRun",
    "RegressionFailure",
    "SampleCase",
    "case_directory",
    "check_case_name",
    "failure_line",
    "find_cases",
    "read_expected",
    "read_input",
    "record_expected",
    "regression_message",
    "run_graph",
]
