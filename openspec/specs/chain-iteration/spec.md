# chain-iteration Specification

## Purpose
The chain layer's iteration construct: one operator that turns a list into one dictionary per element,
so a collected node set (or any other list a stage produces) can be parsed per item without a second
fan-out mechanism, a named chain container or a template directive.

## Requirements

### Requirement: `each` turns a list into one dictionary per element

`each` SHALL be an operator with arity 2 and exactly one action, written `["each", {<field name>:
<chain>, …}]`, so the stage carries its argument in slot 2 and no action text. Its input MUST be a
list; its result MUST be a list of dictionaries holding exactly one dictionary per input element, in
input order. Each field chain SHALL be evaluated with the element as its input value.

An empty list MUST yield an empty list, not a missing value. A non-list input MUST fail with
`UP2-E2002`, naming the type that arrived. A missing input is handled by the shared stage rule: `each`
does not accept a missing value, so the chain short-circuits before the operator runs.

#### Scenario: A list of two strings

- **WHEN** the chain is `[["each", {"n": [["py","len",""]], "u": [["py","upper",""]]}]]` and the value is
  `["ab", "cd"]`
- **THEN** the result is `[{"n": 2, "u": "AB"}, {"n": 2, "u": "CD"}]`

#### Scenario: An empty list

- **WHEN** the chain is `[["each", {"n": [["py","len",""]]}]]` and the value is `[]`
- **THEN** the result is `[]`

#### Scenario: The input order is preserved

- **WHEN** the chain is `[["each", {"raw": [["py","strip",""]]}]]` and the value is `["b", "a"]`
- **THEN** the result is `[{"raw": "b"}, {"raw": "a"}]`

#### Scenario: A collected node set

- **WHEN** the chain is `[["css","nodes","li"], ["each", {"title": [["css1","text","a"]]}]]` and the
  value is a document whose list holds two `<li>` elements
- **THEN** the result is a list of two dictionaries, each holding the title of its own element

#### Scenario: An input that is not a list

- **WHEN** the chain is `[["each", {"n": [["py","len",""]]}]]` and the value is `{"a": 1}`
- **THEN** the outcome is `UP2-E2002`, naming an object as the type that arrived

### Requirement: The field map is one ordered program per element

The argument of `each` MUST be an object whose values are chains, and its fields SHALL be evaluated in
declaration order, all of them against the same element and in one scope per element, so a later field
can read what an earlier field of the same element produced. The dictionary an element yields MUST
carry exactly those field names, in that order.

#### Scenario: A later field reads an earlier field's value

- **WHEN** the chain is `[["each", {"_raw": [["py","strip",""]], "seen": [["ctx","get","locals._raw"]]}]]`
  and the value is `["  a  "]`
- **THEN** the result is `[{"seen": "a"}]`

### Requirement: A `_`-prefixed key is a per-element local and never enters the dictionary

A field name beginning with `_` SHALL be stored as a local of that element instead of becoming a key of
its dictionary: it MUST be absent from the result, and it MUST remain readable by the later fields of
the same element.

#### Scenario: A temporary that two fields consume

- **WHEN** the chain is `[["each", {"_t": [["py","strip",""]], "a": [["ctx","get","locals._t"]],
  "b": [["ctx","get","locals._t"], ["py","upper",""]]}]]` and the value is `[" x "]`
- **THEN** the result is `[{"a": "x", "b": "X"}]`, with no `_t` key

### Requirement: Every element is evaluated in its own scope

Each element SHALL be evaluated in a fresh child scope of the scope that called `each`. Reads SHALL fall
back outward **by name**: the innermost scope that holds the first segment of a path resolves the whole
path, so a name the element itself wrote is resolved in the element's own locals and nowhere else — a key
missing under such a name MUST NOT fall through to an outer scope holding the same name. A name the
element did not write falls back outward as usual (the calling scope's locals, then the chain-level
values). Writes SHALL land in the element's own scope, and the element's locals MUST NOT outlive the
element or be visible to another element.

