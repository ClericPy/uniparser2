# A story's flow may not loop

## Why

`next` lets a step hand its answers to another step, and that step may be written **earlier** in the
array — so a story can express a loop, and nothing rejects one. `03` §13 O9 records it as open: the run
ends when the program counter passes the last step, so a loop runs until the host interrupts it. The
committed samples use backward `next` edges (a fan-out whose answers are parsed by a step written
earlier), so the lint has to separate "jumps backwards" from "can come back to a step it is executing".

## What Changes

- **The story compiler checks the flow is acyclic** (`UP2-E1017`, new code), drawn over the edges the
  executor actually walks: **one per step**, the next array position, or — for a request step, whose
  `next` is required — the step `next` names. A step the walk enters twice is refused at compile time,
  with the travel path in the message and the JSON Pointer on the backward `next`.
- **`next` stays free to name any step.** A backward `next` whose region cannot reach the jumping step
  again is legal and runs; both committed samples and the test suite's fan-out shapes keep compiling.
- **The stronger reading is rejected**: drawing a step's fall-through edge and its receiver edges at the
  same time refuses `samples/books.toscrape.com`, where `channels` fans out to `shelf_page`, which falls
  through to `shelf`, whose own `next` is `book` — every one of those steps runs exactly once.
- Docs: `03` §10 gains the `L12` row, §10/§13 O9 are settled, a new deviation record `12.5` (`D-03-5`)
  states the rule, the rejected reading and the proof that the rule equals "no backward jump that
  loops"; `02` §7.1 gains the `UP2-E1017` row; `01` §4.4's cycle row stops saying a cycle cannot be
  expressed.

**Out of scope**: the runtime, `MAX_STORY_STEPS`, the operator layer, the Store, the trial UI and
pagination. Nothing in `core/story.py`'s run loop changes.

## Capabilities

### New Capabilities

None. The rule polices the story format and its executor, which the capability that owns the chain
layer's structure already covers; a second one would split one format across two specs.

### Modified Capabilities

- `chain-iteration`: a story's flow SHALL be acyclic — a requirement about the compile-time validation of
  the step graph `next` and the implicit fall-through draw. The existing requirements about `next`,
  `exit` and the run loop are unchanged.

## Impact

- Kernel: `core/story.py` (the compile-time flow check, `_lint_flow` / `_cycle`); `core/errors.py`
  (`UP2-E1017`).
- Docs: `03` §10, §12.5, §13 O9; `02` §7; `01` §4.4; `CHANGELOG.md`.
- Tests: the cycle cases in `tests/chains/test_story.py`, and four runtime-code cases there whose
  deliberately self-referential `next` would now be a compile-time loop (they gain a receiver step so
  they still reach the run-time path they assert).
