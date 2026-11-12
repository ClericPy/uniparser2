# predicates Specification

## Purpose

The chain layer needs to **decide** things — whether a response is the page it was expecting, whether a
document has the structure a parse rule needs, which of several candidates actually carries a value —
and every decision has to be writable as data, checkable before a run and readable by whoever (or
whatever) wrote the chain. This capability is the boolean vocabulary that makes that possible: one-stage
comparisons (`==`, `!=`, `<`, `<=`, `>`, `>=`), Python's membership test (`in`), Python's value-selecting
`or` / `and`, and `exists` on the selector family.

Two properties are the point of the whole capability. First, a predicate **answers with a value** rather
than leaving the caller to interpret an absence: `css.nodes` answers `[]` when nothing matches, so a
caller has to decide what that means, while `css.exists` answers `true` / `false` outright — a predicate
that leaves its answer to the caller is not a predicate. Second, the behaviour is **Python's**,
spellings included, so an author (or a model) that knows the language already knows the semantics: `or`
answers with the first truthy operand rather than with a boolean, `in` keeps its operand order (the
parameter is the container), and negation is `!=` against a boolean instead of a separate action. Where
Python would raise, the engine reports `UP2-E2002` naming both types, so an incomparable pair is a
diagnosis rather than a backstop.

Strictness lives at the predicate boundary (the L2 `match` requires a boolean), not in these actions,
which is what lets one action serve both selection and judgement. The actions are **eager** — they read
values the field map has already computed — so a condition costs what it costs even when an earlier one
decided the result; ordering the field map cheapest-first is the author's lever.

## Requirements

### Requirement: A comparison action decides a predicate in one stage

The `py` operator SHALL declare `==`, `!=`, `<`, `<=`, `>` and `>=` — Python's spellings — each
comparing the upstream value with one parameter that MAY be a literal or a reference. `==` and `!=`
MUST use Python's equality: deep equality for containers, no coercion (`200` is not `"200"`), and `1`
equals `true`. The ordering actions MUST accept both numbers or both strings only, where a boolean is
not a number; any other pair MUST fail with `UP2-E2002`, naming both types.

#### Scenario: A status code

- **WHEN** the chain is `[["json","status"], ["py","==",200]]` and the value is `{"status": 200}`
- **THEN** the result is `true`

#### Scenario: Equality does not coerce types

- **WHEN** the chain is `["py","==",200]` and the value is `"200"`
- **THEN** the result is `false`

#### Scenario: An incomparable pair

- **WHEN** the chain is `["py","<",10]` and the value is `"abc"`
- **THEN** the outcome is `UP2-E2002`, naming `str` and `int`

### Requirement: A comparison answers a boolean, and `null` is written with `in`

Every comparison action SHALL answer `true` or `false`; none depends on how a no-match settles, and an
unreadable path fails the stage before the action runs. A bare `null` parameter MUST fail at compile time
with `UP2-E1005`, because a written `null` is indistinguishable from an omitted parameter; a null
comparison is written `["py","in",[null]]`. `!=` against a boolean is how a boolean is negated, so no
`not` action is added.

#### Scenario: A reference as the second operand

- **WHEN** the chain is `[["py",">","$globals.min_len"]]` and `globals.min_len` is `3` and the value is `5`
- **THEN** the result is `true`

#### Scenario: Negating a boolean

- **WHEN** the chain is `[["py","in",["x"]], ["py","!=",true]]` and the value is `"y"`, and then `"x"`
- **THEN** the results are `true` and `false`

#### Scenario: A bare null comparison is a compile error

- **WHEN** the chain is `[["py","==",null]]` and it is compiled
- **THEN** compilation fails with `UP2-E1005`, naming the missing parameter

### Requirement: `in` keeps Python's operand order

The `py` operator SHALL declare `in`, whose parameter is the **container** and whose upstream value is
the element looked up in it: a `str` parameter answers a substring test, a `list` parameter a membership
test (deep equality) and a `dict` parameter a key test. Any other parameter type MUST fail with
`UP2-E2002`. To ask whether the upstream value *contains* something, the element is written in front
(`[["py","const","/public/"],["py","in","$locals.url"]]`).

