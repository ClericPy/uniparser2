# Design — the renamed story keys and the unified run vocabulary

## Context

`rename-and-unify` is a vocabulary change, and its content is the list of words. What it needs from a
design document is the **reason each word was wrong** and the evidence that the replacement does not
collide with something already there.

Current spellings, and what is wrong with each:

| Today | The problem |
|---|---|
| `"parse"` on a step | it names an *action* ("parse this") while its value is the step's **body** — a chain, a whole-chain reference or a field map (`03` §2.1) |
| `"with"` on a `call` step | Python's statement keyword, and the same word `03` §4.2 uses when it explains the *effect*; the thing it holds is the host function's **arguments** |
| `"exit"` | reads as "stop here"; what it declares is the step whose products are **collected** (`03` §9) |
| a task's `"next"` | the step-level `next` is a string naming a step, while a task's is a chain that computes one — one key, two shapes |
| `run.next()` / `run.send()` | `next` is the story's routing key (`03` §4.1.1) and `send` is what the *host* does with a request; neither belongs to the run object |
| `$fields` | a second name for `locals` with no user in this repository |

## Goals / Non-Goals

**Goals:**

- One word per concept, in the bundle, in the API and in the design notes.
- A task's `next` is written like the step-level one when it is a constant: `"next": "left"`.
- No behaviour change: every gate and every sample output stays what it was.

**Non-Goals:**

- No new capability, no new error code, no new operator.
- `globals` is **not** renamed and **not** made writable: it is the chain-level read-only environment
  (`03` §8) and the one name that was already right.
- No compatibility alias for the old spellings: an unknown bundle or step key is `UP2-E1005`, which is
  what a stale spelling gets.

## Decisions

1. **`body` for a step's work, `args` for a `call`'s arguments, `collect` for the collected step.** Each
   word names what the value *is* rather than what the engine does with it: a body is what the step is
   made of, args is what the host function receives, and collect names the end of the run without
   implying that the run stops there (the flow still runs off the end of the array, `03` §12.5 C3).
   *Alternative rejected*: keeping `parse` and documenting the difference — a reader has to hold "parse
   the keyword" and "parse the action" apart in the same sentence, which is exactly the cost this change
   removes.

2. **A task's `next` accepts a string as well as a chain.** The step-level `next` is a string and a task's
   was a chain, so the same key had two shapes depending on where it appeared. Accepting both unifies
   them; the chain form stays because a fan-out whose receiving step differs per item computes it from
   the item (`03` §13 O8), and the string form is preferred in the samples because it is shorter.
   *Alternative rejected*: making the task's `next` string-only, which would delete the per-task override
   that `03` §4.1.1 and the samples' `channels` step both use.

3. **`go()` / `feed()` on the run object.** `go` reads the current effect and `feed` answers it; neither
   word is already taken inside the story vocabulary (`next` is a step key, `send` describes the host).
   `go` stays idempotent, which is what makes the documented host loop work (`03` §5).
   *Alternative rejected*: `next_effect()` / `answer()`, which are longer and the second one still
   competes with "the answer" that a host fetches.

4. **`$fields` is deleted, not aliased.** Nothing in the repository wrote it, a second name for `locals`
   has no behaviour of its own, and the `ctx` surface listed it beside `locals` for writes as well — so a
   reader had to ask which of the two a rule should use. This is recorded with the other retirements
   (`03` §12.6's family) and a bundle that writes it is `UP2-E1006`, an unknown reference root.
   *Alternative rejected*: keeping it as an alias, which leaves the question open forever.

5. **The `ctx` write surface loses `fields` with it.** `_WRITABLE_PREFIXES` and `_READABLE_ROOTS` name
   `locals` alone, so `ctx.set locals._x` is the one way to write a step's scratch area and a rule that
   writes `fields.x` is `UP2-E1015` — the same code a write to `globals` already gets.

## Risks / Trade-offs

- **Every committed bundle and every test that calls the run object has to change** → mechanical, and the
  suite is the check: the renamed keys are what the compiler requires, so a missed one fails loudly.
- **A downstream bundle breaks on the old spellings** → deliberate, and the diagnostic is `UP2-E1005` with
  the unknown key named, because a silent alias would make the format's vocabulary provisional.
- **Two words changed at once (the bundle keys and the run methods)** → one change, because they are one
  vocabulary: a reader who sees `collect` in the bundle and `send` in the loop is reading two languages.
- **The trace's parameter column** → `03` §4.4 and `06` §5.1 keep the key `params`; only the bundle's
  spelling of a `call`'s arguments changes, so the trace structure is untouched.

## Open Questions

None. The owner settled each rename and the `globals` exception; this change implements them as written.
