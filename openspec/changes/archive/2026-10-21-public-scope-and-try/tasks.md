# Tasks

## 1. The `public` scope

- [ ] 1.1 `core/refs.py`: `RESERVED_ROOTS` gains `public`; `Scope` gains a `public` mapping; the
      read path resolves `$public.*`; the JSON projection gains the partition
- [ ] 1.2 `core/refs.py`: `write_text` accepts the `public` root and still refuses the others
- [ ] 1.3 `ops/ctx.py`: the writable roots are `locals` and `public`; the readable roots gain
      `public`
- [ ] 1.4 `core/story.py`: the run's scope owns the `public` mapping; a child scope shares it
- [ ] 1.5 Tests: write-then-read across nodes; the fingerprint does not change; `globals` stays
      read-only; `ctx.dict` may collect a `public` path

## 2. The `try` directive

- [ ] 2.1 `core/compile.py`: recognise the directive stage (a one-slot stage whose slot is a policy
      name) and reject a malformed one
- [ ] 2.2 `core/compile.py`: reject two directives in a row, and a directive as the last stage
- [ ] 2.3 `core/evaluator.py`: the one-shot guard — the next stage consumes it; on failure `raise`
      stops, `skip` continues with the carried value, `break` ends the chain
- [ ] 2.4 `core/evaluator.py`: the trace records the failure of a skipped stage
- [ ] 2.5 Tests: the three policies, the disarm-on-success rule, the two compile-time rules, and the
      unguarded failure

## 3. Docs

- [ ] 3.1 `01` §4: the scope table's third row and the policy paragraph
- [ ] 3.2 `02` §5 (the stage semantics) and §6.8 (`ctx`'s writable roots)
- [ ] 3.3 `03` §8 (the scope table) and the lint table
- [ ] 3.4 `docs/operator-reference.md`, both READMEs, `CHANGELOG.md`

## 4. Gates

- [ ] 4.1 `ruff format --check`, `ruff check`, `mypy`
- [ ] 4.2 `pytest --cov=uniparser2.core --cov-fail-under=95`
- [ ] 4.3 `up2 conformance --check`
