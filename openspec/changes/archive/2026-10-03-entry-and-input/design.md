# Design — the entry step and the whole-chain reference

## Context

`03` §2 declares the run's **end** and leaves its **start** implicit: `exit` is required, while the run
begins at whatever step sits first in the array. Two consequences follow from that, and both are
measurable in the committed samples.

A bundle cannot say where the run starts, so the file's meaning depends on array order alone; and a step
that nothing jumps to and that is not first is **dead** with no diagnostic — the flow lint (`03` §10 L12,
`UP2-E1017`) walks the same single-edge graph but only looks for loops.

The second asymmetry is in the chain layer. `$` already has one meaning — "a reference" — and `args`
already writes a whole value as a reference (`"rows": "$in"`, `03` §4.2). But a chain cannot: a field-map
value must be an array of stages, so a step that passes its own input through needs an **identity stage**,
and the identity stage is why `py.id` exists at all (`03` §13 O5). The DSL therefore spells one concept
twice, and the extra spelling is a stage that does no work.

## Goals / Non-Goals

**Goals:**

- A bundle declares both of its endpoints, and both are checked the same way at compile time.
- A chain that is a reference is written as a reference: one spelling, no identity stage.
- The samples exercise both: `entry` in every bundle, no identity stage in any chain.

**Non-Goals:**

- No single-element stage form (`["$in"]` as an operator of its own).
- No reachability *inference*: the lint reports what the flow cannot reach, it does not reorder steps or
  rewrite the bundle.
- No `up2` command change beyond naming the entry in `lint`'s output.

## Decisions

1. **`entry` is required, not defaulted to the first step.** A default would keep the ambiguity this
   change removes, and would make "the first step" a second way to say what `entry` says — exactly the
   duplication `03` §2 avoids for `exit`. A bundle without `entry` is `UP2-E1005`, at `/entry`.
   *Alternative rejected*: `entry` optional, defaulting to `steps[0]`, which leaves a dead step
   undetectable in the one case that matters (the author believes the first step runs).

2. **The start is a step name, not an index.** Symmetric with `exit` and with `next`, and it survives
   reordering the array. `entry` is checked against the declared names and is `UP2-E1016` when it names
   nothing.

3. **Unreachability is a compile-time lint, `UP2-E1018`.** The graph already exists: `_lint_flow` builds
   one edge per step (the next array position, or a request step's `next`) and walks it for loops. The
   same walk answers "what does the flow reach from the entry", so the new rule is one traversal, not a
   second model of the flow. The walk starts from the **entry**, not from position 0, which is the whole
   point of the change. *Alternative rejected*: reporting unreachable steps as a warning and continuing —
   a dead step is an authoring error with no legal reading, and `N3` ("a bad chain fails at compile
   time") already applies to the flow.

   The code `UP2-E1018` is the next free `E10xx` number and is **not** a retired one: `E1008` was never
   allocated, `E1101`–`E1106` are the retired graph family (`02` §7.1), and no retired number is reused.

4. **A chain may be a `$` reference, and it is the *only* way to write identity.** Wherever a chain is
   expected — a field-map value, or a step's `parse` when it is an array — a string beginning with `$` is
   a **whole-chain reference**: it is compiled as one reference leaf (the same `Ref` and the same scope
   read a parameter uses), and its product is the value it names, unchanged and unconverted. A leading
   `$` therefore always means "a reference" in every position, which is `02` §3.3's one rule extended by
   one position rather than a new rule. *Alternative rejected*: a single-element stage form
   (`["$in"]`), which would make `$` mean "a reference" in parameter position and "an operator name" in
   stage position.

   Inside an `each` field map the chain's input is the **current element** (`02` §5), so `"url": "$in"`
   there is the element, exactly as the stage form receiving the element was. `$globals.<name>` /
   `$locals.<name>` / `$<step>.<field>` / `$in` all work; a literal `$`-prefixed string in a chain
   position is no longer expressible, which is why `{"$lit": …}` exists for the parameter positions and
   is not needed here (a chain position never carried a literal).

5. **Compile-time validation is shared, not duplicated.** The reference is checked by the same
   `_check_refs` path a parameter's reference takes, so "an unknown root" is `UP2-E1006`, "a `_` key
   across steps" is `UP2-E1014` and "a step references its own name" is `UP2-E1006` — the codes the
   existing cases already pin.

6. **`py.id` is deleted, not deprecated.** It exists only as the identity stage, and the reference form
   replaces it outright (`03` §13 O5 is re-settled by this change). Keeping it would leave the second
   spelling the change is about. The samples drop its two uses; the `py` function count goes 42 → 41 and
   the conformance pair count 73 → 72.

7. **The samples' seed is the site root, and `base_url` stays the urljoin base.** They are the same
   string in both samples today, and that is a coincidence of these two sites: the seed is where the run
   starts (the page whose links are the channels), while `base_url` is what a relative link is resolved
   against. A host therefore takes the seed from `argv` and defaults it to the site root, and the bundle
   keeps owning `base_url` for the chains. Passing `globals.base_url` as the seed conflated the two.

## Risks / Trade-offs

- **An existing bundle without `entry` stops compiling** → deliberate, and the fix is one key; the
  diagnostic carries the declared step names as its allowed values.
- **A `$`-prefixed string in a chain position changes meaning from "a stage array" to "a reference"** →
  it was never legal before (it was `UP2-E1004`: a chain must be an array), so no legal bundle changes
  behaviour.
- **`py.id` removal is breaking** → the replacement is shorter and is the spelling `args` already used;
  the change is recorded in the changelog as a DSL syntax change.
- **The reachability lint could refuse a bundle that runs** → it cannot: the walk uses the executor's own
  edges (`_LoopWalk`'s `flow`), so "unreachable" means the program counter can never arrive there.
- **The trace loses the identity row** → the whole-chain reference records nothing of its own. A
  reference does no work; the step's `parse` result is still the product and still visible in the run, and
  recording a synthetic stage would put a non-operator in the operator column (`06` §5.1).

## Open Questions

None. The owner settled the naming (`entry`), the spelling (`$`), the removal (`py.id`) and the samples'
seed handling; this change implements them as written.
