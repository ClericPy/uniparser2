# predicates Specification

## Purpose

The chain layer needs to **decide** things — whether a response is the page it was expecting, whether a
document has the structure a parse rule needs, which of several candidates actually carries a value —
and every decision has to be writable as data, checkable before a run and readable by whoever (or
whatever) wrote the chain. This capability is the boolean vocabulary that makes that possible: one-stage
comparisons (`==`, `!=`, `<`, `<=`, `>`, `>=`), Python's membership test (`in`), Python's value-selecting
`or` / `and`, and `exists` on the selector family.

Two properties are the point of the whole capability. First, a predicate **answers with a value** rather
than leaning on the missing-value policy: `css.nodes` reports `Missing` when nothing matches, so its
result depends on `on_missing`, while `css.exists` answers `true` / `false` under every policy — a
predicate that changes its answer with a policy is not a predicate. Second, the behaviour is **Python's**,
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

The `py` operator SHALL declare `==`, `!=`, `<`, `<=`, `>` and `>=` — **Python's own spellings** — each
comparing the upstream value with its single parameter, which MAY be a literal or a reference. `==` and
`!=` SHALL answer with a boolean using **Python's own equality**: deep equality for containers, no string
coercion (`200` is not `"200"`), and — because `bool` is an `int` in Python — `1` **is** equal to `true`
and `0` to `false`. The four ordering actions SHALL accept comparable pairs only — both numbers or both
strings, where a boolean is **not** a number — and any other pair MUST fail with `UP2-E2002`, naming both
types; a Python `TypeError` MUST NOT escape as `UP2-E2099`. None of the six actions SHALL consult the
missing-value policy for their own result: they answer `true` or `false`, and a missing upstream value
still short-circuits before the action runs.

The two families therefore disagree on booleans by design: `["py","==",1]` on `true` is `true` (Python's
equality), while `["py","<",1]` on `true` is `UP2-E2002` (a boolean is not ordered against a number).

A **bare `null` cannot be written as the parameter**: the parameter machinery cannot tell a written
`null` from an omitted parameter (`core/compile._is_empty_placeholder`), so `["py","==",null]` fails at
compile time with `UP2-E1005` ("missing required parameter") before anything runs. A null comparison is
written `["py","in",[null]]`. That limitation belongs to every scalar parameter in the DSL, not to these
actions.

`!=` against a boolean literal is also how a boolean is negated, which is why no `not` action is added.

#### Scenario: A status code

- **WHEN** the chain is `[["json","status"], ["py","==",200]]` and the value is `{"status": 200}`
- **THEN** the result is `true`

#### Scenario: Equality does not coerce types

- **WHEN** the chain is `["py","==",200]` and the value is `"200"`
- **THEN** the result is `false`

#### Scenario: An incomparable pair

- **WHEN** the chain is `["py","<",10]` and the value is `"abc"`
- **THEN** the outcome is `UP2-E2002`, naming `str` and `int`

#### Scenario: A reference as the second operand

- **WHEN** the chain is `[["py",">","$globals.min_len"]]` and `globals.min_len` is `3` and the value is `5`
- **THEN** the result is `true`

#### Scenario: Negating a boolean

- **WHEN** the chain is `[["py","in",["x"]], ["py","!=",true]]` and the value is `"y"`, and then `"x"`
- **THEN** the results are `true` and `false`

### Requirement: `in` keeps Python's operand order

The `py` operator SHALL declare `in`, whose parameter is the **container** and whose upstream value is
the element looked up in it: a `str` parameter answers a substring test, a `list` parameter a membership
test (deep equality) and a `dict` parameter a key test. Any other parameter type MUST fail with
`UP2-E2002`. The answer is a boolean and never comes from the missing-value policy. To ask whether the
upstream value *contains* something, the element is written in front
(`[["const","/public/"],["py","in","$locals.url"]]`), because the operands keep Python's order.

#### Scenario: A list of allowed values

- **WHEN** the chain is `[["py","in",[200,301,302]]]` and the value is `301`, and then `404`
- **THEN** the results are `true` and `false`

#### Scenario: A dict key

- **WHEN** the chain is `[["py","in",{"status": 200}]]` and the value is `"status"`
- **THEN** the result is `true`

#### Scenario: A substring, with the element in front

- **WHEN** the chain is `[["const","/public/1681/a.html"],["ctx","set","locals._url"],
  ["const","/public/"],["py","in","$locals._url"]]`
