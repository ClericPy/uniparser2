"""``up2`` command line: operator introspection / conformance audit / compile check / local trial
run (design docs 04 §7-S0–S3, 05 §5).

Exit codes: ``0`` ok (including ``Missing`` — missing is not an error, 01 §4.1); ``1`` compile or
run failed; ``2`` usage error.

Value conventions:
- ``--global K=V`` / ``--product K=V``: ``V`` is parsed as JSON and falls back to a string.
- ``--input K=V``: ``V`` is parsed as JSON only when it starts with ``{``/``[``; otherwise it stays
  a string (otherwise ``--input text=123`` would silently become an int).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import uniparser2
from uniparser2 import (
    Diagnostic,
    Failed,
    Missing,
    Ok,
    Outcome,
    Policy,
    Scope,
    Up2Error,
    compile_field,
    eval_field,
    pack,
)
from uniparser2.core import registry
from uniparser2.core.conformance import check

from .conformance import DEFAULT_TESTS_ROOT, scan_tests

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
MAIN_INPUT_KEY = "text"
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
    trial.add_argument("--on-missing", default="empty", choices=("empty", "none", "drop", "raise"))
    trial.add_argument("--on-error", default="raise", choices=("raise", "empty", "none", "drop"))
    trial.add_argument("--json", action="store_true", help="output JSON")
    trial.set_defaults(handler=_cmd_trial)

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
            print(f"  - {action['name']}{missing}  [slot3={form}]  {action['summary']}")
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


def _cmd_trial(args: argparse.Namespace) -> int:
    source, error = _load_chain(args.file)
    if error is not None:
        print(error, file=sys.stderr)
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
    policy = Policy(on_missing=args.on_missing, on_error=args.on_error)
    scope = Scope(globals=globals_map, products=products)
    value = inputs.get(MAIN_INPUT_KEY, inputs)
    return _report_outcome(eval_field(compiled, value, scope=scope, policy=policy), args.json)


def _report_outcome(outcome: Outcome, as_json: bool) -> int:
    if isinstance(outcome, Ok):
        packed = pack(outcome.value)
        if isinstance(packed, Failed):
            return _report_outcome(packed, as_json)
        payload: dict[str, Any] = {"state": "ok", "value": outcome.value}
        code = EXIT_OK
    elif isinstance(outcome, Missing):
        payload = {"state": "missing", "reason": outcome.reason}
        code = EXIT_OK
    else:
        payload = {
            "state": "failed",
            "code": outcome.code,
            "reason": outcome.reason,
            "fix": outcome.fix,
        }
        code = EXIT_FAILED
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"[{payload['state']}] " + json.dumps(payload, ensure_ascii=False))
    return code


def _print_diagnostic(diagnostic: Diagnostic, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(diagnostic.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(str(diagnostic), file=sys.stderr)


def _load_chain(path_text: str) -> tuple[Any, str | None]:
    path = Path(path_text)
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"cannot read chain file {path}: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"{path} is not valid JSON: {exc}"


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
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
