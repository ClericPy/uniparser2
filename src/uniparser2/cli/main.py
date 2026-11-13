"""``up2`` command line: operator introspection / conformance audit / compile check / local trial
run (design docs 04 §7-S0–S3, 05 §5), the template store's own commands (04 §4–§6), and the SOP
commands around them: the snapshot runner of G2 (``up2 snapshot`` / ``up2 test``, 04 §7-S4/S5) and
``up2 doctor`` with its ``--fix`` (04 §10, 07 §3 acceptance item 3).

Exit codes: ``0`` ok (a value, including an empty one — a query that matched nothing is not an
error, `01` §4); ``1`` compile or
run failed; ``2`` usage error.

Two file shapes are accepted by ``lint`` / ``trial`` / ``publish`` / ``snapshot``: a **field chain**
(a JSON array of stages) and a **story** (a JSON object carrying ``globals`` and ``nodes``). A
story is compiled and run with the story layer; a host function it calls must be supplied by the
command, and a missing one is reported with ``UP2-E1010``.

``up2 trial --trace`` reports the run's per-stage trace (``06`` §5.1): the events in evaluation
order, as one JSON document with ``--json`` and as one line per event without it. A trace changes
nothing about the run: a story that calls a missing host function still fails with ``UP2-E1010``,
and the trace carries the events up to that failure.

Value conventions:
- ``--global K=V`` / ``--product K=V``: ``V`` is parsed as JSON and falls back to a string.
- ``--input K=V``: ``V`` is parsed as JSON only when it starts with ``{``/``[``; otherwise it stays
  a string (otherwise ``--input text=123`` would silently become an int).

The store commands take their implementation from ``UP2_STORE`` and their location from ``UP2_HOME``
(04 §4.1); ``get`` recompiles what it read back, because a stored chain is data and is never trusted
as a compilation product (01 §8). The sample commands take their root from ``--tests-root``
(default ``samples``, where 05 §3 puts a chain's behavioral contract).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import uniparser2
from uniparser2 import (
    Diagnostic,
    Ok,
    Outcome,
    Scope,
    Trace,
    TraceEvent,
    Up2Error,
    ValueView,
    compile_field,
    compile_story,
    eval_field,
    run,
)
from uniparser2.core import compare_products, registry
from uniparser2.core.conformance import check
from uniparser2.core.values import loads_json
from uniparser2.net import RequestCache
from uniparser2.store import (
    AuditRow,
    audit_row_dict,
    gate_overwrite,
    gate_skip_tests,
    lint_graph,
    open_store,
    repair_chain,
    template_dict,
)

from .conformance import DEFAULT_TESTS_ROOT, scan_tests
from .samples import (
    DEFAULT_SAMPLES_ROOT,
    RegressionFailure,
    SampleCase,
    case_directory,
    check_case_name,
    failure_line,
    find_cases,
    read_expected,
    read_input,
    record_expected,
    regression_message,
    run_graph,
)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
MAIN_INPUT_KEY = "text"
STORY_KEY = "nodes"
UNKNOWN_ACTOR = "unknown"
AGENT_SOURCE = "agent"
DOCTOR_ACTOR = "doctor"
DOCTOR_NOTE = "written by `up2 doctor --fix`: this chain had no audit row"
SOURCES = ("human", "agent", "import")
_G2_FIX = "run `up2 test` for the full difference list, or pass --skip-tests --note"
_JSON_CONTAINER_PREFIXES = ("{", "[")


def main(argv: Sequence[str] | None = None) -> int:
    """``up2`` entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return EXIT_USAGE
    try:
        return int(handler(args))
    except Up2Error as exc:
        # The store and the runner read data that can be corrupt; a bad row is a coded diagnostic
        # like any other, never a traceback. Handlers report most errors themselves; this is the
        # backstop for the paths that read first and validate later.
        _print_diagnostic(exc.diagnostic, as_json=bool(getattr(args, "json", False)))
        return EXIT_FAILED
    except ValueError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="up2", description="uniparser2 command line")
    parser.add_argument(
        "--version", action="version", version=f"uniparser2 {uniparser2.__version__}"
    )
    sub = parser.add_subparsers(dest="command")

    ops = sub.add_parser("ops", help="list operators, actions and parameter schemas")
    ops.add_argument("--json", action="store_true", help="output JSON")
    ops.set_defaults(handler=_cmd_ops)

    conf = sub.add_parser("conformance", help="audit registry declarations against case coverage")
    conf.add_argument("--check", action="store_true", help="exit with code 1 on disagreement")
    conf.add_argument("--json", action="store_true", help="output JSON")
    conf.add_argument("--tests-root", default=str(DEFAULT_TESTS_ROOT), help="test directory")
    conf.set_defaults(handler=_cmd_conformance)

    lint = sub.add_parser("lint", help="compile-check a chain (without executing it)")
    lint.add_argument("file", help="chain file (JSON)")
    lint.add_argument(
        "--product",
        action="append",
        default=[],
        metavar="NAME[=JSON]",
        help="declare outputs of preceding nodes that may be referenced",
    )
    lint.add_argument("--json", action="store_true", help="output JSON")
    lint.set_defaults(handler=_cmd_lint)

    trial = sub.add_parser("trial", help="trial-run a chain on local inputs")
    trial.add_argument("file", help="chain file (JSON)")
    trial.add_argument(
        "--input",
        action="append",
        default=[],
        metavar="K=V|K=@file",
        help=f"input value; {MAIN_INPUT_KEY} is the main input slot",
    )
    trial.add_argument(
        "--global",
        dest="global_vars",
        action="append",
        default=[],
        metavar="K=V",
        help="chain-level read-only environment",
    )
    trial.add_argument(
        "--product",
        action="append",
        default=[],
        metavar="NAME=JSON",
        help="inject outputs of preceding nodes",
    )
    trial.add_argument(
        "--node",
        default=None,
        metavar="NAME",
        help="the story node to run (default: the first node)",
    )
    trial.add_argument(
        "--trace",
        action="store_true",
        help="report the per-stage trace of this run (06 §5.1)",
    )
    trial.add_argument("--json", action="store_true", help="output JSON")
    trial.set_defaults(handler=_cmd_trial)

    publish = sub.add_parser("publish", help="store a chain under a business identity (04 §5, §6)")
    publish.add_argument("file", help="chain file (JSON)")
    publish.add_argument("--domain", required=True, help="site identity, e.g. ah.gov.cn")
    publish.add_argument("--key", dest="tpl_key", required=True, help="business name")
    publish.add_argument(
        "--actor", default=UNKNOWN_ACTOR, help="who publishes it (default unknown)"
    )
    publish.add_argument(
        "--source", default=AGENT_SOURCE, choices=SOURCES, help="who wrote the chain"
    )
    publish.add_argument("--note", default=None, help="a remark recorded on the audit row")
    publish.add_argument(
        "--skip-tests",
        action="store_true",
        help="skip the snapshot regression; requires --note",
    )
    publish.add_argument(
        "--confirm-overwrite",
        action="store_true",
        help="replace a chain whose status is already ready",
    )
    publish.add_argument(
        "--tests-root",
        default=str(DEFAULT_SAMPLES_ROOT),
        help="root of the sample cases G2 regresses (default: samples)",
    )
    publish.add_argument(
        "--types",
        default=None,
        help="a host module to import for its domain types (register_type)",
    )
    publish.add_argument("--json", action="store_true", help="output JSON")
    publish.set_defaults(handler=_cmd_publish)

    snapshot = sub.add_parser("snapshot", help="record a case's product as its expected product")
    snapshot.add_argument("file", help="chain file (JSON)")
    snapshot.add_argument("--domain", required=True, help="site identity, e.g. ah.gov.cn")
    snapshot.add_argument("--key", dest="tpl_key", required=True, help="business name")
    snapshot.add_argument("--case", required=True, help="sample case name (a directory)")
    snapshot.add_argument(
        "--accept",
        action="store_true",
        help="confirm the product and write samples/.../expected.json",
    )
    snapshot.add_argument(
        "--tests-root",
        default=str(DEFAULT_SAMPLES_ROOT),
        help="root of the sample cases (default: samples)",
    )
    snapshot.add_argument(
        "--types",
        default=None,
        help="a host module to import for its domain types (register_type)",
    )
    snapshot.add_argument("--json", action="store_true", help="output JSON")
    snapshot.set_defaults(handler=_cmd_snapshot)

    test = sub.add_parser("test", help="run the frozen chain of a key plus its samples (04 §7-S5)")
    test.add_argument("domain", help="site identity")
    test.add_argument("key", help="business name")
    test.add_argument("--case", default=None, help="run one case only")
    test.add_argument(
        "--tests-root",
        default=str(DEFAULT_SAMPLES_ROOT),
        help="root of the sample cases (default: samples)",
    )
    test.add_argument(
        "--types",
        default=None,
        help="a host module to import for its domain types (register_type)",
    )
    test.add_argument("--json", action="store_true", help="output JSON")
    test.set_defaults(handler=_cmd_test)

    doctor = sub.add_parser("doctor", help="check the store for inconsistencies and repair them")
    doctor.add_argument("--fix", action="store_true", help="write the audit rows that are missing")
    doctor.add_argument("--json", action="store_true", help="output JSON")
    doctor.set_defaults(handler=_cmd_doctor)

    get = sub.add_parser("get", help="print a stored chain with its fingerprint")
    get.add_argument("domain", help="site identity")
    get.add_argument("key", help="business name")
    get.add_argument(
        "--graph", action="store_true", help="print only the chain data (backup material)"
    )
    get.set_defaults(handler=_cmd_get)

    audit = sub.add_parser("audit", help="print the fingerprint chain of a stored chain")
    audit.add_argument("domain", help="site identity")
    audit.add_argument("key", help="business name")
    audit.add_argument("--json", action="store_true", help="output JSON")
    audit.set_defaults(handler=_cmd_audit)

    return parser