- **THEN** the result is `true`

#### Scenario: A parameter that is not a container

- **WHEN** the chain is `[["py","in",7]]` and the value is `"x"`
- **THEN** the outcome is `UP2-E2002`

### Requirement: The selection actions follow Python's value semantics

The `py` operator SHALL declare `or` and `and`, with Python's own semantics, because the common need is
to **choose a value** rather than to compute a boolean:

- `or` SHALL answer with the first truthy operand, otherwise with the last operand, and `false` for an
  empty array.
- `and` SHALL answer with the first falsy operand, otherwise with the last operand, and `true` for an
  empty array.

The operands SHALL be a single parameter that is an **array of references or literals** — read after the
field map has computed them, typically into `_` locals — so the two are **eager** and cannot
short-circuit. Truthiness SHALL follow Python: `""`, `0`, `[]`, `{}`, `null` and `false` are falsy. The
actions MUST NOT require booleans: answering with the chosen operand is the point, and a boolean is
enforced at the predicate boundary (the L2 `match`), not by the combinator. A parameter that is not an
array MUST fail with `UP2-E2002`.

A **missing** reference inside the array is not an operand: reference resolution short-circuits the whole
stage before the action runs (the rule every operator's parameters follow), so "take A, else B" covers
candidates that are **present but empty** only. A candidate that may be absent is made present first —
`[["css1","text","h1"],["py","default",""]]`, with `default` accepting the missing value — and only then
handed to `or`. Under `on_missing="empty"` (the default) a missing reference lands as an empty string,
which `or` does skip, but that is the policy doing the work rather than the action.

#### Scenario: A missing candidate never reaches `or`

- **WHEN** the chain is `[["py","or",["$locals._a","fallback"]]]` with `_a` **absent**, evaluated with
  `on_missing="drop"`, and then with `["const",""],["ctx","set","locals._a"]` in front of it
- **THEN** the first is `Missing` — the reference short-circuits before `or` runs — and the second is
  `"fallback"`

#### Scenario: The first non-empty candidate wins

- **WHEN** the chain is `[["const",""],["ctx","set","locals._a"],["const","/p/1"],["ctx","set",
  "locals._b"],["py","or",["$locals._a","$locals._b"]]]` and the value is a string
- **THEN** the result is `"/p/1"` — the chosen operand, not `true`

#### Scenario: Every candidate is falsy

- **WHEN** the chain is `[["py","or",["$locals._a","$locals._b"]]]` with `_a` empty and `_b` `0`
- **THEN** the result is `0`, the last operand, which is Python's answer

#### Scenario: `and` answers with the first falsy operand

- **WHEN** the chain is `[["py","and",["$locals._a","$locals._b"]]]` with `_a` a non-empty dict and `_b`
  the empty string
- **THEN** the result is `""`

#### Scenario: An empty array

- **WHEN** the chains are `[["py","or",[]]]` and `[["py","and",[]]]`
- **THEN** the results are `false` and `true` respectively

#### Scenario: An operand that is not an array

- **WHEN** the chain is `[["const","x"],["ctx","set","locals._a"],["py","or","$locals._a"]]` and it is
  evaluated with `on_missing="drop"`
- **THEN** the outcome is `UP2-E2002`, naming `str` — the operand arrived, it just is not an array

### Requirement: The selector family answers existence with a boolean

`css` and `css1` SHALL declare an `exists` action that answers whether the selector matches at least
one node. Unlike `nodes` — which reports `Missing` when nothing matches, and therefore lets the
missing-value policy decide the outcome — `exists` MUST answer `true` or `false` and MUST NOT report
`Missing`, so a chain can use it as a predicate regardless of the policy in force.

#### Scenario: A structure that matches

- **WHEN** the chain is `[["css","exists","ul.list li"]]` and the value is an HTML document with that
  structure
- **THEN** the result is `true`

#### Scenario: A structure that does not match, under every policy

- **WHEN** the chain is `[["css","exists",".nope"]]` and the value is an HTML document without it
- **THEN** the result is `false` under `on_missing="empty"`, `"drop"`, `"none"` and `"raise"` alike

#### Scenario: The neighbour action still reports a missing value

- **WHEN** the chain is `[["css","nodes",".nope"]]` and it is evaluated with `on_missing="drop"`
- **THEN** the outcome is `Missing` — `exists` is a new action, not a change to `nodes`
