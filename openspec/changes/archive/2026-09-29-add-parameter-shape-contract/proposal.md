# Proposal

## Why

A chain step's parameter slot (slot 3) has three writings — the value itself, a positional array, a
named object — and which one an action accepts is decided by how many parameters that action still
has to fill. Nothing states that per action: the rule lives only in `02` §4, so a writer has to infer
it, and an LLM that follows the engineering note's instruction to read `up2 ops --json` first sees
parameter names and kinds but not the writing. The mistake is cheap to make and, for `py`, invisible
until runtime — measured in this repository:

| chain (all pass `up2 lint`) | today |
|---|---|
| `["css1","text",{"selector":"h1"}]` | compile-time `UP2-E1005` at `/0/2/selector`, with a fix line |
| `["re","search",{"pattern":"\\d+"}]` | compile-time `UP2-E1005` at `/2/pattern` |
| `["ctx","set",{"path":"locals.x"}]` | compile-time `UP2-E1005` at `/2/path` |
| `["json",{"expr":"a"}]` | compile-time `UP2-E1005` at `/0/1/expr` |
| `["py","urljoin",{"base":"https://example.com/"}]` | **passes lint**, fails at runtime with `UP2-E2002` and an empty `fix` |
| `["py","slice",{"spec":"0:4"}]` | **passes lint**, fails at runtime with `UP2-E2002` |

`py` declares 31 functions and validates two of them (`urlsplit.part`, `parse_time.format`) in its
`precompile` hook; every other operator already validates its own parameters there. So the same
mistake is a compile-time diagnostic everywhere except in `py`, which contradicts `N3` ("a bad chain
fails at compile time") exactly where the operator table is widest.

## What Changes

- **`py` validates its scalar parameters at compile time**, through the existing `precompile` hook and
  reusing `UP2-E1005` (no new error code): a JSON container where the function's own runtime guard
  requires a string or an integer becomes a compile-time diagnostic with a pointer at the parameter
  and a fix line that gives the correct writing.
- **The parameter slot keeps its current semantics**: nothing is reinterpreted, and a container stays a
  legal value for a parameter that accepts any type. `["py","default",{"a":1}]` returns `{"a":1}` today
  and must keep doing so; `{"$lit": …}` remains the escape for an explicit literal.
- **`up2 ops` states the slot shape per action** — `value` / `named` / `none`, derived from the
  parameters the action still has to fill — in both the human view and `--json`, so the rule is
  visible where the chain is written rather than only in the DSL spec.
- **Docs**: `02` §4 (the shape rule gains the single-parameter prohibition) and §6.4 (`py`'s parameter
  table), `01` §7 (the self-description field list), `CHANGELOG.md`.
- **BREAKING**: none for legal chains. The `py` writings that change behavior are the ones that already
  fail — they now fail at `up2 lint` instead of at runtime.

## Capabilities

### New Capabilities

- `dsl-operators`: the operator layer's chain-facing contract — which shape each action's parameter
  slot takes, what each action validates about its own parameters at compile time (`py`'s per-function
  scalar parameters included), and the capability self-description `up2 ops` prints for both.

### Modified Capabilities

(none. `openspec/specs/` holds `code-execution` and `time-parsing`; no requirement of either changes.)

## Impact

- Code: `src/uniparser2/ops/pyops.py` (a scalar-parameter table plus one check called from the existing
  `precompile`); `src/uniparser2/core/registry.py` (`ActionReport` and `report_dicts()` gain the
  slot-shape field and its derivation from the action's preset parameters);
  `src/uniparser2/cli/main.py` (the human `up2 ops` view prints it).
- Dependencies: none; the kernel keeps zero third-party dependencies and stays IO-free.
- Tests: `tests/ops/test_pyops.py` (negative cases per covered function, plus regression guards for the
  legal container literal and for the multi-parameter named form), `tests/cli/test_cli.py` (`up2 ops`
  text), `tests/ops/test_registry.py` (the report field).
- Conformance: the pair count stays 59 and no error code is added, so `up2 conformance --check` must
  stay green with the existing declarations.
- Docs: `docs/specs/001` §7, `docs/specs/002` §4/§6.4, `CHANGELOG.md`.