#### Scenario: A list of allowed values

- **WHEN** the chain is `[["py","in",[200,301,302]]]` and the value is `301`, and then `404`
- **THEN** the results are `true` and `false`

#### Scenario: A dict key

- **WHEN** the chain is `[["py","in",{"status": 200}]]` and the value is `"status"`
- **THEN** the result is `true`

#### Scenario: A substring, with the element in front

- **WHEN** the chain is `[["py","const","/public/1681/a.html"],["ctx","set","locals._url"],
  ["py","const","/public/"],["py","in","$locals._url"]]`
- **THEN** the result is `true`

### Requirement: `in` always answers a boolean

The answer of `in` SHALL always be a boolean. A path that cannot be read fails the stage before the
action runs, and nothing else changes the answer.

#### Scenario: A parameter that is not a container

- **WHEN** the chain is `[["py","in",7]]` and the value is `"x"`
- **THEN** the outcome is `UP2-E2002`

### Requirement: The selection actions follow Python's value semantics

The `py` operator SHALL declare `or` and `and`, with Python's own value semantics. Both MUST include
the **upstream value as the first operand** and the parameter's array after it, so
`["py","or",[a,b]]` reads `value or a or b`. `or` SHALL answer the first truthy operand, otherwise the
last, and the upstream value for an empty array; `and` SHALL answer the first falsy operand, otherwise
the last, and the upstream value for an empty array.

#### Scenario: The upstream value is the first operand

- **WHEN** the chain is `[["py","or",["","fallback"]]]` and the value is `"in"`
- **THEN** the result is `"in"`, because the action reads `value or "" or "fallback"`

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

### Requirement: The selection operands are eager and any JSON value

The operands MUST be a single parameter that is an **array of references or literals**, read after the
field map has computed them, so the actions are eager and cannot short-circuit. A `$` reference
(`$locals.a`, `$obj`) SHALL be accepted inside the array. Truthiness MUST follow Python: `""`, `0`, `[]`,
`{}`, `null` and `false` are falsy. The actions MUST NOT require booleans: answering with the chosen
operand is the point. A parameter that is not an array MUST fail with `UP2-E2002`.

#### Scenario: A falsy candidate is skipped

- **WHEN** the chain is `[["py","or",[0,"",false,"x"]]]` and the value is `null`
- **THEN** the result is `"x"`

#### Scenario: A parameter that is not an array

- **WHEN** the chain is `[["py","const","x"],["ctx","set","locals._a"],["py","or","$locals._a"]]`
- **THEN** the outcome is `UP2-E2002`, naming `str` — the operand arrived, it just is not an array

### Requirement: A missing path is not an operand

A **path that cannot be read** inside the array MUST fail the whole stage before the action runs, so
"take A, else B" covers candidates that are **present but empty** only. Because the upstream value is
the first operand, `or` is also the fallback, so a stage that may answer `null` or `""` needs no
separate defaulting action.

#### Scenario: An unreadable candidate never reaches `or`

- **WHEN** the chain is `[["py","or",["$locals._a","fallback"]]]` with `_a` **absent**, and then the same
  chain with `["py","const",""],["ctx","set","locals._a"]` in front of it
- **THEN** the first fails with `UP2-E2001` — the reference fails before `or` runs — and the second is
  `"fallback"`

### Requirement: The selector family answers existence with a boolean

`css` and `css1` SHALL declare an `exists` action that answers whether the selector matches at least
one node. Unlike `nodes` — which answers `[]` when nothing matches, so a caller has to decide what an
empty value means — `exists` MUST answer `true` or `false`, so a chain can use it as a predicate without
a second decision.

#### Scenario: A structure that matches

- **WHEN** the chain is `[["css","exists","ul.list li"]]` and the value is an HTML document with that
  structure
- **THEN** the result is `true`

#### Scenario: A structure that does not match

- **WHEN** the chain is `[["css","exists",".nope"]]` and the value is an HTML document without it
- **THEN** the result is `false`

#### Scenario: The neighbour action answers the shape's empty value

- **WHEN** the chain is `[["css","nodes",".nope"]]`
- **THEN** the outcome is `[]` — `exists` is a boolean view of the same fact, not a change to `nodes`

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
