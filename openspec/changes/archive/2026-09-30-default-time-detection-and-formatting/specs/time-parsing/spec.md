# Spec Delta

## Purpose

Define the decision order of `py.parse_time`: which input shapes are read with no parameter at all, how
an explicit layout and a language interact with that default, how an ambiguous numeric date and the base
clock of a relative expression are controlled, and what happens when the optional engine is not
installed.

## ADDED Requirements

### Requirement: Natural-language input is parsed without a parameter

When the chain gives no explicit `format` and the built-in table matches nothing, `py.parse_time` SHALL
pass the text to the optional natural-language engine (`dateparser`) with automatic language detection,
so a chain does not have to name a language to read one. The canonical output stays
`%Y-%m-%d %H:%M:%S`.

When the engine is not installed, the outcome MUST be `UP2-E2008`, naming the extra to install; a chain
MUST NOT return a different value because an optional engine is absent. When the engine is installed and
cannot read the text, the outcome MUST be `UP2-E2007`.

#### Scenario: A French date without parameters

- **WHEN** the chain is `["py", "parse_time", ""]` and the value is `24 septembre 2026`
- **THEN** the result is `2026-09-24 00:00:00` (with the engine installed)

#### Scenario: A relative expression without parameters

- **WHEN** the chain is `["py", "parse_time", ""]` and the value is `yesterday`
- **THEN** the result is the canonical form of the day before the base clock

#### Scenario: A German date without parameters

- **WHEN** the chain is `["py", "parse_time", ""]` and the value is `24. September 2026`
- **THEN** the result is `2026-09-24 00:00:00` (with the engine installed)

#### Scenario: A machine shape never needs the engine

- **WHEN** the chain is `["py", "parse_time", ""]` and the value is `Sep 24, 2026`
- **THEN** the result is `2026-09-24 00:00:00` and the optional engine is not imported

#### Scenario: The engine is missing

- **WHEN** the engine is not installed and the value is `24 septembre 2026`
- **THEN** the outcome is `UP2-E2008` and the fix line names the extra to install

#### Scenario: Nothing can read the text

- **WHEN** the engine is installed and the value is `not a timestamp at all`
- **THEN** the outcome is `UP2-E2007`

### Requirement: The ambiguous numeric order is an explicit parameter

`py.parse_time` SHALL accept an optional `date_order` parameter whose value is one of `MDY`, `DMY` or
`YMD`, validated at compile time with `UP2-E1005`. It MUST decide the order of an ambiguous numeric
writing in **both** places where such a writing can be read — the built-in table's `dd/mm/yyyy` /
`mm/dd/yyyy` pair and the natural-language engine — so that a plain date and a date with a time part
cannot give different dates. When `date_order` is absent the default MUST be `DMY`, and that default
MUST be stated in the design note and in the operator reference. `YMD` has no writing of its own in the
table's pair, so it MUST keep the default order there and only affect the engine.

#### Scenario: The default is day first, in both writings

- **WHEN** the chains `["py", "parse_time", ""]` receive `03/04/2026` and `03/04/2026 15:30`
- **THEN** both results are `2026-04-03` (the same date, at 00:00:00 and 15:30:00)

#### Scenario: A month-first order changes both writings

- **WHEN** the chain is `["py", "parse_time", {"date_order": "MDY"}]` and the values are `03/04/2026` and
  `03/04/2026 15:30`
- **THEN** both results are `2026-03-04` (the same date, at 00:00:00 and 15:30:00)

#### Scenario: The parameter overrides the language preference

- **WHEN** the chain is `["py", "parse_time", {"lang": "de", "date_order": "MDY"}]` and the value is
  `03/04/2026 15:30`
- **THEN** the result is `2026-03-04 15:30:00`

#### Scenario: An unknown order is a compile error

- **WHEN** the chain is `["py", "parse_time", {"date_order": "YDM"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the parameter, and the fix line names the accepted values

### Requirement: Relative expressions have a pinnable base clock

`py.parse_time` SHALL accept an optional `now` parameter that fixes the base clock of a relative
expression (`yesterday`, `3 days ago`). The parameter is a `ref_or_literal` value: it SHALL accept the
canonical layout as a literal and a reference such as `"$globals.now"`. When it is absent, the wall clock
is used and that time-dependence MUST be stated in the design note and in the operator reference.

#### Scenario: A literal base clock

- **WHEN** the chain is `["py", "parse_time", {"now": "2026-01-01 12:00:00"}]` and the value is `tomorrow`
- **THEN** the result is `2026-01-02 12:00:00`

#### Scenario: A base clock from the chain environment

- **WHEN** the chain is `["py", "parse_time", {"now": "$globals.now"}]`, the environment carries
  `now = 2026-01-01 12:00:00` and the value is `tomorrow`
- **THEN** the result is `2026-01-02 12:00:00`

#### Scenario: A base clock that is not a canonical time

- **WHEN** the chain is `["py", "parse_time", {"now": "next tuesday"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the parameter

### Requirement: An explicit format and a language are alternatives

A `format` and a `lang` given together MUST be rejected at compile time with `UP2-E1005`, because the
explicit format wins over the language fallback and the language could therefore never have an effect.
The fix line MUST name the two alternatives.

#### Scenario: The combination is rejected

- **WHEN** the chain is `["py", "parse_time", {"format": "%Y-%m-%d", "lang": "en"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the language parameter

#### Scenario: A language alone still restricts the detection

- **WHEN** the chain is `["py", "parse_time", {"lang": "fr"}]` and the value is `24 septembre 2026`
- **THEN** the result is `2026-09-24 00:00:00`

## MODIFIED Requirements

### Requirement: An explicit format and the language fallback keep their precedence

The decision order of `py.parse_time` SHALL be: an explicit `format` (parsed with exactly that layout) →
the built-in table of machine shapes → the language fallback → `UP2-E2007`. The explicit `format` SHALL
take precedence over the built-in table and over the language fallback, the language fallback SHALL be
reachable without naming a language (see "Natural-language input is parsed without a parameter"), and
leading and trailing whitespace SHALL still be trimmed before parsing.

#### Scenario: Explicit format still wins

- **WHEN** the chain is `["py", "parse_time", {"format": "%d.%m.%Y %H:%M"}]` and the value is `24.09.2026 15:30`
- **THEN** the result is `2026-09-24 15:30:00`

#### Scenario: The table is reached before the language fallback

- **WHEN** the chain is `["py", "parse_time", ""]` and the value is `2026-09-24 15:30:00`
- **THEN** the result is `2026-09-24 15:30:00` without consulting the language engine

#### Scenario: Whitespace is still trimmed

- **WHEN** the upstream value is `  2026-09-24T15:30:00Z  `
- **THEN** the result is `2026-09-24 15:30:00`
