# Spec Delta

## ADDED Requirements

### Requirement: strptime parses with an explicit literal format

`py.strptime` SHALL parse the upstream text with one explicit, literal format
(`["py","strptime","%d|%m|%Y"]`) and answer a `datetime`: naive, or aware when the format contains
`%z`. The format MUST be validated at compile time against `strftime`'s locale-free allowlist, and a
bad or unknown directive MUST be `UP2-E1005`. There SHALL be no format guessing, fallback table or
implicit trimming; a text that does not match MUST be `UP2-E2005`, naming the format.

#### Scenario: A day-first date

- **WHEN** the chain is `[["py","strptime","%d|%m|%Y"]]` and the value is `24|09|2026`
- **THEN** the result is the naive `datetime` for 2026-09-24 at 00:00:00

#### Scenario: A format with an offset

- **WHEN** the chain is `[["py","strptime","%Y-%m-%dT%H:%M:%S%z"]]` and the value is
  `2026-09-24T15:30:00+0800`
- **THEN** the result is an aware `datetime` at `+08:00`

#### Scenario: A text that does not match

- **WHEN** the chain is `[["py","strptime","%d|%m|%Y"]]` and the value is `2026-09-24`
- **THEN** the outcome is `UP2-E2005`, and the message names `%d|%m|%Y`

#### Scenario: There is no guessing

- **WHEN** the chain is `[["py","strptime","%d|%m|%Y"]]` and the value is
  `Thu, 24 Sep 2026 15:30:00 +0800`
- **THEN** the outcome is `UP2-E2005`, because a shape the format does not describe is never inferred

#### Scenario: A rejected directive is a compile error

- **WHEN** the chain is `["py","strptime","%B %d, %Y"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the format parameter, because the locale decides the
  month name

### Requirement: An epoch converts to and from a datetime

`py.from_timestamp` and `py.to_timestamp` SHALL convert between epoch seconds and a `datetime` at a
fixed offset, with no timezone database or DST. `from_timestamp` SHALL answer an aware `datetime` at
`tz` hours (optional, default `0` = UTC; a half-hour zone writes `5.5`). `to_timestamp` SHALL use an
aware value's own offset and interpret a naive value at `tz`; an aware value with a non-zero `tz` MUST
be `UP2-E2002`, and a `tz` that is not a number MUST be `UP2-E1005`.

#### Scenario: Epoch seconds become an aware datetime

- **WHEN** the chain is `[["py","from_timestamp",0]]` and the value is `0`
- **THEN** the result is an aware `datetime` at `+00:00` holding 1970-01-01 00:00:00

#### Scenario: A half-hour zone

- **WHEN** the chain is `[["py","from_timestamp",5.5]]` and the value is `0`
- **THEN** the result is an aware `datetime` at `+05:30` holding 1970-01-01 05:30:00

#### Scenario: The zone defaults to UTC

- **WHEN** the chain is `[["py","from_timestamp"]]` and the value is `0`
- **THEN** the result is an aware `datetime` at `+00:00`

#### Scenario: An aware value uses its own offset

- **WHEN** the chain is `[["py","to_timestamp"]]` and the value is an aware `datetime` at `+08:00`
  holding 1970-01-01 08:00:00
- **THEN** the result is `0`

#### Scenario: A naive value is read at UTC

- **WHEN** the chain is `[["py","to_timestamp"]]` and the value is the naive `datetime`
  1970-01-01 00:00:00
- **THEN** the result is `0`, regardless of the machine's local zone

#### Scenario: A second zone on an aware value

- **WHEN** the chain is `[["py","to_timestamp",2]]` and the value is an aware `datetime`
- **THEN** the outcome is `UP2-E2002`, because the value already carries an offset

#### Scenario: A zone that is not a number

- **WHEN** the chain is `["py","from_timestamp","+02:00"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the zone parameter

#### Scenario: A receiver that is not a datetime

- **WHEN** the chain is `["py","to_timestamp"]` and the value is the text `"0"`
- **THEN** the outcome is `UP2-E2002`

## REMOVED Requirements

### Requirement: Zone-bearing timestamp shapes are accepted without an explicit format

**Reason**: `py.parse_time` is deleted (D14): an action that guesses a timestamp's shape is what made
the result depend on a built-in table, and `strptime` with an explicit format covers the machine shapes
without guessing.

**Migration**: write the shape as a format — `["py","strptime","%Y-%m-%dT%H:%M:%S%z"]`, with `.%f`
added for fractional seconds, and the space-separated variant as `"%Y-%m-%d %H:%M:%S %z"`. A shape the
locale-free allowlist cannot express (RFC 822 with month names, or a named zone) is parsed by a host
`udf` or by `code`.

### Requirement: The offset is consumed, not applied

**Reason**: `py.parse_time` is deleted (D14), so there is no normalised wall-clock string for an
offset to be dropped from.

**Migration**: `strptime` keeps the offset on the value when the format contains `%z`, and `strftime`
with a layout that omits `%z` renders the wall clock. Use `py.to_timestamp` to compare instants.

### Requirement: An explicit format and the language fallback keep their precedence

**Reason**: `py.parse_time` is deleted (D14), and with it the built-in table and the language fallback
the precedence was decided between.

**Migration**: `strptime` takes the explicit format as its only parameter; there is no second source of
truth and therefore no precedence.

### Requirement: Natural-language input is parsed without a parameter

**Reason**: `py.parse_time` is deleted (D14), and the `time` extra / `dateparser` dependency and the
`UP2-E2008` code go with it. Natural-language dates are out of scope, because detecting a language makes
a chain's result depend on an optional engine.

**Migration**: parse such text in a host `udf` or in `code`; a deterministic chain should carry the
format it expects.

### Requirement: The ambiguous numeric order is an explicit parameter

**Reason**: `py.parse_time` is deleted (D14), so the `date_order` parameter and the default it carried
no longer exist.

**Migration**: the order is written into the format — `["py","strptime","%d/%m/%Y"]` for day first and
`"%m/%d/%Y"` for month first.

### Requirement: Relative expressions have a pinnable base clock

**Reason**: `py.parse_time` is deleted (D14), and the clock dependency that made a relative expression
non-deterministic disappears with it. Relative dates are out of scope.

**Migration**: resolve a relative expression in a host `udf` or in `code`, where the base clock is the
host's explicit choice; keep the absolute result in the chain.

### Requirement: An explicit format and a language are alternatives

**Reason**: `py.parse_time` is deleted (D14), and the `lang` parameter has no counterpart on
`strptime`.

**Migration**: write the format only; a text that a single format cannot describe is out of scope for
`strptime`.
