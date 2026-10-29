# Spec Delta

## ADDED Requirements

### Requirement: A literal that starts with `$` is quoted at any depth

In a parameter whose kind is `ref_or_literal`, an object with exactly one `$`-prefixed key MUST be
read as a directive at every depth, not only at the parameter slot. `{"$lit": value}` MUST produce
`value` verbatim. Any other such directive MUST be rejected at compile time with `UP2-E1005`,
naming the escape.

#### Scenario: The escape at the parameter slot

- **WHEN** the chain is `["py", "default", {"$lit": "$100"}]` and it is evaluated on `null`
- **THEN** compilation succeeds and the result is the string `"$100"`

#### Scenario: The escape inside a positional array

- **WHEN** the chain is `["py", "or", [{"$lit": "$a"}, "fallback"]]` and it is evaluated
- **THEN** compilation succeeds and the result is the string `"$a"` — not the object
  `{"$lit": "$a"}`, and not a reference read

#### Scenario: The escape inside a named object

- **WHEN** the chain is `["code", {"src": "x", "inputs": {"a": {"$lit": "$k"}}}]` and it is compiled
- **THEN** compilation succeeds and the value of the `a` input is the literal `"$k"`

#### Scenario: An unsupported directive at depth

- **WHEN** the chain is `["py", "or", [{"$price": 1}, "fallback"]]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` and the fix line shows `{"$lit": …}`

#### Scenario: A literal parameter keeps the dollar sign

- **WHEN** the chain is `["py", "replace", ["$locals.old", "X"]]` and it is evaluated on
  `"$locals.old"` repeated
- **THEN** the literal text `$locals.old` is replaced, because both of `replace`'s parameters are
  `literal`

### Requirement: The escape respects each parameter kind

The directive rule MUST apply only where a value may be either a reference or a literal. A parameter
whose kind is `literal` MUST keep a leading `$` as text, and a parameter whose kind is `ref` MUST
NOT accept a directive.

#### Scenario: A ref-only parameter refuses the escape

- **WHEN** a parameter declared `ref` receives `{"$lit": "x"}` and the chain is compiled
- **THEN** compilation fails with `UP2-E1007`, because a parameter that must be a reference has no
  literal branch

### Requirement: A `$`-prefixed mistake reports the way out

A diagnostic raised because a value was read as a reference or a path when it was meant as text MUST
state how to write the text instead. An unknown reference root (`UP2-E1006`) MUST name
`{"$lit": …}`. A `ctx` path rejected at compile time (`UP2-E1005` for a read, `UP2-E1015` for a
write) MUST say, when the path starts with `$`, that a `ctx` path is written bare.

#### Scenario: An unknown root names the escape

- **WHEN** the chain is `["py", "default", "$100"]` and it is compiled
- **THEN** compilation fails with `UP2-E1006`, and the fix line names `{"$lit": …}` alongside the
  reserved roots

#### Scenario: A `$`-prefixed ctx read path names the bare spelling

- **WHEN** the chain is `["ctx", "get", "$locals.k"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005`, and the fix line says to drop the leading `$`

#### Scenario: A `$`-prefixed ctx write path names the bare spelling

- **WHEN** the chain is `["ctx", "set", "$locals.k"]` and it is compiled
- **THEN** compilation fails with `UP2-E1015`, and the fix line says to drop the leading `$`
