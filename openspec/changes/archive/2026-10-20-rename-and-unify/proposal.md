# Rename the story's keys and unify the run's vocabulary

## Why

Seven names in the story format and its run loop say the wrong thing, and one of them is a duplicate.
`with` is Python's statement keyword, not the word for a host function's arguments; `parse` names a
*step's* parse action while the thing it holds is a **body** (a chain or a field map); `exit` reads as
"stop" when it means "these are the products that are collected"; a task item's `next` is a chain while
the step-level `next` is a string, so one key has two shapes; `run.next()` / `run.send()` collide with
`next`'s and the story's own vocabulary; and `$fields` is a second name for `locals` that nothing uses.
Reusing a word for two meanings is how a format becomes unreadable.

## What Changes

- **`$fields` is deleted** (`core/refs.py`, its docs and its tests): it was a second name for `locals` and
  no bundle in this repository ever wrote it. `$locals` is the one spelling; the removal is recorded with
  the other retirements. **BREAKING** for a bundle that wrote `$fields`.
- **`with` → `args`** on a `call` step. **BREAKING**.
- **`parse` → `body`** (a step's body: a chain, a whole-chain reference, or a field map). **BREAKING**.
- **`exit` → `collect`**: it names the step whose products are collected. **BREAKING**.
- **A task item's `next` may be a string as well as a chain**, unifying it with the step-level `next`;
  the samples prefer the plain string. **BREAKING** only in that the chain form is no longer the only one.
- **The run object's methods `next()` / `send()` become `go()` / `feed()`**: `next` is the story's own
  routing key and `send` names something a host does with a request, so neither word belonged to the run.
- **`globals` keeps its name and its read-only meaning** — it is not renamed and not made writable.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chain-iteration`: the bundle's collected-products key, a step's body and a `call`'s arguments are
  renamed; a task's `next` accepts a string; the run loop's two methods are renamed.
- `core-evaluator`: the `$fields` reference root is gone, so `$locals` is the one name for the current
  scope.
- `dsl-operators`: the operator catalogue reflects the renamed spellings.

## Impact

- Kernel: `core/story.py` (`args` / `body` / `collect`, the task's string `next`, `run.go()` /
  `run.feed()`); `core/refs.py` (the `$fields` root deleted from the reserved roots, the aliases and the
  `ctx` surface); `ops/ctx.py` (`_WRITABLE_PREFIXES` / `_READABLE_ROOTS` lose `fields`); `cli/main.py`
  (the story report and the trial note).
- Samples: both `samples/*/site.json` and both `samples/*/host.py`.
- Docs: `03`, `002`, `004` §7/§9, `006`'s mock, `007`'s rows, `docs/operator-reference.md`, both READMEs,
  the regenerated `docs/report/up2-report.md`, and a `CHANGELOG.md` `[Unreleased]` entry.
- Tests: every story bundle and every `run.next()` / `run.send()` call in the suite.
