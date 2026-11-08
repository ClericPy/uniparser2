# Proposal

## Why

`up2 lint` is supposed to reject a bad chain before it runs — that is a kernel invariant, and
`dsl-operators` states it for scalar parameters. The implementation only gets half of it: a JSON
**container** written where a scalar belongs is rejected, but a scalar of the **wrong type**, or a
string the function cannot parse, passes lint and fails during evaluation. Measured on this commit:

| Chain | Today |
|---|---|
| `["py","urljoin",42]` | lints; evaluation fails `UP2-E2002` with an **empty fix line** |
| `["py","slice","bogus"]` | lints; evaluation fails `UP2-E2005` |
| `["py","split",{"sep":",","maxsplit":"x"}]` | lints; evaluation fails `UP2-E2005` |
| `["py","split",{"sep":42}]` | lints; evaluation fails `UP2-E2002` |
| `["py","replace",[42,"x"]]` | lints; evaluation fails `UP2-E2002` |
| `["py","getattr",42]` | lints; evaluation fails `UP2-E2002` |

Every one of these values is a literal, so the compiler knows it; every one of them is rejected
deterministically by the runtime, so there is nothing to defer. The rule the repository states —
"bad chains fail at compile time, with a `UP2-E*` code and a JSON Pointer" — is simply not met here.

## What Changes

- **The scalar table carries the accepted Python types**, not only a prose expectation, and a literal
  of another type is `UP2-E1005` at compile time with the parameter's pointer and the accepted writing
  in the fix line.
- **The two strings the runtime parses are parsed at compile time** with the runtime's own parser:
  `slice.spec` (a slice notation) and `split.maxsplit` (an integer, where `null` and `""` keep their
  documented "no limit" meaning).
- **A container stays a compile-time error** as before, and `py.default.value` / `join.sep` /
  `parse_time.lang` keep accepting what they coerce today — the check is about values the runtime
  rejects, not about values it transforms.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `dsl-operators`: the compile-time validation of a scalar parameter covers the literal's **type** and
  the **values the runtime parses**, not only the container case.

## Impact

- `ops/pyops.py`: `_SCALAR_PARAMS` gains the accepted types, `_check_scalar_params` gains the type and
  value checks, and the value checks reuse `_parse_slice_spec` / the runtime's integer rule.
- `02` §6.4 (the `py` table's validation note), `docs/operator-reference.md`, `CHANGELOG.md`.
- Tests: the six wrong-typed cases above plus the two unparsable strings.
- **Behaviour narrowing**: a chain that linted and then failed at evaluation now fails at lint. No
  chain that produced a value changes meaning.
