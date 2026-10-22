# Tasks

## 1. `$fields` is deleted

- [ ] 1.1 `core/refs.py`: drop `fields` from the reserved roots, the writable roots and the local
  aliases; a `locals` read is the only alias left
- [ ] 1.2 `ops/ctx.py`: `_WRITABLE_PREFIXES` and `_READABLE_ROOTS` name `locals` (and `globals` for reads)
- [ ] 1.3 `core/compile.py`: the `UP2-E1014` and `UP2-E1006` fix lines point at `$locals.*`
- [ ] 1.4 Record the removal where the other retirements are recorded (`03` §12.6, `002` §3.1)
- [ ] 1.5 Tests: a `$fields` read is `UP2-E1006`; a `ctx` write to `fields.*` is `UP2-E1015`

## 2. The bundle's keys

- [ ] 2.1 `core/story.py`: `parse` → `body`, `with` → `args`, `exit` → `collect` (keys, the compiled
  fields, the docstrings and every message)
- [ ] 2.2 `cli/main.py`: the story report and the trial note use the new names
- [ ] 2.3 Tests and both samples: every bundle writes the new keys

## 3. A task's `next` may be a string

- [ ] 3.1 `core/story.py`: a task item's `next` is a string naming a step or a chain computing one; the
  receiver lookup accepts both and an unknown target is still `UP2-E1016`
- [ ] 3.2 Both samples prefer the plain string in their fan-out items
- [ ] 3.3 Tests: a string `next`, a chain `next`, and an unknown target for each

## 4. The run object's methods

- [ ] 4.1 `core/story.py`: `run.next()` → `run.go()`, `run.send()` → `run.feed()`
- [ ] 4.2 Both `samples/*/host.py` and every test call the new names
- [ ] 4.3 `06`'s mock and `03` §5 keep the effect tuple's shape (`("call", name, args)`)

## 5. Docs

- [ ] 5.1 `03`: §2/§2.1 (the bundle, the step, the body), §4.1.1 (a task's `next`), §4.2 (`args`),
  §5 (`go` / `feed`), §7 (`$fields` out, `$locals` the scope), §8 (the scope table), §9 (`collect`),
  §10 (the lint table), §11 (the walkthrough and the measurements), §12, §13
- [ ] 5.2 `002` §3.1/§3.3 (§`fields` out, `$locals` the one scope), §5, §6.8 (`ctx`)
- [ ] 5.3 `004` §7's SOP examples and §9's counter-examples, `006`'s mock, `007`'s rows,
  `docs/operator-reference.md`, both READMEs, the regenerated `docs/report/up2-report.md`
- [ ] 5.4 `CHANGELOG.md`: one `[Unreleased]` entry

## 6. Gates

- [ ] 6.1 `ruff format --check` / `ruff check` / `mypy` / `pytest --cov=uniparser2.core
  --cov-fail-under=95` / `up2 conformance --check`
- [ ] 6.2 Both samples re-run live through their committed host scripts
- [ ] 6.3 The `change-linter` for every edited `.py`
- [ ] 6.4 `openspec validate --strict` and archive with the `openspec-archive-change` skill