#### Scenario: An element local shadows an outer one

- **WHEN** the chain is `[["ctx","set","locals.t"], ["each", {"seen": [["py","upper",""],
  ["ctx","set","locals.t"], ["ctx","get","locals.t"]]}]]` and the value is `["a"]`
- **THEN** the result is `[{"seen": "A"}]`, not the value the calling scope wrote

#### Scenario: An element reads a value from the calling scope

- **WHEN** the chain is `[["ctx","set","locals.base"], ["each", {"base":
  [["ctx","get","locals.base"]]}]]` and the value is `["a"]`
- **THEN** the result is `[{"base": ["a"]}]`

#### Scenario: A missing key does not fall through to a name an outer scope owns

- **WHEN** the chain is `[["each", {"_a": [["const", {"b": 1}]], "kids": [["each", {"_a":
  [["const", {"c": 2}]], "seen": [["ctx","get","locals._a.b"]]}]]}]]` and the value is `[["x"]]`
- **THEN** the result is `[{"kids": [{}]}]`: the inner element owns `_a`, so the read is a miss, never the
  outer element's `{"b": 1}`

#### Scenario: An element's local does not outlive the element

- **WHEN** the chain is `[["each", {"_t": [["py","strip",""]]}], ["ctx","get","locals._t"]]` and the
  value is `["a"]`
- **THEN** the final read resolves as a missing value — the key is absent — never as the element's
  temporary

### Requirement: A failure stays inside its element and no element is dropped

A missing value SHALL stay inside its element: a value that is missing for one element is absent from that
element alone and does not disturb the others. `each` MUST NOT drop an element silently: the result holds
one dictionary per input element even when every field of an element resolves to absent, and a failure
MUST propagate out of `each` with the code the failing stage reported.

#### Scenario: Every field is missing

- **WHEN** the chain is `[["each", {"n": [["ctx","get","locals.nope"]]}]]` and the value is `["a", "b"]`
- **THEN** the result is `[{}, {}]`, a list of two dictionaries

#### Scenario: A failing stage propagates

- **WHEN** the chain is `[["each", {"first": [["py","getitem","0"]]}]]` and the value is `["ab"]`
- **THEN** the outcome is `UP2-E2002`, the code the failing stage reported

### Requirement: The field map is validated recursively at compile time

The argument MUST be an object of field name to chain; anything else MUST be rejected at compile time
with `UP2-E1005` and a fix line showing the accepted writing. Every sub-chain MUST be compiled like a
top-level chain — so an unknown operator, an unknown action, a malformed parameter or a dangling
reference inside it is reported at compile time with a pointer that reaches that stage inside the field
map — and each sub-chain MUST respect the per-chain stage limit. A field map nested deeper than
`MAX_EACH_DEPTH` MUST fail at compile time with `UP2-E1012`.

#### Scenario: An argument that is not an object

- **WHEN** the chain is `["each", "title"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` and the fix line shows `["each", {"title": [...]}]`

#### Scenario: A malformed sub-chain

- **WHEN** the chain is `[["each", {"title": [["py","no_such_function",""]]}]]` and it is compiled
- **THEN** compilation fails with `UP2-E1003` at the pointer of that stage inside the field map

#### Scenario: A field map nested too deeply

- **WHEN** four `each` stages are nested inside one another and the chain is compiled
- **THEN** compilation fails with `UP2-E1012`

### Requirement: The input length limit is checked before evaluation

An input list longer than `MAX_EACH_ITER` MUST fail with `UP2-E2012` before any field chain runs.

#### Scenario: One element over the limit

- **WHEN** the chain is `[["each", {"n": [["py","len",""]]}]]` and the value is a list of 10 001
  elements
- **THEN** the outcome is `UP2-E2012`, and the fix line names `py.slice` as the way to truncate first

### Requirement: A story bundle declares ordered steps and a named exit

