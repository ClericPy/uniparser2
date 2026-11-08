# Spec Delta

## MODIFIED Requirements

### Requirement: The canonical time string can be rendered in another layout

`py` SHALL provide a `strftime` action whose receiver is a `datetime` and whose single parameter is the
output layout, written with a plain value (`["py", "strftime", "%Y/%m/%d"]`). The result SHALL be a
string, so the stage's product is JSON even though the value entering it is not.

A receiver that is not a `datetime` MUST fail with `UP2-E2002`. There is no canonical time string and no
implicit conversion: a chain that holds text parses it with `py.strptime` first (`time-parsing`,
"strptime parses with an explicit literal format").

#### Scenario: A slash-separated date

- **WHEN** the chain is `[["py","strptime","%d.%m.%Y"], ["py","strftime","%Y/%m/%d"]]` and the value is
  `24.09.2026`
- **THEN** the result is `2026/09/24`

#### Scenario: A layout with a literal part

- **WHEN** the chain is `["py", "strftime", "%d.%m.%Y %H:%M"]` and the value is the `datetime` for
  2026-09-24 15:30
- **THEN** the result is `24.09.2026 15:30`

#### Scenario: A value that is not a canonical time

- **WHEN** the chain is `["py", "strftime", "%Y/%m/%d"]` and the value is `24 septembre 2026`
- **THEN** the outcome is `UP2-E2002`, because a text is parsed with `py.strptime` first and the action
  consumes a `datetime` only

#### Scenario: A receiver that is not text

- **WHEN** the chain is `["py", "strftime", "%Y/%m/%d"]` and the value is `20260924`
- **THEN** the outcome is `UP2-E2002`

### Requirement: The layout is validated against a locale-free allowlist

The layout parameter MUST be validated at compile time with `UP2-E1005` against an allowlist of
directives whose rendering is independent of the process locale and of the platform: `%Y` `%y` `%m` `%d`
`%H` `%I` `%M` `%S` `%f` `%j` `%U` `%W` `%w` `%u` `%z` `%%`. `%z` SHALL render an aware value's
numeric offset and the empty string for a naive value. The rejected families MUST be reported with their
reason in the fix line:

- locale-dependent names, whose spelling the process locale decides: `%a` `%A` `%b` `%B` `%p` `%c` `%x`
  `%X`;
- the zone name `%Z`, whose spelling the platform's zone data decides;
- platform-dependent directives: `%e` `%k` `%l` `%G` `%V`;
- epoch seconds, which would have to assume a zone: `%s`;
- an unknown directive, or a stray `%`.

Output MUST NOT depend on the process locale or the platform: every accepted directive has exactly one
rendering for one input value.

#### Scenario: A name-bearing directive is rejected

- **WHEN** the chain is `["py", "strftime", "%B"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005`, and the fix line says the locale decides the name

#### Scenario: The zone name is rejected

- **WHEN** the chain is `["py", "strftime", "%Z"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005`, and the fix line says the platform's zone data decides the
  name

#### Scenario: An offset is rendered, and a naive value renders nothing

- **WHEN** the chain is `[["py","strftime","%Y-%m-%dT%H:%M:%S%z"]]` and the value is an aware `datetime`
  at `+08:00`
- **THEN** the result is `2026-09-24T15:30:00+0800`, and the same layout over a naive value answers
  `2026-09-24T15:30:00` with an empty offset

#### Scenario: An epoch directive is rejected

- **WHEN** the chain is `["py", "strftime", "%s"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005`, and the fix line says an epoch needs an assumed zone

#### Scenario: An unknown directive is rejected

- **WHEN** the chain is `["py", "strftime", "%Q"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the layout parameter

#### Scenario: The accepted layouts are stable

- **WHEN** the accepted layouts are rendered under `LC_TIME=C` and under the system locale
- **THEN** both runs produce the same text