def _cmd_ops(args: argparse.Namespace) -> int:
    payload = registry.report_dicts()
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return EXIT_OK
    for item in payload:
        mark = "" if item["available"] else "  [unavailable]"
        slots = ", ".join(f"slot{i + 2}={role}" for i, role in enumerate(item["slots"]))
        print(f"{item['name']}{mark}  arity={item['arity']}  [{slots}]  {item['summary']}")
        for action in item["actions"]:
            missing = f"  [missing {', '.join(action['missing'])}]" if action["missing"] else ""
            form = action["param_form"]
            # The parameter slot is the operator's last one: slot 3 for a 3-slot operator, slot 2
            # for a 2-slot one (`json` / `const` / `code`).
            head = f"  - {action['name']}{missing}  [slot{item['arity']}={form}]"
            print(f"{head}  {action['summary']}")
    return EXIT_OK


def _cmd_conformance(args: argparse.Namespace) -> int:
    root = Path(args.tests_root)
    if not root.is_dir():
        print(
            f"test directory not found: {root}; "
            "the conformance audit must run inside the source tree",
            file=sys.stderr,
        )
        return EXIT_USAGE
    pairs, codes = scan_tests(root)
    report = check(covered_pairs=pairs, covered_codes=codes)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(report.render())
    return EXIT_OK if report.ok else EXIT_FAILED


