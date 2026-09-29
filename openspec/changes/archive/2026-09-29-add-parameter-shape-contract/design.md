# Design

## Context

See `proposal.md` — Why, for the measurements that motivate this change. The constraints that shape
the approach:

- **Compilation already has a fixed shape rule.** `core/compile._classify` picks the parameter shape in
  a fixed order: an empty placeholder means "not passed"; a single-key `$`-prefixed object is a
  directive (`{"$lit": …}`, allowed only for a single-parameter action); **zero** remaining parameters
  reject any value; **exactly one** remaining parameter makes the whole slot value that parameter's
  value — a container included; two or more take a named object, a positional array, or a scalar bound
  to the first parameter. The rule is deterministic and documented in `02` §4.
- **Each operator validates its own parameters** in its `precompile(action, params, pointer)` hook, and
  that is where `css` / `css1` / `re` / `ctx` / `json` already reject a container written for a scalar
  parameter with `UP2-E1005` plus a pointer. `py` has the same hook and uses it for two functions only
  (`urlsplit.part`, `parse_time.format`).
- **A container is a legal parameter value.** `["py","default",{"a":1}]` compiles and evaluates to
  `{"a":1}`; `{"$lit": …}` exists as the explicit literal escape. Any rule that treats "container in a
  single-parameter slot" as an error on shape alone would break working chains.
- **The registry already self-describes actions** through `ActionReport` / `report_dicts()`
  (`name` / `summary` / `available` / `requires` / `missing` / `accepts_missing` / `params[]` with
  `name` / `kind` / `required` / `default`), and `up2 ops` renders both a human view and `--json`.
  `Op.action_params(action, action_text)` is the existing hook that reports the parameters the action
  slot itself provides (`css`'s `@<attribute>` providing `attr`).

## Goals / Non-Goals

**Goals:**

- The `py` function table is at parity with every other operator: a container where the function's own
  runtime path requires a scalar is a compile-time diagnostic, not a runtime failure.
- The parameter-slot shape of every action is stated in the operator self-description, in both views,
  so a chain writer (or an LLM reading `--json`) does not have to infer it from the DSL spec.
- No legal chain changes behavior, and the parameter-slot semantics stay exactly as they are.

**Non-Goals:**

- Changing `_classify`, the directive escape, or any other operator's validation (they already behave
  correctly — mesured in the proposal).
- Making the kernel reject a container in a single-parameter slot by shape. That would break the legal
  container value above; the knowledge lives with the function that requires a scalar.
- Covering parameters that the operator merely coerces (`str(sep)`, `str(lang)`): a container there
  produces nonsense rather than a failure, and rejecting it would change today's accepted behavior.
- Any new error code, dependency, or configuration surface.

## Decisions

### D1. The check lives in `py`'s existing `precompile` hook, not in the kernel

*Alternatives*: (a) a kernel-level rule in `_classify`; (b) a new validation framework for parameter
types.

`py` is the only operator that needs the check; the other five parameterized operators already
implement it. A kernel rule cannot tell "this container is a malformed named-object binding" from
"this container is the parameter's value", so it would have to break the legal value form (D6). The
operator hook is also the layer the architecture assigns parameter knowledge to (`01` §7: every
operator declares and validates its own arguments), so no new machinery is introduced — `py` gains a
table and one call, in the same shape as `_check_url_part` / `_check_time_format`.

### D2. `UP2-E1005` is reused; no error code is added

`UP2-E1005` ("parameter schema validation failed") is what every sibling operator already raises for
this class of mistake, and what `_named_params` raises for an unknown parameter. Reusing it keeps
`CODES`, the conformance counts (59 pairs, 25 codes) and the diagnostic shape unchanged. A dedicated
code would only restate "the parameter's value has the wrong type" and would add a declaration to
maintain.

### D3. The covered parameters are declared as data, justified one by one by their runtime path

The check is a table: function name → parameter name → required scalar type, plus the decision to
reject a container. A parameter is covered when a container either raises inside the operator or
violates a guard the operator already applies at runtime:

| Function | Parameter | Runtime behavior on a container | Required |
|---|---|---|---|
| `urljoin` | `base` | `isinstance(base, str)` guard → `UP2-E2002` | string |
| `slice` | `spec` | `isinstance(spec, str)` guard → `UP2-E2002` | string |
| `split` | `sep` | `isinstance(sep, str)` guard → `UP2-E2002` | string |
| `split` | `maxsplit` | `int(container)` raises `TypeError`, which the operator does not catch | integer |
| `getitem` | `index` | same `int(container)` path as above | integer |
| `get` | `key` | explicit `isinstance(key, (list, dict))` guard → `UP2-E2002` | string |
| `replace` | `old` / `new` | `isinstance(..., str)` guard → `UP2-E2002` | string |
| `sort` | `key` | enum check (`None` / `""` / `str` / `int` / `float`), unknown → `UP2-E2005` | one of the enum |
| `urlsplit` | `part` | enum check, already performed in `precompile` | one of the enum |
| `parse_time` | `format` | non-empty-string check, already performed in `precompile` | string |

