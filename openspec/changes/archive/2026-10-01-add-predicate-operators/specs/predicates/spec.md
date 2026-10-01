# Spec Delta

## ADDED Requirements

### Requirement: A comparison action decides a predicate in one stage

The `py` operator SHALL declare `==`, `!=`, `<`, `<=`, `>` and `>=` — **Python's own spellings** — each
comparing the upstream value with its single parameter, which MAY be a literal or a reference. `==` and
`!=` SHALL accept any two JSON values and answer with a boolean (deep equality for containers, no type
coercion: `200` and `"200"` are not equal). The four ordering actions SHALL accept comparable pairs only
— both numbers or both strings — and any other pair MUST fail with `UP2-E2002`, naming both types; a
Python `TypeError` MUST NOT escape as `UP2-E2099`. None of the six actions SHALL consult the
missing-value policy for their own result: they answer `true` or `false`, and a missing upstream value
still short-circuits before the action runs.

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
