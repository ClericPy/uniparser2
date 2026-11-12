# Contributing

This file exists so that GitHub surfaces a contribution guide. The project keeps each rule in one
place, so nothing here is authoritative — start from these instead:

| What you need | Where it is |
|---|---|
| Environment, gates, test layering, the conformance audit, post-edit checks, release | [`docs/specs/005-engineering-workflow.md`](docs/specs/005-engineering-workflow.md) — §4 tests, §5 the OpenSpec process, §6 post-edit checks, §7 release |
| Definition of done, kernel invariants, error-code rules, the change process | [`AGENTS.md`](AGENTS.md) |
| What a chain may contain (triples and operators) | [`docs/specs/002-dsl-spec-triples-and-operators.md`](docs/specs/002-dsl-spec-triples-and-operators.md) |
| Chain structure and assembly | [`docs/specs/003-parse-chain-spec.md`](docs/specs/003-parse-chain-spec.md) |

Start here:

```bash
uv sync           # create .venv and install the dev dependencies
uv run pytest     # the test suite (sandbox cases skip unless you add `--extra code`)
uv run pytest -n 4  # the same suite in parallel (pytest-xdist); CI stays serial
```

Read note `005` before your first change. If a note and the code disagree, reconcile them in the same
change — a stale note is worse than none.
