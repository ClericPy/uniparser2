# Spec Delta

## Purpose

Define what `py.parse_time` accepts when the chain gives no explicit `format`: beyond the zone-less
calendar shapes it already reads, it must also read the two timestamp shapes that real feeds
publish (RFC 822 dates and zone-bearing ISO 8601 timestamps), while keeping one normalised output
shape so downstream comparisons and stored values stay stable.

## ADDED Requirements

### Requirement: Zone-bearing timestamp shapes are accepted without an explicit format

When `py.parse_time` receives no `format` parameter, it SHALL accept a timestamp whose zone is
written inside the string, in these shapes:

- ISO 8601 with a `T` separator and a numeric offset (`+08:00` or `+0800`) or a `Z` suffix,
  with or without fractional seconds;
- RFC 822 / RFC 2822 (`Thu, 24 Sep 2026 15:30:00 +0800`), including the named zones `GMT` and
  `UTC` in place of the numeric offset;
- the space-separated variant of an ISO timestamp followed by a numeric offset
  (`2026-09-24 15:30:00 +0800`).

A string matching none of the accepted shapes MUST still fail with `UP2-E2007`, exactly as before.

#### Scenario: RSS 2.0 `pubDate`

- **WHEN** the upstream value is `Thu, 24 Sep 2026 15:30:00 +0800` and the chain is `["py", "parse_time", ""]`
- **THEN** the result is `2026-09-24 15:30:00`

#### Scenario: RSS 2.0 `pubDate` with a named zone

- **WHEN** the upstream value is `Thu, 24 Sep 2026 15:30:00 GMT`
- **THEN** the result is `2026-09-24 15:30:00`

#### Scenario: Atom 1.0 `updated`

- **WHEN** the upstream value is `2026-09-24T15:30:00Z`
- **THEN** the result is `2026-09-24 15:30:00`

#### Scenario: An ISO timestamp with a numeric offset and fractional seconds

- **WHEN** the upstream value is `2026-09-24T15:30:00.000+08:00`
- **THEN** the result is `2026-09-24 15:30:00`

#### Scenario: An unreadable timestamp still fails

- **WHEN** the upstream value is `not a timestamp`
- **THEN** the outcome is `UP2-E2007`

### Requirement: The offset is consumed, not applied

The result of `py.parse_time` MUST stay the normalised wall-clock string
`%Y-%m-%d %H:%M:%S`. A zone in the input MUST NOT shift the returned time: the offset is read so
that the string parses, and is then dropped. The operation MUST NOT convert to UTC and MUST NOT
return a zone-bearing value.

#### Scenario: Two zones, one wall clock

- **WHEN** `2026-09-24T15:30:00Z` and `2026-09-24T15:30:00+08:00` are parsed
- **THEN** both return `2026-09-24 15:30:00` (identical output; no UTC shift)

#### Scenario: The accepted shapes agree with the existing zone-less shape

- **WHEN** `2026-09-24T15:30:00`, `2026-09-24T15:30:00Z` and `2026-09-24T15:30:00+00:00` are parsed
- **THEN** all three return `2026-09-24 15:30:00`

### Requirement: An explicit format and the language fallback keep their precedence

The new shapes MUST NOT change how the existing parameters behave: a `format` parameter SHALL still
parse with exactly that format and take precedence over the built-in table, the language fallback
SHALL still be reachable, and leading/trailing whitespace SHALL still be trimmed before parsing.

#### Scenario: Explicit format still wins

- **WHEN** the chain is `["py", "parse_time", {"format": "%d.%m.%Y %H:%M"}]` and the value is `24.09.2026 15:30`
- **THEN** the result is `2026-09-24 15:30:00`

#### Scenario: Whitespace is still trimmed

- **WHEN** the upstream value is `  2026-09-24T15:30:00Z  `
- **THEN** the result is `2026-09-24 15:30:00`
