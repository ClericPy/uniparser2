# Design — a story's flow may not loop

## Context

`next` names the step that receives a `Request` / `RequestBatch` step's answers, and it may name a step
written earlier in the array (`03` §2.1, §4.1.1). The run is a program counter: a step that is not a
request falls through to the next array position, and a request step continues at its receiver. Nothing
checks that the two together can terminate, and the committed samples use backward `next` edges: in
`samples/books.toscrape.com`, `shelf.next` names `book`, which is written later, while `shelf_page` (the
receiver of `channels`) falls through to `shelf`. A lint that simply rejects "a `next` that points
backwards" would refuse the format's own central shape.

## Goals / Non-Goals

- Goal: a story whose flow cannot re-enter a step it is executing, rejected at compile time with the
  travel path.
- Goal: the samples, the test suite's fan-out shapes and any backward `next` that cannot loop keep
  working — `next` targets any step.
- Non-goal: bounding how many times a step may run, or how many steps a run may take. A forward jump
  makes a step run more than once, and `MAX_STORY_STEPS` (64) bounds the graph, not the behaviour.
- Non-goal: the runtime. The check is compile-time only (`N3`), so `core/story.py`'s run loop is
  untouched.

## Decisions

1. **The graph is the flow the executor walks: one edge per step.** For a step whose `type` is a JSON
   name (or absent), the edge is the step at the next array position. For a step whose `type` is
   `Request` / `RequestBatch` — where `next` is required, so there is no fall-through to draw — the edge
   is the step `next` names. A depth-first walk from the first step that enters a step it is already
   standing on fails the story. The check runs inside `compile_story`, after the step names, `next` and
   `exit` have been resolved, so a dangling target is still `UP2-E1016` and never reaches it.
2. **The union reading is rejected** — a graph that draws a step's fall-through edge *and* its receiver
   edges at the same time. It refuses `samples/books.toscrape.com`: the union cycle is
   `channels → shelf_page → shelf → channels`, yet each of those steps runs exactly once, because the
   batch's receiver is invoked rather than followed. The samples are the acceptance case for the format,
   so the union graph would declare the central shape illegal. Recorded as `D-03-5` (`03` §12.5).
3. **A backward `next` is legal, and the rule catches loops rather than backward edges.** The two are
   equivalent, and the reason is a proof, not an observation: in a cycle, take the step whose array
   position is greatest; it cannot be entered by a fall-through (that edge strictly increases the
   position), so it must be entered by a jump — therefore **every cycle contains a forward jump**, and a
   backward jump is always a link of some cycle. The DFS above reports a loop exactly when some step is
   entered twice, which is exactly when the run can come back to a step it is executing. So the
   committed samples (a backward jump whose region ends forward, beyond it) compile, while `a → … → a`
   and any self-jumping step fail.
4. **`exit` is not an edge.** A run ends when the program counter passes the last step, whatever `exit`
   names (a step that never ran contributes nothing); modelling the exit as a graph node would make the
   lint depend on a fact the executor does not use, and `exit` is already checked to name a step
   (`UP2-E1016`).
5. **The code is the new `UP2-E1017`.** The existing numbers cannot carry it: `UP2-E1005` is the generic
   "parameter schema validation failed", whose message and fix are about one parameter, and
   `UP2-E1016` is specifically "the target is not a step of the story" — a name that does not resolve,
   which is a different defect with a different fix (renaming a target does not break a loop). The
   number was free: the compile-time table (`02` §7) runs `UP2-E1001`–`UP2-E1016` with `UP2-E1008`
   retired, so `E1017` is the first number after the last taken one, and the retired graph numbers
   `UP2-E1101`–`E1106` / `UP2-E1108` are not reused (`02` §7.1, `03` §12.1).

## Risks / Trade-offs

- **A cyclic story the author *wanted*** is now refused at compile time. A run bounded by the host (a
  retry loop with an external stop) cannot be expressed at all. Accepted: §5's loop has no iteration
  counter and no stop condition, so such a story terminates only by host interruption, and the samples
  show that the useful shapes do not need a cycle that re-enters a running step.
- **The check is not a termination proof in the general case**, and is not claimed as one: it refuses a
  graph loop, and a run whose steps simply produce a lot of work is the resource limits' business
  (`UP2-E1012`). The forward jump is the honest example — legal, and the step after it runs more than
  once.
- **Four runtime-code cases in `tests/chains/test_story.py` used a self-referential `next`** (`bad` →
  `bad`) as a convenient way to make a step sit in a one-step story. They are now compile errors, so
  each gained a plain receiver step (`sink`) and still reaches the run-time path it asserts; the change
  removes no coverage and bends no assertion.

## Open Questions

None. `03` §13 O9 is settled by this change; the deviation record is `D-03-5` (`03` §12.5).
