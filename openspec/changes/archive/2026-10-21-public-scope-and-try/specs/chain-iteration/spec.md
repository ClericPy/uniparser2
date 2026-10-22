# Spec Delta

## ADDED Requirements

### Requirement: A run carries a `public` scope, shared by every node

A run SHALL expose a third scope, `public`, beside `globals` and `locals`: it is **writable** and
**readable from any node of the run**, and it lives exactly as long as the run. It SHALL NOT be part
of the chain data, so it never enters the fingerprint: a run's `public` values are runtime notes, not
a property of the chain.

The reference root `public` SHALL be reserved, and `$public.<path>` SHALL read it. A write through
`ctx.set` SHALL accept a `public.` path; a write to `globals`, to a step's product or to any other
root SHALL still be refused.

`globals` SHALL stay read-only and `locals` SHALL stay private to the scope that wrote it, so the
three scopes read as constants / shared / private.

#### Scenario: A node writes and the next node reads

- **WHEN** a step's field map writes `["ctx","set","public.page"]` and a later step reads
  `$public.page`
- **THEN** the later step SHALL read the written value

#### Scenario: `public` is not chain data

- **WHEN** a run writes `public.page` and the chain is fingerprinted
- **THEN** the fingerprint SHALL be the same as it was before the write

#### Scenario: A write outside the writable roots is refused

- **WHEN** a step writes `["ctx","set","globals.page"]` or `["ctx","set","in.page"]`
- **THEN** compilation SHALL fail with `UP2-E1015`, naming the writable roots

#### Scenario: `public` may be collected like any scope

- **WHEN** the chain is `[["ctx","dict",{"p":"public.page"}]]`
- **THEN** the outcome SHALL be `Ok({"p": <the value of public.page>})`

### Requirement: A `try` directive guards the next stage only

A chain MAY carry a `try` stage whose parameter is one policy: `raise`, `skip` or `break`. It SHALL
guard **the stage immediately after it** and nothing else.

- `raise` SHALL be the default behaviour of a failing stage: the chain stops and the run fails.
- `skip` SHALL keep the value the chain already carried into the failing stage and continue with the
  next stage.
- `break` SHALL end the chain at that point and answer with the value the chain carried into the
  failing stage.

A guarded stage that **succeeds** SHALL disarm the guard, so a `try` never affects a later failure.
Two `try` stages in a row SHALL be a compile error, and a `try` as the last stage of a chain SHALL be a
compile error, because it would guard nothing.

The policies are **control, not degradation**: `skip` and `break` keep a value the chain already had;
neither of them SHALL turn an exception into a value.

#### Scenario: A guarded failure is skipped

- **WHEN** the chain is `[["const", "keep"], ["try", "skip"], ["py", "int", ""]]` and the input is
  `"not-a-number"`
- **THEN** the outcome SHALL be `Ok("keep")`

#### Scenario: A guarded failure breaks the chain

- **WHEN** the chain is `[["const", "keep"], ["try", "break"], ["py", "int", ""]]` and the input is
  `"not-a-number"`
- **THEN** the outcome SHALL be `Ok("keep")`, and the stages after the guarded one SHALL NOT be
  evaluated

#### Scenario: A guarded success disarms the guard

- **WHEN** the chain is `[["const", ""], ["try", "skip"], ["py", "strip", ""], ["py", "int", ""]]` and
  the input is `"not-a-number"`
- **THEN** the chain SHALL fail at the `py.int` stage — the guard covered only the stage next to it

#### Scenario: An unguarded failure fails the run

- **WHEN** the chain is `[["const", "keep"], ["py", "int", ""]]` and the input is `"not-a-number"`
- **THEN** the run SHALL fail with `UP2-E2005`

#### Scenario: Two guards in a row are a compile error

- **WHEN** the chain is `[["try", "skip"], ["try", "skip"], ["py", "strip", ""]]`
- **THEN** compilation SHALL fail with `UP2-E1005`, naming the rule

#### Scenario: A guard at the end of a chain is a compile error

- **WHEN** the chain is `[["py", "strip", ""], ["try", "skip"]]`
- **THEN** compilation SHALL fail with `UP2-E1005`, naming the rule