A story bundle SHALL be a JSON object carrying `steps` (a non-empty array, whose order is execution
order) and `exit` (the name of the step whose products form the run's output). It MAY carry `globals`
(a mapping of chain-level read-only constants). It SHALL NOT carry a `chains` table: a parse rule is a
step.

A step SHALL be a JSON object with `name`, an optional `type` (the product's type name), exactly one of
`parse` (an array, one field chain, or an object, a field map) and `call` (a host function name), plus
`with` only on a `call`. A field map SHALL be evaluated once, over the step's input, with `_`-prefixed
fields staying in that step's locals. A written `type` SHALL be resolved against the type registry at the
step boundary: a built-in name or a host registration is built from the product, an unregistered name is
`UP2-E1011`, and a constructor that refuses the product is `UP2-E2019`, both at that step.

#### Scenario: A bundle with one parse step

- **WHEN** the bundle is `{"steps": [{"name": "records", "parse": {"url": [["py","id",""]]},
  "type": "Record"}], "exit": "records"}` and the run's input is `{"url": "u"}`
- **THEN** the run SHALL finish with the output `[{"url": "u"}]`

#### Scenario: A step declares both parse and call

- **WHEN** a step carries `parse` and `call`
- **THEN** compilation SHALL fail with `UP2-E1005`, naming the step

#### Scenario: A bundle has no exit

- **WHEN** the bundle carries `steps` but no `exit`
- **THEN** compilation SHALL fail with `UP2-E1005`, because the exit is declared, never derived

#### Scenario: A bundle carries a chains table

- **WHEN** a bundle carries `chains` beside `steps`
- **THEN** compilation SHALL fail with `UP2-E1005`: a parse rule is a step, and the bundle has no
  second namespace for one

#### Scenario: A declared type is unknown

- **WHEN** a step declares a `type` that is neither a built-in name nor registered
- **THEN** the run SHALL fail with `UP2-E1011` at that step, because the registry is host state and the
  bundle compiles without a host

### Requirement: Step names are unique, unreserved and resolvable

Every step SHALL declare a non-empty `name` that is unique within the bundle and is not one of the
reserved reference roots (`globals` / `locals` / `fields` / `in`). Every `next` and `exit` value SHALL
name a step of the same bundle, and the check SHALL happen at compile time.

#### Scenario: Two steps share a name

- **WHEN** two steps are both named `records`
- **THEN** compilation SHALL fail with `UP2-E1009`

#### Scenario: A step is named after a reserved root

- **WHEN** a step is named `globals`
- **THEN** compilation SHALL fail with `UP2-E1009`, listing the reserved roots

#### Scenario: An exit names a step that does not exist

- **WHEN** `exit` names a step the bundle does not declare
- **THEN** compilation SHALL fail with `UP2-E1016`, listing the declared step names

### Requirement: A request step names the step that receives the responses

A step whose `type` is `Request` or `RequestBatch` SHALL declare `next`, naming the step that receives
the responses; `next` on any other step SHALL be rejected at compile time. A single task item MAY carry
its own `next`, which overrides the step-level default for that task's answer. The kernel SHALL resolve
`next` and SHALL NOT hand it to the host: the task a suspension reports SHALL NOT carry a `next` key.

#### Scenario: A request step without next

- **WHEN** a step whose `type` is `Request` declares no `next`
- **THEN** compilation SHALL fail with `UP2-E1005`, because nothing would receive the answer

#### Scenario: next on a step that produces no request

- **WHEN** a step whose `type` is `dict` declares `next`
- **THEN** compilation SHALL fail with `UP2-E1005`

#### Scenario: A task overrides the step's next

- **WHEN** a `RequestBatch` step declares `next: "page"` and one of its task items carries
  `next: "feed"`
- **THEN** that task's answer SHALL be delivered to the step named `feed` and the others' to `page`

#### Scenario: The host never sees next

- **WHEN** a batch of tasks that carry `next` is reported as an effect
- **THEN** every task SHALL be free of the `next` key

### Requirement: An answer is parsed by the step that receives it

A suspension on `Request` or `RequestBatch` SHALL resume the same run with the host's answer, unwrapped
and unconverted. The kernel SHALL run the receiving step once per answer, in task order, with that
answer as the step's input. The product of a single `Request` answer SHALL become the input of the step
after the receiving step; for a `RequestBatch` the products SHALL be collected, in task order, into a
list that becomes the input of the step after the **last** step that received an answer (so a join
never re-runs a step that already answered). A receiving step that
itself produces a `Request` / `RequestBatch` SHALL suspend the run again, and the nested answers SHALL
resume inside the same fan-out.

#### Scenario: A response is read by the step that receives it

- **WHEN** a step produces `Request` with `next: "read"` and the host sends back a response object
- **THEN** the step named `read` SHALL run with that object as its input, and its field map MAY read it
  with `["py","getattr",NAME]`

#### Scenario: A batch fans out and rejoins

- **WHEN** a `RequestBatch` step hands over two tasks whose answers both go to a step named `page`,
  and `page` produces one product per answer
- **THEN** the step after `page` SHALL receive the list of those two products, in task order

#### Scenario: A receiving step is itself a request

- **WHEN** the step that receives an answer produces `RequestBatch`
- **THEN** the run SHALL suspend again with that batch, and the answers to it SHALL resume in the same
  run

### Requirement: The run's output is the exit step's products

The run SHALL be done when execution passes the last step, and its product SHALL be the products of
the step named by `exit`, collected in order as a list. A step whose chain product is a missing value
SHALL be skipped, so the list SHALL hold the products that exist and nothing else: no `null` is invented
for a step that produced nothing. A run whose exit step never executed SHALL be done with an empty list.

#### Scenario: A per-answer exit step

- **WHEN** the exit step runs once per answer of a batch of thirty
- **THEN** the run's product SHALL be a list of thirty products, in task order

#### Scenario: An exit step that never runs

- **WHEN** execution ends without reaching the step named by `exit`
- **THEN** the run SHALL be done with an empty list

#### Scenario: An exit step that produced nothing

- **WHEN** the exit step runs but its chain product is a missing value
- **THEN** the run's product SHALL be an empty list, and that step SHALL NOT contribute a `null`

### Requirement: `$in` names the current step's own input

`in` SHALL be a reserved reference root naming the step's own input value, so `$in.url` reads the input's
`url` without writing it to `locals` first. It SHALL resolve through the same path walk as any other
root (a mapping by key, a sequence by index, a host object by `getattr`). In a standalone field chain the
chain's input SHALL be the step's input.

#### Scenario: A seed step reads its own input

- **WHEN** a step's chain is `[["py","id",""]]` and its input is the seed URL
- **THEN** the product SHALL be that URL unchanged

#### Scenario: An answer's final URL is the base of a relative link

- **WHEN** a step's field chain is `[["py","getattr","href"], ["py","urljoin","$in.url"]]`, the input is
  a response object whose `url` is `https://x/p/` and whose `href` attribute is `a.html`
- **THEN** the product SHALL be `https://x/p/a.html`

#### Scenario: A step name may not shadow the root

- **WHEN** a step is named `in`
- **THEN** compilation SHALL fail with `UP2-E1009`

### Requirement: `py.id` returns its input unchanged

The `py` operator SHALL provide an `id` action taking no arguments, whose product is the value it
received, unchanged and unconverted. It SHALL replace the `["py","str",""]` spelling for a step whose
value *is* its own input.

#### Scenario: The identity on a string

- **WHEN** the chain is `[["py","id",""]]` and the value is `https://example.com/list.html`
- **THEN** the product SHALL be that same string

#### Scenario: The identity does not convert

- **WHEN** the chain is `[["py","id",""]]` and the value is a host object
- **THEN** the product SHALL be that same object

### Requirement: The run loop suspends on an effect and resumes the same run

`start(bundle, value)` SHALL compile the bundle and run it to the first suspension or to completion.
`run.next()` SHALL return the current effect as one of `("request", request, next_step)`,
`("batch", tasks, default_next)`, `("call", name, with)` or `("done", product)`. `run.send(answer)`
SHALL resume the suspended run with the answer and return the next effect or `done`. A suspension
SHALL NOT end the run: the same run continues, so the kernel still performs no IO.

#### Scenario: A run suspends on a request and then finishes

- **WHEN** a bundle's first step produces `Request` and the host answers it
- **THEN** `run.next()` SHALL report `("request", …)` before the answer, and after `send` the run SHALL
  continue at the receiving step

#### Scenario: A call suspends and resumes with the receipt

- **WHEN** a step calls `host.store_records` with `{"table": "records"}`
- **THEN** `run.next()` SHALL report `("call", "host.store_records", {"table": "records"})`, and a
  `send(receipt)` SHALL make the receipt that step's product

#### Scenario: A finished run stays finished

- **WHEN** `run.next()` has reported `done`
- **THEN** a later `run.next()` SHALL report the same `done` result

### Requirement: The CLI accepts a story file

`up2 lint` and `up2 trial` SHALL accept a story file — a JSON object carrying `steps` — in addition to a
field-chain file. `lint` SHALL compile the story and report the step count. `trial` SHALL run the story
to its first effect: a finished run SHALL print the product, and a suspension SHALL print the effect as
a suspended run, because the CLI has no host to answer it. A story file SHALL reject `--global` and
`--product`: the story carries its own `globals` and its own step names.

#### Scenario: Linting a story

- **WHEN** `up2 lint samples/books.toscrape.com/books/site.json` runs on a valid story
- **THEN** it SHALL exit 0 and report the number of steps

#### Scenario: Trialing a story with a request

- **WHEN** `up2 trial <story> --input text=…` reaches a `Request` step
- **THEN** it SHALL exit 0 and print the suspended state with the request it would have sent

#### Scenario: A story with --product

- **WHEN** `up2 trial <story> --product n=1` is invoked
- **THEN** it SHALL fail with a usage error naming the unsupported flag

### Requirement: A story's flow is acyclic

The compiler SHALL draw the story's flow graph over its steps, from the first step, with **one edge per
step**: the step at the next array position, or — for a step whose `type` is `Request` / `RequestBatch`,
which SHALL declare `next` — the step `next` names. A step the walk enters twice SHALL be rejected at
compile time with `UP2-E1017`.

`next` SHALL remain free to name any step of the bundle, including one written earlier in the array: a
backward `next` whose target cannot reach the jumping step again SHALL compile and run. `exit` SHALL NOT
be an edge of the flow graph, and `MAX_STORY_STEPS` SHALL bound the graph, not the number of steps a run
may take.

#### Scenario: A next that closes a loop

- **WHEN** the steps are `feed` (a `Request` step whose `next` is `page`), `page`, and `again` (a
  `Request` step whose `next` is `feed`)
- **THEN** compilation SHALL fail with `UP2-E1017`, the message SHALL carry the travel path
  `feed -> page -> again -> feed`, and the JSON Pointer SHALL name the `next` of `again`

#### Scenario: A step that jumps to itself

- **WHEN** a `Request` step named `bad` declares `next: "bad"`
- **THEN** compilation SHALL fail with `UP2-E1017`

#### Scenario: A backward next into a region that cannot reach it

- **WHEN** a `RequestBatch` step written after its receivers declares `next` naming an earlier step, and
  no path leads from that receiver back to the batch step
- **THEN** the story SHALL compile, and the run SHALL deliver the batch to that receiver and finish

#### Scenario: A fan-out that falls through and jumps forward again

- **WHEN** a `Request` step's `next` names a later plain step, that step falls through to a
  `RequestBatch`, and the batch's `next` names a later step still
- **THEN** the story SHALL compile and the run SHALL finish with the last step's product

#### Scenario: A next naming a step that does not exist

- **WHEN** a `next` or an `exit` names a step the bundle does not declare
- **THEN** compilation SHALL still fail with `UP2-E1016`, not with the flow check
