# Proposal

## Why

Today a chain can only express processing logic through `py`'s 31 allowlisted functions, reference passing, and host-registered `udf`; as soon as document-level one-off processing is needed (multi-branch cleanup, line-based restructuring, batch validation), the only option is to change host code and redeploy — and LLM-generated chains naturally write this kind of code. This project needs a path that is **both able to write code and unwilling to hand RCE to the chain**. `pydantic-monty` (a language-level sandbox written in Rust, MIT, 1.0.0) satisfies this combination per this repo's spike measurements: works on Windows, checkout+run median 0.72–0.84 ms with a warm pool, three runs byte-identical under frozen clock + seeded random, and the classic CPython escape chain simply does not exist at the language level (`'str' object has no attribute '__class__'`).

## What Changes

- New standalone operator **`code`** (2 slots, single behavior so no action slot): `["code", {"src": "…", "inputs": {"x": "$locals.x"}}]`; the upstream value is implicitly bound as `obj`.
- New optional extra **`[code]`** (`pydantic-monty>=1.0.0`): **absent by default**; when not installed, compile-time `UP2-E1107` + install hint (reusing the existing optional dependency gate, no new "capability not granted" code); `[all]` does **not** include `code`, avoiding "installing everything grants code execution".
- The sandbox **mounts no host capability**: no external functions, no directory mounts, no `os` callback, no host object wrapping — only JSON inputs.
- Determinism by default: frozen clock + fixed timezone + `sleep=zero` + seeded random; the host may explicitly override, and overriding forfeits the cross-machine replay guarantee (written into the docs).
- Limits are configured by the host and **the chain cannot loosen them**: memory, per-feed duration, request timeout, suspension count, recursion depth, with conservative defaults; the worker binary is pinned to an explicit path (no letting `PATH` decide what the sandbox is).
- Two new error codes: `UP2-E2016` (sandbox limit triggered), `UP2-E2017` (sandbox code raised); the `UP2-E2009` wording is generalized from "udf returned…" to "operator returned…".
- **Unified parameter convention between in-chain code and host functions**: both take the upstream value as the first parameter, both pass named configuration as a named object, and both share the same **read-only scope snapshot `ctx`** (implicitly available in `code`; obtained in `udf` by the function declaring a `ctx` parameter, injected by signature, existing single-parameter functions unaffected). `ctx` is a reserved parameter name and is a **read-only JSON snapshot** (handles stripped); it exposes no writable scope and does not pollute the chain's locals.
- Conformance declarations grow from 58 pairs to **59 pairs** (adding `("code", "run")`).
- Docs: `02` gets §6.12 and one row in the slot table; `04` gets "the chain's trust boundary" in four layers (the chain is data / host-registered functions / optional sandbox code / three things never done: no host capability mounts, no snapshot loading, no finding binaries via `PATH`).

**BREAKING**: none. Without the extra installed, existing chains and existing behavior are unchanged character for character.

## Capabilities

### New Capabilities

- `code-execution`: sandboxed execution of in-chain code (operator shape and parameters, dependency gate, isolation boundary, resource limits, determinism, tri-state and error codes, host-side configuration), plus the **shared parameter convention between in-chain code and host functions** (`obj` / named configuration / read-only `ctx` snapshot).

### Modified Capabilities

(None. This repo's `openspec/specs/` has no archived capabilities yet; beyond the external behavior change this change adds no spec.)

## Impact

- Code: new `src/uniparser2/ops/code.py`; changes to `core/errors.py` (+2 codes, 1 wording generalization), **`ops/udf.py` (inject read-only `ctx` by signature, `ctx` reserved-name validation)**, `ops/__init__.py`, `cli/main.py` (`up2 ops` shows dependencies and limits), `pyproject.toml` (extra `code`, `all` excludes it).
- Dependencies: new optional dependency `pydantic-monty>=1.0.0` (with an ~12 MB platform binary runtime); **runtime dependencies remain empty**, `core/` still has zero third-party code, no IO, and is fully synchronous.
- Tests: new `tests/ops/test_code.py` (isolation boundary / limits / determinism / tri-state / parameter shapes / dangling references); **updated `tests/ops/test_udf.py` (`ctx` injection, existing functions that do not declare `ctx`, `ctx` reserved name, read-only snapshot)**; updated operator sets and the 59-pair assertions in `test_registry.py`, `test_cli.py`.
- CI: only one job (3.13 + Ubuntu) installs `[code]` and runs the sandbox cases; the other jobs use `importorskip`; `uv export` + `pip-audit` audit the new entry.
- Docs: design notes 02, 04 and 05 (`docs/specs/0NN-*.md`), `README.md`, `CHANGELOG.md`.
