# Design — the skipped step and the callable attribute

## Context

See `proposal.md` — Why. Both rules live in code that already applies them elsewhere: `01` §4.2 fixes
the outcome of a missing value (absent in a field map, skipped in a batch) and `pyops._py_getattr`
already refuses a callable attribute with the message and fix hint this change reuses.

Two facts shape the first decision. The run loop is a generator whose `_step_product` returns
`(program counter, value)`; the value it returns is the input of the next step. And the exit list is
appended to at the moment the exit step runs, so "skip" has to mean *both* "record no product" and
"append nothing".

## Goals / Non-Goals

**Goals:**

- One rule for a missing value everywhere: it is not a value, so nothing is carried, recorded or
  collected for it.
- The two refusals (`py.getattr` and a dotted reference) read as one rule: the same code, the same
  message shape, the same one-line fix.

**Non-Goals:**

- No change to what `Missing` means for a *stage* (it still short-circuits a chain and stays missing).
- No new error code: the reference refusal reuses `UP2-E2002`.
- No cycle detection, no trace, no policy — the other `03` §13 items that stay open (O6, O9).

## Decisions

1. **A missing step product is a distinct return, not a `null` value.** `_step_product` answers
   `(pc + 1, <no value>, produced=False)`, and the caller ignores the value; the product dictionary is
   not written and the exit appends nothing. A sentinel value would have to be filtered at every use
   site — a third state in a function that already carries two — whereas "produced" is exactly what the
   caller decides on. *Alternative rejected*: keeping the `None` and filtering it out of the exit list,
   which would leave the `null` visible to every later step and to the run's value.
2. **A skipped receiving step advances past the step that follows it.** The single-request path already
   knows the receiver's index, so "the step after the receiver" is `pc + 1` from the receiver's own run;
   a fan-out joins on the maximum of its receivers' continuations, which is the rule the per-task `next`
   already forced. *Alternative rejected*: ending the run on a missing answer, which would make an
   ordinary "this page had no title" abort a whole fan-out.
3. **A step that produces nothing is indistinguishable from a step the run never reached** — both leave
   no product and no output entry. That is deliberate: `01` §4.2's rule is about what a missing value
   *is*, and "the step did not produce" is the honest description of both.
4. **The reference refusal reuses `py.getattr`'s code, message shape and fix hint.** One rule with two
   entry points is easier to learn than two rules; `UP2-E2002` already means "the value is not what the
   operation expects" and this is that case. *Alternative rejected*: `UP2-E2001` (the path cannot be
   read), which would read as "the path is wrong" while the path is right and the attribute is a method.
5. **The refusal sits in `_walk_attribute`, the single place a dotted path touches a host object**, so
   `$globals.x`, `$in.x` and `$<step>.x` all obey it — the root decides the base, never the rule.

## Risks / Trade-offs

- **A run can now finish with fewer products than steps that ran** → the exit collects what exists, which
  is what a missing value means everywhere else; a step that must contribute is enforced by its
  registered type constructor, which reports the missing key at that step.
- **A caller that relied on `None` for a missing receiving step** → the run continues instead; the
  alternative (a `null` product that a `Request` step cannot use) was never usable.
- **Refusing `$resp.json` removes a shortcut an author might have wanted** → the fix line names what to
  use instead (`["css","text",""]`, or a `udf` that calls the method), and the value could not have left
  the run anyway.

## Open Questions

None. Both questions this change closes are settled above; the other `03` §13 items (O6, O9) are out of
scope and unchanged.