Excluded on purpose: `default.value` (any JSON value — the spec pins this), `join.sep` and
`parse_time.lang` (coerced with `str()`, so a container is nonsense rather than a failure).

Shapes beyond containers stay the runtime's business: `kind` (`literal` / `ref_or_literal`) already
decides reference-versus-literal at compile time, and a *scalar of the wrong type* (for example
`["py","split",{"sep":1}]`) is out of scope here — the guard message and fix already say what is
wrong, and a full type system for 31 functions is not what this change is for.

### D4. The slot shape is derived from the parameters the action still has to fill

The report computes the shape from the action's declared parameters minus the ones the action slot
already provides — the same subtraction compilation performs (`_build_params` line "active = params
not in preset"), using the existing `Op.action_params` hook. Reported as:

- **no parameter** — zero remaining (write two positions, or `""`);
- **the value itself** — exactly one remaining;
- **a named object** — two or more (a positional array is equally accepted).

Deriving rather than hand-annotating keeps the report and the compiler from drifting: the `css` /
`css1` attribute accessor is the case that proves the subtraction is needed (its `attr` comes from the
accessor, leaving only the selector).

### D5. One field, `param_form`, worded the same in both views

`ActionReport` gains `param_form: str` and `report_dicts()` gains `"param_form"`, with the machine
values `"none"` / `"value"` / `"named"` (the existing report fields are snake_case machine tokens). The
human `up2 ops` view prints the same three states as words, so the two views agree as the spec
requires. Adding a field is what the capability self-description is for (`01` §7), and it is the only
public surface this change touches.

### D6. Nothing is reinterpreted, and there is no auto-correction

*Alternative rejected*: treat a mapping whose keys are all declared parameter names as a named binding
for a single-parameter action, i.e. make `{"base": …}` mean `base = …`.

That would give one written shape two meanings depending on key collision — precisely the ambiguity
the DSL was redesigned to remove (design note `07` §1.5, the R1 root cause). The compile step keeps
treating a container as a value, the *check* reports the mistake with the correct writing in its fix
line, and `{"$lit": …}` stays the only explicit literal escape.

## Risks / Trade-offs

- **A legal chain could be rejected** if a covered function ever legitimately needs a container for
  that parameter. → The table only lists parameters with a runtime type guard or enum check, and the
  regression guard `["py","default",{"a":1}]` (the any-typed parameter) plus
  `["py","split",{"sep":",","maxsplit":1}]` (the multi-parameter named form) are pinned by tests.
- **The report's shape could drift from what compilation accepts.** → The shape is derived from the
  same preset subtraction compilation performs, and a test asserts the report's shape for one action of
  each state, including the preset case.
- **The tightening is a behavior change for chains written today** (they pass `lint`, die at runtime). →
  Those chains are already failures; the change only makes the failure earlier and its message
  actionable. It is recorded in the CHANGELOG and the design notes.
- **Coverage of the check is limited to the declared table**, so a future `py` function with a new
  scalar parameter is not covered automatically. → The table sits beside the function table in
  `pyops.py`, and `up2 ops` now states the shape of every action, which is the reminder.
- **The open action space reports the shape compilation sees.** `udf` declares its actions by host
  registration and models the keyword-argument object as a single parameter, so it reports `value`,
  while its evaluation additionally requires that value to be an object. → Recorded in the spec as an
  explicit scenario and in `02` §6.10; the writing that fails does so at runtime with a fix line that
  names the object form. A schema-level way to declare an object-valued parameter is listed as an open
  question rather than invented here.

## Migration Plan

None needed: no stored artifact, dependency, configuration or public API is removed, and the pair
count stays 59. Rolling back means reverting the commit; the only residue would be the added report
field, which is additive.

## Open Questions

- Whether a container for a coerced parameter (`join.sep`, `parse_time.lang`) should also become a
  compile-time error. Deferrable: it changes today-accepted behavior without fixing a failure, and the
  report now shows the shape, so the mistake is at least visible.
- Whether the same declarative per-parameter type table should be extracted into a shared registry
  type. Deferrable: with one operator needing it, a shared abstraction would be an interface built for
  a single implementation.
