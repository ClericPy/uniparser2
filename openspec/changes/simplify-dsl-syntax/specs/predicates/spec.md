# Spec Delta

## ADDED Requirements

### Requirement: `between` decides a half-open numeric interval

The `py` operator SHALL declare `between`, whose parameter is a two-element array `[lo, hi]`, answering
`true` exactly when `lo <= value < hi`. The comparison SHALL be numeric only: no string ordering, no
coercion, and a boolean is not a number, so a non-number on either side MUST be `UP2-E2002` naming the
type that arrived. The bounds MAY be literals or references.

#### Scenario: A value inside the interval

- **WHEN** the chain is `[["py","between",[200,300]]]` and the value is `200`, and then `299`
- **THEN** both results are `true`

#### Scenario: The upper bound is excluded

- **WHEN** the chain is `[["py","between",[200,300]]]` and the value is `300`
- **THEN** the result is `false`

#### Scenario: A value below the interval

- **WHEN** the chain is `[["py","between",[200,300]]]` and the value is `199`
- **THEN** the result is `false`

#### Scenario: A bound from the environment

- **WHEN** the chain is `[["py","between",["$globals.lo","$globals.hi"]]]`, `globals.lo` is `0`,
  `globals.hi` is `10` and the value is `5`
- **THEN** the result is `true`

#### Scenario: A non-number is refused

- **WHEN** the chain is `[["py","between",[200,300]]]` and the value is `"250"`
- **THEN** the outcome is `UP2-E2002`, naming `str`

## MODIFIED Requirements

### Requirement: The selection actions follow Python's value semantics

The `py` operator SHALL declare `or` and `and`, with Python's own semantics, because the common need is
to **choose a value** rather than to compute a boolean. Both SHALL include the **upstream value as the
first operand** and the parameter's array after it, so `["py","or",[a,b]]` SHALL read `value or a or b`:

- `or` SHALL answer with the first truthy operand, otherwise with the last operand, and with the
  upstream value when the array is empty.
- `and` SHALL answer with the first falsy operand, otherwise with the last operand, and with the
  upstream value when the array is empty.

The operands SHALL be a single parameter that is an **array of references or literals** — read after the
field map has computed them, typically into `_` locals — so the two are **eager** and cannot
short-circuit. A `$` reference (`$locals.a`, `$obj`) SHALL be accepted inside the array. Truthiness SHALL
follow Python: `""`, `0`, `[]`, `{}`, `null` and `false` are falsy. The actions MUST NOT require
booleans: answering with the chosen operand is the point, and a boolean is enforced at the predicate
boundary (the L2 `match`), not by the combinator. A parameter that is not an array MUST fail with
`UP2-E2002`.

A **path that cannot be read** inside the array is not an operand: reference resolution fails the whole
stage before the action runs (the rule every operator's parameters follow), so "take A, else B" covers
candidates that are **present but empty** only. Because the upstream value is the first operand, `or` is
also the fallback, so a stage that may answer `None` or `""` needs no separate defaulting action.

#### Scenario: The upstream value is the first operand

- **WHEN** the chain is `[["py","or",["","fallback"]]]` and the value is `"in"`
- **THEN** the result is `"in"`, because the action reads `value or "" or "fallback"`

#### Scenario: An unreadable candidate never reaches `or`

- **WHEN** the chain is `[["py","or",["$locals._a","fallback"]]]` with `_a` **absent**, and then the same
  chain with `["py","const",""],["ctx","set","locals._a"]` in front of it
- **THEN** the first fails with `UP2-E2001` — the reference fails before `or` runs — and the second is
  `"fallback"`

#### Scenario: The first non-empty candidate wins

- **WHEN** the chain is `[["py","const","/p/1"],["ctx","set","locals._b"],["py","const",""],
  ["ctx","set","locals._a"],["py","or",["$locals._a","$locals._b"]]]` and the value is `""`
- **THEN** the result is `"/p/1"` — the chosen operand, not `true`

#### Scenario: Every candidate is falsy

- **WHEN** the chain is `[["py","or",["$locals._a","$locals._b"]]]` with `_a` empty, `_b` `0` and the
  value empty
- **THEN** the result is `0`, the last operand, which is Python's answer

#### Scenario: `and` answers with the first falsy operand

- **WHEN** the chain is `[["py","and",["$locals._a","$locals._b"]]]` with `_a` a non-empty dict, `_b` the
  empty string and the value `true`
- **THEN** the result is `""`

#### Scenario: An empty array

- **WHEN** the chains are `[["py","or",[]]]` and `[["py","and",[]]]` and the value is `"keep"`
- **THEN** both results are `"keep"`, the upstream value, because it is the first operand

#### Scenario: An operand that is not an array

- **WHEN** the chain is `[["py","const","x"],["ctx","set","locals._a"],["py","or","$locals._a"]]`
- **THEN** the outcome is `UP2-E2002`, naming `str` — the operand arrived, it just is not an array