def _cmd_lint(args: argparse.Namespace) -> int:
    source, error = _load_chain(args.file)
    if error is not None:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    if _is_story(source):
        return _lint_story(source, args)
    names, values, error = _split_assignments(args.product, need_value=False)
    if error is not None:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    del values
    try:
        compiled = compile_field(source, products=names)
    except Up2Error as exc:
        _print_diagnostic(exc.diagnostic, as_json=args.json)
        return EXIT_FAILED
    if args.json:
        print(json.dumps({"ok": True, "steps": len(compiled.stages)}, ensure_ascii=False))
    else:
        print(f"OK: {len(compiled.stages)} stages")
    return EXIT_OK


def _lint_story(source: Any, args: argparse.Namespace) -> int:
    """A story declares its own node names, so ``--product`` has nothing to say here."""
    if args.product:
        print("--product cannot be used with a story file", file=sys.stderr)
        return EXIT_USAGE
    try:
        story = compile_story(source)
    except Up2Error as exc:
        _print_diagnostic(exc.diagnostic, as_json=args.json)
        return EXIT_FAILED
    names = list(story.nodes)
    if args.json:
        print(json.dumps({"ok": True, "nodes": len(names), "names": names}, ensure_ascii=False))
    else:
        print(f"OK: {len(names)} nodes: {', '.join(names)}")
    return EXIT_OK


