# Design

## Context

See `proposal.md` — Why. The current kernel represents "not there" as a third outcome (`Missing`),
short-circuits on it, and lets an individual action opt in to receiving it (`accepts_missing`, used by
`py.default` only). Thirteen sites produce it: the CSS/XPath/JSON/`re` accessors, `py.first` / `py.last`
over an empty list, `py.parse_time` over empty text, and reference resolution for an absent key.

The user's ruling: the engine does not handle errors; a query that finds nothing is not an error, it is
an empty result; everything else fails and the trace carries the diagnosis.

## Goals / Non-Goals

**Goals:**

- One outcome vocabulary: a value, or a failure.
- A no-match result defined per action shape, so a chain author can predict it.
- No per-action flag, no sentinel, no special short-circuit.
- Every place that used to answer "the field/step is absent" answers with a value or a failure.

**Non-Goals:**

- A `try` construct, or any way to turn a failure into a value (the user's model has none yet).
- The story redesign (`nodes` / caller-chosen entry) and durable runs — separate work.
- Settling a no-match into `null` on export: `""` / `[]` / `None` are ordinary JSON values and pass the
  single exit unchanged.

## Decisions

### D1 — A no-match result is the empty value of the action's shape

`""` for text, `[]` for lists, `None` for element handles and JSON queries. This is the only shape that
lets "put candidates in `locals`, collect with `ctx.list`, pick with `py.or`" work: a field that found
nothing still writes its empty value into `locals`, so the later stage sees a value, not a failure.

*Alternative rejected*: a failure — then every optional field needs a construct that contains the
failure, which the model does not have, and "the page has no such field" would abort the run.

### D2 — A reference path that cannot be walked is a failure

`$locals.nope` and a missing dict key are chain bugs (a typo, or a producer that did not run), not
absences. They stay `Failed` with `UP2-E2001`.

*Alternative rejected*: return the empty value or `None` — it silences exactly the mistake the code was
introduced for (`UP2-E2001` exists because a shallower-than-declared path is a defect).

### D3 — `py.default` keeps only its empty-value behaviour

Its `MISSING` branch dies with the state; `None` and `""` remain its inputs. It stays the one-action way
to answer "this stage produced nothing usable, use the fallback", which `py.or` cannot do because a
parameter reference is resolved before the operator runs.

### D4 — A field map has no absent key

Every field of a field map yields a value (possibly `""` / `[]` / `None`) or fails the run. The
`each` element dictionary has the same rule.

### D5 — No skipped step

`_PRODUCT_UNAVAILABLE` and the "a step whose product is missing is skipped" rule are removed; a step
either contributes a product or fails the run. `collect` therefore always sees the same number of
products as the run had steps (or fails).

## Risks / Trade-offs

- **Empty and absent become indistinguishable.** A wrong selector yields `""` instead of nothing, and the
  product carries an empty field. Mitigation: the per-operator table, the samples, and the report's
  examples; a chain that needs "must not be empty" says so through its type constructor (a validator can
  reject `""`).
- **Snapshot churn.** Any case that used to report an absent key or a `Missing` outcome changes shape.
  The samples' snapshots and the `tests/report` catalogue are regenerated in the same change.
- **`py.or` and `py.default` overlap**; the notes must state the difference (upstream value vs parameter
  operands) so the two are not presented as interchangeable.
