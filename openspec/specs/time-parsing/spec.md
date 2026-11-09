# time-parsing Specification

## Purpose

Define what `py.parse_time` accepts and how it decides: the zone-less calendar shapes and the two
timestamp shapes that real feeds publish (RFC 822 dates and zone-bearing ISO 8601 timestamps), the
natural-language path that the optional engine provides **without a parameter**, the two knobs that
make an ambiguous numeric date and the base clock of a relative expression explicit, and the one
normalised output shape that keeps downstream comparisons and stored values stable.

## Requirements

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
