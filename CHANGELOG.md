# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and versioning follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

> The convention during `0.x`: new capabilities bump the minor, bug fixes bump the patch;
> **backward-incompatible DSL syntax changes also bump the minor** (still alpha, no pretending to be stable).

## [Unreleased]

## [0.9.0] - 2026-11-13

### Changed

- **BREAKING — `type` constructs the declared type, and the value flows**: `["type","Article"]` now
  answers the `Article` instance instead of substituting the mapping it was built from, so a later
  stage reads it with `py.getattr` or hands it to a `udf`. The stage carries the constructor's answer
  as it is; only the run's **exit** requires JSON (`UP2-E2003`). A chain that ended with
  `["type","Article"]` and expected the payload at the exit now fails there — write the fields out
  (a field-map node) or serialize with a `udf`.
- **BREAKING — a `type` stage may appear anywhere in a chain**: the chain-tail rule (`UP2-E1005`) is
  gone. It existed only because the payload was carried instead of the instance.
- **pydantic needs no special case**: `Model(**payload)` is the constructor the stage already calls,
  so a pydantic model and a dataclass are the same category, and a `ValidationError` is `UP2-E2019`.
  No dependency is added.

### Added

- **A run may inject its own type table**: `run(story, types={...})` merges an overlay over the
  process-wide registry for that run only, the same way `udfs={...}` does. It accepts a
  `name → constructor` mapping, or a sequence of callables whose `__name__` is the name. The overlay
  reaches a `type` stage through the scope, so two runs in one process may resolve one name
  differently and the process-wide table is never mutated.
- **`UP2-E1011` reports the registered names in its message**, not only in `allowed`.
