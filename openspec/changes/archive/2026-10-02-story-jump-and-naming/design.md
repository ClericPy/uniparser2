# Design — story jumps and the naming that makes them readable

## Context

`03` §2 describes a site bundle as `globals` + `chains` + `steps`, with the exit derived as "the last
step's `out`" (§2, §9). That model assumes strictly linear execution: every step's input is the step
before it, and there is exactly one last step. Both sample bundles (`samples/books.toscrape.com`,
`samples/quotes.toscrape.com`) carried a `chains` table and per-task `chain` values, so the parsing of
an answer happened where the *host* looked a chain up — the kernel never saw which rule applied.

This change keeps the model's intent (one site, one bundle, linear execution, effects as the only
suspension) and closes the three gaps that stop a bundle from being runnable: an unambiguous exit, one
namespace for parse rules, and a name for a step's own input.

## Goals / Non-Goals

- Goal: a bundle whose steps name each other (`next`, `exit`) and whose parse rules are steps.
- Goal: a kernel-side executor that suspends on `Request` / `RequestBatch` / `call` and resumes **the
  same run** with the answer.
- Non-goal: the materialization cache (`03` §6), the Store, the trial UI and pagination.
- Non-goal: the registered-type constructor of `03` §3.2 / L8 — a `type` is checked as a declared
  name, and the value it describes stays JSON.

## Decisions

1. **`key` → `name`, `out` → `type`.** A step's first key is the name other steps refer to (in
   `next`, `exit` and a reference path), and its product key is a type name. The old spellings read
   as generic JSON words and hid that.
2. **The `chains` table is deleted; a parse rule is a step.** A named chain and a step's `parse` were
   the same object — a field chain over one input — and having both meant two namespaces, two
   reference scopes and one lookup in the host. A response is now parsed by the **step that receives
   it**. *Alternative rejected*: keeping `chains` and letting `next` point at a chain entry — the
   bundle would keep two ways to say "this parses that", and only one of them could be tested by
   `up2 lint`.
3. **`next` is kernel-resolved and never reaches the host.** A step whose `type` is `Request` /
   `RequestBatch` **must** name the step that receives the responses; a task item may carry its own
   `next` to override it. The kernel strips `next` from the task before handing the effect over, so
   the request the host sends is exactly an HTTP request and the routing decision stays in the data
   the story was compiled from. *Alternative rejected*: the host mapping `next` to a chain — that is
   the hand-off the model already rejected (`03` R14) and it puts a story concern in host code.
4. **`exit` is required and names one step.** The run's output is that step's products, collected **in
   order as a list** — a step that receives a batch of answers runs once per answer, so "the exit
   step's products" is honestly plural. *Alternative rejected*: keeping "the last step" — with `next`
   a jump can revisit a step, so the last step is not unique.
5. **`$in` names this step's own input.** It is a reserved root (`globals` / `locals` / `fields` /
   `in`) and it resolves through the same path walk as any other root, so `$in.url` reads a response's
   final URL and a dotted path still works on a dictionary. In a standalone field chain (`up2 trial`
   on a chain file) the chain's input is the step's input, so `$in` works there too. A step name may
   not be `in` (L3).
6. **`py.id` is the identity action.** `["py","str",""]` was the workaround: it is the identity on a
   string and it *converts* anything else, which silently changes a seed value's type. The new action
   takes no arguments and copies nothing.
7. **The run loop is one state machine over a program counter**, and it hands out effects in the shape
   `03` §5 prescribes:

   ```text
   start(bundle, value) -> run                  # compile, then run to the first suspension
   run.next()  -> ("request", request, next_step)
                | ("batch", tasks, default_next)
                | ("call", name, with)
                | ("done", product)
   run.send(answer) -> the next effect / done
   ```

   `start` compiles and drives to the first effect; `next()` reads the effect that is current (it is
   idempotent, which is what lets the documented `while True: effect = run.next(); run.send(...)`
   loop work); `send(answer)` resumes with the answer and drives to the next effect.
8. **Resuming with answers runs the receiving step once per answer, then continues after it.** For a
   `Request` there is one answer: the receiving step runs with it and its product becomes the input of
   the step after it. For a `RequestBatch` the kernel pairs each task with its answer, runs each
   task's receiving step (`next` override, else the step default) in task order, collects the products
   into a list, and continues at the step after the **last** receiving step with that list as its
   input — with a per-task override the receiving steps differ, so "after the default" could re-run a
   step that already answered. A receiving step may itself produce a `Request` / `RequestBatch`: the interpreter is a
   generator chain (`yield from`), so that nested suspension reaches the host and resumes inside the
   same fan-out. *Alternative rejected*: delivering the whole answer list to the receiving step at
   once — it would push the per-response iteration back into every step's field map and duplicate
   `each`.
9. **Two new compile-time codes.** `UP2-E1009` (a step name is reserved or duplicated — the code `02`
   §7 already reserves for it) and `UP2-E1016` (a `next` / `exit` target is not a step name). The
   retired numbers are not reused: `UP2-E1008` is retired (`02` §7's note) and `UP2-E1101`–`E1106` are
   retired with the v0.1 node model (`03` §12.1). A step's `type` missing or not a string is
   `UP2-E1005`; `L8`'s "is it a registered type" check waits for the type registry.
10. **`up2 lint` / `up2 trial` branch on shape.** A loaded JSON object with a `steps` key is a story;
    anything else is a field chain. Story lint compiles the bundle; story trial runs to the first
    effect and prints it (`"state": "suspended"`, with the effect), because there is no host in the
    CLI to answer a request. `--global` / `--product` are refused for a story: it carries its own
    `globals` and its own step names.

## Risks / Trade-offs

- **A story can now jump backwards**, so a cycle is possible (`next` may point at any step). Execution
  terminates when the program counter passes the last step; a cycle is an authoring error the lint
  does not yet detect. Recorded as an open question.
- **The step-graph is data, so `next` typos must fail at compile time.** That is what `UP2-E1016` is
  for; a wrong name is refused before a run starts.
- **A `call`'s `with` is resolved as `ref_or_literal` leaves** (a `$`-prefixed string is a reference),
  which matches the parameter slot convention; `03` §13's O2 stays open about whether a host
  registration may bind them instead.
- **A dotted path may still resolve a callable** (`$resp.json` on an object that has a `json` method),
  where `py.getattr` refuses one. It cannot leave the run (`pack`, `UP2-E2003`), and closing it is a
  one-line change to `refs._walk_attribute`; it is recorded as an open question rather than decided
  here.

## Open Questions

- Whether a cycle among steps should be a compile-time error (reachability/termination was rejected
  with the v0.1 graph, but a jump reopens a weaker version of it).
- Whether `refs` should refuse a callable attribute exactly as `py.getattr` does.
- Where a step's `type` is validated against a registry (`L8`) once `register_type` exists.
- Whether `next` should be optional for a `Request` step, defaulting to the following step in array
  order (today it is required, so the routing is never implicit).