def _cmd_trial(args: argparse.Namespace) -> int:
    source, error = _load_chain(args.file)
    if error is not None:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    trace = Trace() if args.trace else None
    if _is_story(source):
        return _trial_story(source, args, trace)
    if args.node is not None:
        print("--node belongs to a story file", file=sys.stderr)
        return EXIT_USAGE
    names, products, error = _split_assignments(args.product, need_value=True)
    if error is not None:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    try:
        compiled = compile_field(source, products=names)
    except Up2Error as exc:
        _print_diagnostic(exc.diagnostic, as_json=args.json)
        return EXIT_FAILED
    globals_map, error = _key_value_map(args.global_vars)
    if error is not None:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    inputs, error = _read_inputs(args.input)
    if error is not None:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    scope = Scope(globals=globals_map, products=products)
    value = inputs.get(MAIN_INPUT_KEY, inputs)
    outcome = eval_field(compiled, value, scope=scope, trace=trace)
    return _report_outcome(outcome, args.json, trace=trace)


def _trial_story(source: Any, args: argparse.Namespace, trace: Trace | None) -> int:
    """Run one story node. Without a host, a story that calls a udf reports `UP2-E1010`."""
    if args.product:
        print(
            "--product cannot be used with a story file: a story carries its own node names",
            file=sys.stderr,
        )
        return EXIT_USAGE
    globals_map, error = _key_value_map(args.global_vars)
    if error is not None:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    inputs, error = _read_inputs(args.input)
    if error is not None:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    value = inputs.get(MAIN_INPUT_KEY, inputs)
    try:
        product = run(
            source,
            args.node,
            value,
            globals=globals_map,
            trace=trace,
        )
    except Up2Error as exc:
        if trace is None:
            _print_diagnostic(exc.diagnostic, as_json=args.json)
            return EXIT_FAILED
        # The trace is the point of asking for one: the failing stage's own event (its code and
        # reason) is what says where the run stopped.
        _emit_state({"state": "failed", **exc.diagnostic.to_dict()}, as_json=args.json, trace=trace)
        return EXIT_FAILED
    return _report_outcome(Ok(product), args.json, trace=trace)


