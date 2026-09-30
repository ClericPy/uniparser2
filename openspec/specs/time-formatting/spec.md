# time-formatting Specification

## Purpose
The output side of time handling: rendering the canonical time string (`%Y-%m-%d %H:%M:%S`, the shape
every time-producing operator returns) in another layout, so a chain can emit `2026/09/24` or
`2026-W39-4` without hand-assembling it from `slice` / `replace`.

## Requirements

### Requirement: The canonical time string can be rendered in another layout

`py` SHALL provide a `strftime` action whose receiver is the canonical time string and whose single
parameter is the output layout, written with a plain value (`["py", "strftime", "%Y/%m/%d"]`). The
result SHALL be a string, so the JSON value domain is unchanged and no datetime object enters the chain.

A receiver that is not a string MUST fail with `UP2-E2002`; a receiver that is a string but not the
canonical shape MUST fail with `UP2-E2007` and the fix line MUST name `py.parse_time` as the way to
produce one.

#### Scenario: A slash-separated date

- **WHEN** the chain is `[["py", "parse_time", ""], ["py", "strftime", "%Y/%m/%d"]]` and the value is
  `2026-09-24 15:30:00`
- **THEN** the result is `2026/09/24`

#### Scenario: A layout with a literal part

- **WHEN** the chain is `["py", "strftime", "%d.%m.%Y %H:%M"]` and the value is `2026-09-24 15:30:00`
- **THEN** the result is `24.09.2026 15:30`

#### Scenario: A value that is not a canonical time

- **WHEN** the chain is `["py", "strftime", "%Y/%m/%d"]` and the value is `24 septembre 2026`
- **THEN** the outcome is `UP2-E2007`, and the fix line names `py.parse_time`

#### Scenario: A receiver that is not text

- **WHEN** the chain is `["py", "strftime", "%Y/%m/%d"]` and the value is `20260924`
- **THEN** the outcome is `UP2-E2002`

### Requirement: The layout is validated against a locale-free allowlist

The layout parameter MUST be validated at compile time with `UP2-E1005` against an allowlist of
directives whose rendering is independent of the process locale and of the platform: `%Y` `%y` `%m` `%d`
`%H` `%I` `%M` `%S` `%f` `%j` `%U` `%W` `%w` `%u` `%%`. The rejected families MUST be reported with their
reason in the fix line:

- locale-dependent names: `%a` `%A` `%b` `%B` `%p` `%c` `%x` `%X`;
- zone-bearing directives, which are empty on a zone-less value: `%z` `%Z`;
- platform-dependent directives: `%e` `%k` `%l` `%G` `%V`;
- epoch seconds, which would have to assume a zone: `%s`;
- an unknown directive, or a stray `%`.

#### Scenario: A name-bearing directive is rejected

- **WHEN** the chain is `["py", "strftime", "%B"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005`, and the fix line says the locale decides the name

#### Scenario: An epoch directive is rejected

- **WHEN** the chain is `["py", "strftime", "%s"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005`, and the fix line says an epoch needs an assumed zone

#### Scenario: An unknown directive is rejected

- **WHEN** the chain is `["py", "strftime", "%Q"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the layout parameter

#### Scenario: The accepted layouts are stable

- **WHEN** the accepted layouts are rendered under `LC_TIME=C` and under the system locale
- **THEN** both runs produce the same text
