# Spec Delta

## ADDED Requirements

### Requirement: The ctx surface names one writable root

The `ctx` operator's readable roots SHALL be `globals` and `locals`, and its writable root SHALL be
`locals` alone. A `ctx.get` / `ctx.map` path whose root is neither SHALL be `UP2-E1005` naming the
accepted roots, and a `ctx.set` / `ctx.del` path outside `locals` SHALL be `UP2-E1015`. `fields` SHALL NOT
be accepted by either: it was a second name for `locals` and is retired (`chain-iteration`, "A reference
path may walk an object").

#### Scenario: a write to the retired root

- **WHEN** the chain is `["ctx","set","fields._tmp"]` and it is compiled
- **THEN** compilation SHALL fail with `UP2-E1015`, and the accepted prefixes SHALL be `locals` alone

#### Scenario: a read of the retired root

- **WHEN** the chain is `["ctx","get","fields.title"]` and it is compiled
- **THEN** compilation SHALL fail with `UP2-E1005`, listing `globals` and `locals` as the readable roots

#### Scenario: the writable root still works

- **WHEN** the chain is `[["ctx","set","locals._tmp"], ["ctx","get","locals._tmp"]]` and the input is `7`
- **THEN** the result SHALL be `7`, because `locals` is the scope a write lands in