def _cmd_publish(args: argparse.Namespace) -> int:
    """G1..G3, then the store's only write entry point (04 §5, §6)."""
    graph, error = _load_chain(args.file)
    if error is not None:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    if args.types:
        error = _load_types(args.types)
        if error is not None:
            print(error, file=sys.stderr)
            return EXIT_USAGE
    store = open_store()
    stored = store.get(args.domain, args.tpl_key)
    refusal = gate_overwrite(
        None if stored is None else stored.status, confirm=args.confirm_overwrite
    )
    if refusal is not None:
        print(f"usage error: {refusal}", file=sys.stderr)
        return EXIT_USAGE
    skipped = gate_skip_tests(skip_tests=args.skip_tests, note=args.note)
    if skipped is not None:
        _print_diagnostic(skipped, as_json=args.json)
        return EXIT_FAILED
    if not args.skip_tests:
        # G2: the snapshots that already exist are regressed before anything is written, so a
        # refusal leaves the store untouched (04 §6). This mirrors `up2 test`, so both report the
        # same JSON Pointer difference for the same red case.
        failures = _run_cases(
            _cases_root(args.tests_root), args.domain, args.tpl_key, graph, case=None
        )
        if failures:
            _print_diagnostic(
                Diagnostic(code="UP2-E3005", message=regression_message(failures), fix=_G2_FIX),
                as_json=args.json,
            )
            return EXIT_FAILED
    try:
        result = store.publish(
            graph,
            root_domain=args.domain,
            tpl_key=args.tpl_key,
            actor=args.actor,
            source=args.source,
            note=args.note,
        )
    except Up2Error as exc:
        _print_diagnostic(exc.diagnostic, as_json=args.json)
        return EXIT_FAILED
    payload: dict[str, Any] = {
        "chain_id": result.chain_id,
        "old_hash": result.old_hash,
        "new_hash": result.new_hash,
        "changed": result.changed,
        "audit_seq": result.audit_seq,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(
            f"changed={result.changed} chain_id={result.chain_id} "
            f"{result.old_hash} -> {result.new_hash} audit_seq={result.audit_seq}"
        )
    return EXIT_OK


def _cmd_snapshot(args: argparse.Namespace) -> int:
    """S4: freeze one case's product as its expected product (04 §7-S4).

    ``--accept`` is the only way a snapshot is written: a person confirms in S3 that the product is
    right, and `up2 trial` never writes one automatically, so "it ran once" cannot record a wrong
    product as the right one.
    """
    if not args.accept:
        print(
            "usage error: writing a snapshot needs --accept (04 §7-S4: a snapshot is frozen only "
            "after a person confirmed the product in S3)",
            file=sys.stderr,
        )
        return EXIT_USAGE
    invalid = check_case_name(args.case)
    if invalid is not None:
        print(f"usage error: {invalid}", file=sys.stderr)
        return EXIT_USAGE
    graph, error = _load_chain(args.file)
    if error is not None:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    if args.types:
        error = _load_types(args.types)
        if error is not None:
            print(error, file=sys.stderr)
            return EXIT_USAGE
    case = SampleCase(
        name=args.case,
        path=case_directory(_cases_root(args.tests_root), args.domain, args.tpl_key, args.case),
    )
    value, error = read_input(case)
    if error is not None:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    result = run_graph(graph, value, cache=RequestCache())
    if not result.ok:
        print(result.error, file=sys.stderr)
        return EXIT_FAILED
    error = record_expected(case, result.value)
    if error is not None:
        print(error, file=sys.stderr)
        return EXIT_FAILED
    payload: dict[str, Any] = {
        "case": case.name,
        "expected": str(case.expected_path),
        "value": result.value,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"recorded {case.expected_path}")
    return EXIT_OK


def _cmd_test(args: argparse.Namespace) -> int:
    """S5: run a key's frozen chain over every sample once (04 §7-S5)."""
    if args.types:
        error = _load_types(args.types)
        if error is not None:
            print(error, file=sys.stderr)
            return EXIT_USAGE
    store = open_store()
    template = store.get(args.domain, args.key)
    if template is None:
        print(f"no chain {args.domain}/{args.key}", file=sys.stderr)
        return EXIT_FAILED
    try:
        # A stored chain is data (`01` §8): compile the row before regressing anything with it, so a
        # hand-edited chain is reported once by the compiler instead of once per case.
        lint_graph(template.graph)
    except Up2Error as exc:
        _print_diagnostic(exc.diagnostic, as_json=args.json)
        return EXIT_FAILED
    failures = _run_cases(
        _cases_root(args.tests_root), args.domain, args.key, template.graph, case=args.case
    )
    if args.json:
        payload = {
            "ok": not failures,
            "domain": args.domain,
            "key": args.key,
            "failures": [item.to_dict() for item in failures],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif failures:
        for failure in failures:
            print(failure_line(failure))
    else:
        print(f"OK: {args.domain}/{args.key} matches its samples")
    return EXIT_FAILED if failures else EXIT_OK


def _cmd_doctor(args: argparse.Namespace) -> int:
    """04 §10: check that chains and audit correspond, and repair what --fix can (E3003)."""
    store = open_store()
    findings = store.inconsistencies()
    fixed: list[AuditRow] = []
    if args.fix:
        for finding in findings:
            row = repair_chain(store, finding.chain_id, actor=DOCTOR_ACTOR, note=DOCTOR_NOTE)
            if row is not None:
                fixed.append(row)
        remaining = store.inconsistencies()
    else:
        remaining = findings
    payload: dict[str, Any] = {
        "ok": not remaining,
        "findings": [finding.to_dict() for finding in findings],
        "fixed": [audit_row_dict(row) for row in fixed],
        "remaining": [finding.to_dict() for finding in remaining],
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for finding in findings:
            print(str(finding), file=sys.stderr)
        for row in fixed:
            print(f"fixed {row.chain_id}: wrote audit row {row.seq}")
        print(
            "OK: no inconsistency"
            if not remaining
            else f"{len(remaining)} finding(s) remain; run `up2 doctor --fix`"
        )
    return EXIT_OK if not remaining else EXIT_FAILED


def _cases_root(tests_root: str) -> Path:
    """Where the sample cases live: ``--tests-root``, defaulting to the repository's ``samples``."""
    return Path(tests_root)


def _run_cases(
    root: Path, root_domain: str, tpl_key: str, graph: Any, *, case: str | None
) -> list[RegressionFailure]:
    """Regress every sample of one key (or one ``--case``) against the graph it was frozen with.

    A missing snapshot is a failure of the gate rather than a silent pass: G2 promises to regress
    "every case under ``samples/`` for this ``tpl_key``" (04 §6), and a chain with no recorded
    snapshot has nothing to regress.

    A story that fetches is answered from the **request cache** (`uniparser2.net`): the runner
    replays, it never reaches the network.
    """
    cases = find_cases(root, root_domain, tpl_key)
    if case is not None:
        cases = [item for item in cases if item.name == case]
    failures: list[RegressionFailure] = []
    cache = RequestCache()
    for item in cases:
        value, error = read_input(item)
        if error is not None:
            failures.append(RegressionFailure(case=item.name, error=error))
            continue
        expected, error = read_expected(item)
        if error is not None:
            failures.append(RegressionFailure(case=item.name, error=error))
            continue
        result = run_graph(graph, value, cache=cache)
        if not result.ok:
            failures.append(RegressionFailure(case=item.name, error=result.error))
            continue
        differences = compare_products(expected, result.value)
        if differences:
            failures.append(RegressionFailure(case=item.name, differences=differences))
    return failures


def _cmd_get(args: argparse.Namespace) -> int:
    """Read a chain back and recompile it before trusting it (01 §8)."""
    template = open_store().get(args.domain, args.key)
    if template is None:
        print(f"no chain {args.domain}/{args.key}", file=sys.stderr)
        return EXIT_FAILED
    try:
        lint_graph(template.graph)
    except Up2Error as exc:
        _print_diagnostic(exc.diagnostic, as_json=False)
        return EXIT_FAILED
    payload: object = template.graph if args.graph else template_dict(template)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return EXIT_OK


def _cmd_audit(args: argparse.Namespace) -> int:
    """The fingerprint chain of one key: who changed what, and when (04 §10)."""
    store = open_store()
    template = store.get(args.domain, args.key)
    if template is None:
        print(f"no chain {args.domain}/{args.key}", file=sys.stderr)
        return EXIT_FAILED
    rows = store.audit(template.chain_id)
    if args.json:
        print(json.dumps([audit_row_dict(row) for row in rows], indent=2, ensure_ascii=False))
        return EXIT_OK
    for row in rows:
        print(
            f"{row.seq}  {row.at}  {row.actor}  {row.source}  "
            f"{row.old_hash} -> {row.new_hash}  {row.note or ''}".rstrip()
        )
    return EXIT_OK


def _report_outcome(outcome: Outcome, as_json: bool, *, trace: Trace | None = None) -> int:
    if isinstance(outcome, Ok):
        payload: dict[str, Any] = {"state": "ok", "value": outcome.value}
        code = EXIT_OK
    else:
        payload = {
            "state": "failed",
            "code": outcome.code,
            "reason": outcome.reason,
            "fix": outcome.fix,
        }
        code = EXIT_FAILED
    _emit_state(payload, as_json=as_json, trace=trace)
    return code


def _emit_state(payload: dict[str, Any], *, as_json: bool, trace: Trace | None) -> None:
    """Print one run's state, and its trace when the caller asked for one.

    The trace is a key of the JSON document (so one call answers both), and one line per event in
    the text output -- printing it twice would be unreadable for a long run.
    """
    if as_json:
        if trace is not None:
            payload["trace"] = trace.to_list()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if trace is not None:
        _print_trace(trace)
    print(f"[{payload['state']}] " + json.dumps(payload, ensure_ascii=False))


def _print_trace(trace: Trace) -> None:
    """One line per trace event: the trial bench (`06` §3) renders the same events as a table."""
    for event in trace.events:
        print(_trace_line(event))


def _trace_line(event: TraceEvent) -> str:
    where = event.node or "-"
    if event.field:
        where = f"{where}.{event.field}"
    item = "-" if event.item is None else str(event.item)
    stage = "-" if event.stage is None else str(event.stage)
    doing = f"{event.op}.{event.action}"
    return (
        f"{event.seq:>4}  {where:<24} item={item:<4} stage={stage:<3} {doing:<22} "
        f"{event.state:<8}{event.ms:>8.3f}ms  "
        f"{_view_text(event.input)} -> {_view_text(event.output)}"
    )


def _view_text(view: ValueView) -> str:
    """One event side, compactly: the type and size, then the preview's beginning."""
    text = view.preview if len(view.preview) <= 48 else view.preview[:48] + "..."
    return f"{view.type}({view.size}) {text}"


def _print_diagnostic(diagnostic: Diagnostic, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(diagnostic.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(str(diagnostic), file=sys.stderr)


def _load_chain(path_text: str) -> tuple[Any, str | None]:
    path = Path(path_text)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"cannot read chain file {path}: {exc}"
    try:
        return loads_json(text, subject=str(path)), None
    except Up2Error as exc:
        return None, str(exc)


def _load_types(path_text: str) -> str | None:
    """Import a host module so its domain types are registered (``register_type``).

    A story names its types (``03`` §3.3) and the host owns them, so the runner needs the host's
    registrations to build a product. The module is imported for its side effect, exactly like a
    host recipe does.
    """
    path = Path(path_text)
    if not path.is_file():
        return f"cannot read the types module {path}: no such file"
    name = f"up2_types_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return f"cannot import the types module {path}"
    module = importlib.util.module_from_spec(spec)
    # The module goes into `sys.modules` **before** it runs: a dataclass with `slots=True` looks
    # its own module up there to rebuild the class.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        del sys.modules[name]
        return f"the types module {path} failed to load: {exc!r}"
    return None


def _is_story(source: Any) -> bool:
    """A story is a JSON object carrying ``nodes``; anything else is a field chain (03 §2)."""
    return isinstance(source, Mapping) and STORY_KEY in source


def _split_assignments(
    items: Sequence[str], *, need_value: bool
) -> tuple[list[str], dict[str, Any], str | None]:
    """``K[=V]`` list → (name list, name→value map, error)."""
    names: list[str] = []
    values: dict[str, Any] = {}
    for item in items:
        name, sep, raw = item.partition("=")
        if not name:
            return [], {}, f"malformed argument: {item!r}"
        if not sep:
            if need_value:
                return [], {}, f"{item!r} is missing the =VALUE part"
            names.append(name)
            continue
        names.append(name)
        values[name] = _parse_json_or_text(raw)
    return names, values, None


def _key_value_map(items: Sequence[str]) -> tuple[dict[str, Any], str | None]:
    names, values, error = _split_assignments(items, need_value=True)
    if error is not None:
        return {}, error
    return {name: values[name] for name in names}, None


def _read_inputs(items: Sequence[str]) -> tuple[dict[str, Any], str | None]:
    inputs: dict[str, Any] = {}
    for item in items:
        name, sep, raw = item.partition("=")
        if not name or not sep or not raw:
            return {}, f"--input must be written as K=V or K=@file: {item!r}"
        if raw.startswith("@"):
            path = Path(raw[1:])
            try:
                inputs[name] = path.read_text(encoding="utf-8")
            except OSError as exc:
                return {}, f"cannot read input file {path}: {exc}"
            continue
        inputs[name] = _parse_json_or_text(raw) if raw.startswith(_JSON_CONTAINER_PREFIXES) else raw
    return inputs, None


def _parse_json_or_text(raw: str) -> Any:
    try:
        return loads_json(raw)
    except Up2Error:
        return raw


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
