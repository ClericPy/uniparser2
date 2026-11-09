# chain-iteration Specification

## Purpose
The chain layer's iteration construct: one operator that turns a list into one dictionary per element,
so a collected node set (or any other list a stage produces) can be parsed per item without a second
fan-out mechanism, a named chain container or a template directive.

## Requirements

### Requirement: `each` turns a list into one dictionary per element

`each` SHALL be an operator with arity 2 and exactly one action, written `["each", <parameter>]`, so the
stage carries its argument in slot 2 and no action text. The **parameter's shape selects the mode**:

- an **object** is a field map — every element produces one dictionary, in input order;
- an **array** is one chain — every element produces that chain's product, so the result is a list of
  products (`["each",[["py","strip"]]]` over `[" a ", " b "]` is `["a","b"]`).

Its input MUST be a list. In the field-map mode the result MUST be a list of dictionaries holding
exactly one dictionary per input element, in input order, and each field chain SHALL be evaluated with
the element as its input value. In the chain mode the result MUST be a list holding one product per
input element, in input order, and the chain SHALL be evaluated with the element as its input value.
Calling a registered host function per element is the chain mode with a `udf` stage
(`["each",["udf","normalize"]]`), so no dedicated call action exists.

An empty list MUST yield an empty list. A non-list input MUST fail with `UP2-E2002`, naming the type
that arrived. A parameter that is neither an object nor an array MUST be `UP2-E1005`, naming both
shapes, and an empty array MUST be `UP2-E1004`, because it is an empty chain. A stage before `each` that
cannot read its path fails the chain before the operator runs.

#### Scenario: A list of two strings

- **WHEN** the chain is `[["each", {"n": [["py","len"]], "u": [["py","upper"]]}]]` and the value is
  `["ab", "cd"]`
- **THEN** the result is `[{"n": 2, "u": "AB"}, {"n": 2, "u": "CD"}]`

#### Scenario: An empty list

- **WHEN** the chain is `[["each", {"n": [["py","len"]]}]]` and the value is `[]`
- **THEN** the result is `[]`

#### Scenario: The input order is preserved

- **WHEN** the chain is `[["each", {"raw": [["py","strip"]]}]]` and the value is `["b", "a"]`
- **THEN** the result is `[{"raw": "b"}, {"raw": "a"}]`

#### Scenario: A collected node set

- **WHEN** the chain is `[["css","nodes","li"], ["each", {"title": [["css1","text","a"]]}]]` and the
  value is a document whose list holds two `<li>` elements
- **THEN** the result is a list of two dictionaries, each holding the title of its own element

#### Scenario: A list of strings through one chain

- **WHEN** the chain is `[["each", [["py","strip"]]]]` and the value is `[" a ", " b "]`
- **THEN** the result is `["a", "b"]`, one product per element

#### Scenario: A list of dicts through one chain

- **WHEN** the chain is `[["each", [["py","getitem","url"], ["py","urljoin","$globals.base"]]]]`, the
  value is `[{"url": "a.html"}, {"url": "b.html"}]` and `globals.base` is `https://x/`
- **THEN** the result is `["https://x/a.html", "https://x/b.html"]`

#### Scenario: An empty chain

- **WHEN** the chain is `[["each", []]]` and it is compiled
- **THEN** compilation fails with `UP2-E1004`, because an empty array is an empty chain

#### Scenario: An input that is not a list

- **WHEN** the chain is `[["each", {"n": [["py","len"]]}]]` and the value is `{"a": 1}`
- **THEN** the outcome is `UP2-E2002`, naming an object as the type that arrived

### Requirement: The field map is one ordered program per element

In the field-map mode the argument of `each` MUST be an object whose values are chains, and its fields
SHALL be evaluated in declaration order, all of them against the same element and in one scope per
element, so a later field can read what an earlier field of the same element produced. The dictionary
an element yields MUST carry exactly those field names, in that order.

#### Scenario: A later field reads an earlier field's value

- **WHEN** the chain is `[["each", {"_raw": [["py","strip"]], "seen": [["ctx","get","locals._raw"]]}]]`
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
- **THEN** the final read SHALL fail with `UP2-E2001` — the key is not there — and SHALL NOT resolve
  the element's temporary

### Requirement: A failure stays inside its element and no element is dropped

`each` SHALL produce one dictionary per input element, holding the keys its field map declares. A field
whose query matched nothing SHALL carry the empty value of that action's shape (it is a value, not an
absent key). `each` MUST NOT drop an element silently, and a failure MUST propagate out of `each` with
the code the failing stage reported.

#### Scenario: Every field is missing

- **WHEN** the chain is `[["each", {"n": [["css1","text","h1"]]}]]` and the value is
  `["<p>a</p>", "<h1>b</h1>"]`
- **THEN** the result is `[{"n": ""}, {"n": "b"}]`, a list of two dictionaries

#### Scenario: A failing stage propagates

- **WHEN** the chain is `[["each", {"first": [["py","getitem","0"]]}]]` and the value is `[42]`
- **THEN** the outcome is `UP2-E2018`, the code the failing stage reported

### Requirement: The field map is validated recursively at compile time

The argument of `each` — and a step's `body` field map, which is the same object shape — MUST be an
object of field name to chain, or an array holding exactly one chain; anything else MUST be rejected at
compile time with `UP2-E1005` and a fix line showing both accepted writings. Every sub-chain MUST be
compiled like a top-level chain — so an unknown operator, an unknown action, a malformed parameter or a
dangling reference inside it is reported at compile time with a pointer that reaches that stage inside
the field map — and each sub-chain MUST respect the per-chain stage limit. A field map nested deeper
than `MAX_EACH_DEPTH` MUST fail at compile time with `UP2-E1012`.

#### Scenario: An argument that is not an object

- **WHEN** the chain is `["each", "title"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` and the fix line shows both accepted writings,
  `["each", {"title": [...]}]` and `["each", [[...]]]`

#### Scenario: A malformed sub-chain

- **WHEN** the chain is `[["each", {"title": [["py","no_such_function"]]}]]` and it is compiled
- **THEN** compilation fails with `UP2-E1003` at the pointer of that stage inside the field map

#### Scenario: A malformed chain in the array form

- **WHEN** the chain is `[["each", [["py","no_such_function"]]]]` and it is compiled
- **THEN** compilation fails with `UP2-E1003` at the pointer of that stage inside the array

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

A story bundle SHALL be a JSON object carrying `entry` (the name of the step the run starts at), `steps`
(a non-empty array, whose order is execution order) and `collect` (the name of the step whose products
form the run's output, collected as a list). It MAY carry `globals` (a mapping of chain-level read-only
constants). It SHALL NOT carry a `chains` table: a parse rule is a step.

The run SHALL start at the step `entry` names, with the value the caller handed to the run as that
step's input. `entry` SHALL name a step of the same bundle; a missing `entry` or one that does not name a
string SHALL be `UP2-E1005` at `/entry`, and one that names no declared step SHALL be `UP2-E1016`, listing
the declared step names.

A step SHALL be a JSON object with `name`, an optional `type` (the product's type name), exactly one of
`body` (an array, one chain, or a `$` reference, or an object, a field map) and `call` (a host function
name), plus `args` only on a `call`. A field map SHALL be evaluated once, over the step's input, with
`_`-prefixed fields staying in that step's locals. A written `type` SHALL be resolved against the
type registry at the step boundary: a built-in name or a host registration is built from the product, an
unregistered name is `UP2-E1011`, and a constructor that refuses the product is `UP2-E2019`, both at that
step.

An unknown bundle key and an unknown step key SHALL both be `UP2-E1005`, naming the key: the old
spellings (`parse`, `with`, `exit`) are not aliased.

#### Scenario: A bundle with one parse step

- **WHEN** the bundle is `{"entry": "records", "steps": [{"name": "records", "body": {"url": [["py","strip",""]]},
  "type": "Record"}], "collect": "records"}` and the run's input is `{"url": " u "}`
- **THEN** the run SHALL finish with the output `[{"url": "u"}]`

#### Scenario: The run starts at the entry, not at the first step

- **WHEN** the bundle's `steps` array is `[a, b]` and its `entry` is `b`
- **THEN** the run SHALL execute `b` first, with the caller's value as its input

#### Scenario: A bundle has no entry

- **WHEN** the bundle carries `steps` and `collect` but no `entry`
- **THEN** compilation SHALL fail with `UP2-E1005` at `/entry`, because the start is declared, never
  derived from the array order

#### Scenario: An entry names a step that does not exist

- **WHEN** `entry` names a step the bundle does not declare
- **THEN** compilation SHALL fail with `UP2-E1016`, listing the declared step names

#### Scenario: A step declares both a body and a call

- **WHEN** a step carries `body` and `call`
- **THEN** compilation SHALL fail with `UP2-E1005`, naming the step

#### Scenario: A bundle has no exit

- **WHEN** the bundle carries `steps` but no `collect`
- **THEN** compilation SHALL fail with `UP2-E1005`, because the collected step is declared, never derived

#### Scenario: A bundle carries a chains table

- **WHEN** a bundle carries `chains` beside `steps`
- **THEN** compilation SHALL fail with `UP2-E1005`: a parse rule is a step, and the bundle has no
  second namespace for one

#### Scenario: A step still writes the old keys

- **WHEN** a step carries `parse` or `with`, or the bundle carries `exit`
- **THEN** compilation SHALL fail with `UP2-E1005`, naming the unknown key

#### Scenario: A declared type is unknown

- **WHEN** a step declares a `type` that is neither a built-in name nor registered
- **THEN** the run SHALL fail with `UP2-E1011` at that step, because the registry is host state and the
  bundle compiles without a host

### Requirement: Step names are unique, unreserved and resolvable

Every step SHALL declare a non-empty `name` that is unique within the bundle and is not one of the
reserved reference roots (`globals` / `locals` / `in`). Every `entry`, `next` and `collect` value SHALL
name a step of the same bundle, and the check SHALL happen at compile time.

#### Scenario: Two steps share a name

- **WHEN** two steps are both named `records`
- **THEN** compilation SHALL fail with `UP2-E1009`

#### Scenario: A step is named after a reserved root

- **WHEN** a step is named `globals`
- **THEN** compilation SHALL fail with `UP2-E1009`, listing the reserved roots

#### Scenario: An exit names a step that does not exist

- **WHEN** `collect` names a step the bundle does not declare
- **THEN** compilation SHALL fail with `UP2-E1016`, listing the declared step names

### Requirement: A request step names the step that receives the responses

A step whose `type` is `Request` or `RequestBatch` SHALL declare `next`, naming the step that receives
the responses; `next` on any other step SHALL be rejected at compile time. A single task item MAY carry
its own `next` — **a string naming a step, or a chain that computes one** — which overrides the
step-level default for that task's answer. The kernel SHALL resolve
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

#### Scenario: A task computes its next with a chain

- **WHEN** a `RequestBatch` step declares `next: "left"` and one of its task items carries
  `next: [["py","getitem","parser"]]`
- **THEN** that task's answer SHALL be delivered to the step the chain produced, and the others' to `left`

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

The run SHALL be done when execution passes the last step, and its product SHALL be the products of the
step `collect` names, collected in order as a list. Every executed step SHALL either contribute its
product or fail the run: there SHALL be no "skipped step", and no `null` is invented for a step that
produced nothing. A run whose exit step never executed SHALL be done with an empty list.

#### Scenario: A per-answer exit step

- **WHEN** the exit step runs once per answer of a batch of thirty
- **THEN** the run's product SHALL be a list of thirty products, in task order

#### Scenario: An exit step that never runs

- **WHEN** execution ends without reaching the step named by `collect`
- **THEN** the run SHALL be done with an empty list

#### Scenario: An exit step that produced nothing

- **WHEN** the exit step runs and its field chains each matched nothing
- **THEN** the run's product SHALL hold that step's product (its fields carrying the empty values), and
  SHALL NOT hold a `null`

### Requirement: `$in` names the current step's own input

`in` SHALL be a reserved reference root naming the step's own input value, so `$in.url` reads the input's
`url` without writing it to `locals` first. It SHALL resolve through the same path walk as any other
root (a mapping by key, a sequence by index, a host object by `getattr`). In a standalone field chain the
chain's input SHALL be the step's input.

#### Scenario: A seed step reads its own input

- **WHEN** a step's chain is the whole-chain reference `"$in"` and its input is the seed URL
- **THEN** the product SHALL be that URL unchanged

#### Scenario: An answer's final URL is the base of a relative link

- **WHEN** a step's field chain is `[["py","getattr","href"], ["py","urljoin","$in.url"]]`, the input is
  a response object whose `url` is `https://x/p/` and whose `href` attribute is `a.html`
- **THEN** the product SHALL be `https://x/p/a.html`

#### Scenario: A step name may not shadow the root

- **WHEN** a step is named `in`
- **THEN** compilation SHALL fail with `UP2-E1009`

### Requirement: A chain may be a whole-chain reference

Wherever a chain is expected — the value of a field-map entry, or a step's `body` when it is written as
an array — a **string beginning with `$`** SHALL be accepted and SHALL mean "the value the reference
names, unchanged and unconverted". It SHALL be the same reference spelling a parameter uses (`$globals`
/ `$locals` / `$in` / a step name, with a dotted path), resolved through the same path walk and the same
scope, and it SHALL be the **only** way to express identity: no single-element stage form SHALL be added.

Inside an `each` field map the chain's **input value** is the current element, so the first stage of such a
chain consumes that element; `$in` keeps naming the **step's** input (`02` §5). The reference SHALL be
validated at compile time by the same rules a parameter's reference uses: an unknown root or a step's own
name is `UP2-E1006`, and a `_`-prefixed key of another step is `UP2-E1014`.

#### Scenario: A field-map entry that is the step's input

- **WHEN** a step's field map is `{"url": "$in"}` and its input is the string
  `https://example.com/list.html`
- **THEN** the field SHALL hold that string, unchanged, with no stage evaluated for it

#### Scenario: A step's body that is a whole-chain reference

- **WHEN** a step's `body` is the string `"$in"` and the run's input is the seed URL
- **THEN** the step's product SHALL be that URL

#### Scenario: A reference's value is not converted

- **WHEN** a chain is the reference `"$in"` and the input is a host object
- **THEN** the product SHALL be that same object

#### Scenario: A reference inside an each field map

- **WHEN** the chain is `[["each", {"whole": "$in", "elem": [["py","upper",""]]}]]`, the value is
  `["a", "b"]` and the step's input is `{"seed": "s"}`
- **THEN** the result SHALL be `[{"whole": {"seed": "s"}, "elem": "A"}, {"whole": {"seed": "s"}, "elem": "B"}]`,
  because the element is the stage's input value while `$in` still names the step's input (`02` §5)

#### Scenario: A chain that opens with a reference

- **WHEN** a chain is `["$globals.base", ["py","strip",""]]` and `globals.base` is `"  a  "`
- **THEN** the reference SHALL be read first and the stages after it evaluated in order

#### Scenario: A reference root that does not exist

- **WHEN** a chain is the string `"$nope"` and no step or reserved root carries that name
- **THEN** compilation SHALL fail with `UP2-E1006`, listing the accepted roots

#### Scenario: A step references its own name through a chain reference

- **WHEN** the field map of the step named `rows` is `{"url": "$rows.url"}`
- **THEN** compilation SHALL fail with `UP2-E1006`

### Requirement: A step unreachable from the entry is rejected

The compiler SHALL draw the story's flow graph over its steps from the step `entry` names, with one edge
per step (the step at the next array position, or the step a request step's `next` names), and every step
the walk cannot reach SHALL be rejected at compile time with `UP2-E1018`, whose diagnostic SHALL name the
unreachable step and point at it.

#### Scenario: A step nothing reaches

- **WHEN** the steps are `start` (a `Request` step whose `next` is `done`) and `done`, and a third step
  `orphan` is declared after them with nothing jumping to it
- **THEN** compilation SHALL fail with `UP2-E1018`, naming `orphan`

#### Scenario: The entry is not the first step of the array

- **WHEN** the steps are `[dead, start]` and `entry` is `start`
- **THEN** compilation SHALL fail with `UP2-E1018`, naming `dead`

#### Scenario: Every step is reachable

- **WHEN** every step is entered by the fall-through edge or by a `next` from a reachable step
- **THEN** the story SHALL compile

### Requirement: The run loop suspends on an effect and resumes the same run

`start(bundle, value)` SHALL compile the bundle and run it to the first suspension or to completion.
`run.go()` SHALL return the current effect as one of `("request", request, next_step)`,
`("batch", tasks, default_next)`, `("call", name, args)` or `("done", product)`. `run.feed(answer)`
SHALL resume the suspended run with the answer and return the next effect or `done`. A suspension
SHALL NOT end the run: the same run continues, so the kernel still performs no IO.

#### Scenario: A run suspends on a request and then finishes

- **WHEN** a bundle's first step produces `Request` and the host answers it
- **THEN** `run.go()` SHALL report `("request", …)` before the answer, and after `feed` the run SHALL
  continue at the receiving step

#### Scenario: A call suspends and resumes with the receipt

- **WHEN** a step calls `host.store_records` with `{"table": "records"}`
- **THEN** `run.go()` SHALL report `("call", "host.store_records", {"table": "records"})`, and a
  `feed(receipt)` SHALL make the receipt that step's product

#### Scenario: A finished run stays finished

- **WHEN** `run.go()` has reported `done`
- **THEN** a later `run.go()` SHALL report the same `done` result

### Requirement: The CLI accepts a story file

`up2 lint` and `up2 trial` SHALL accept a story file — a JSON object carrying `steps` — in addition to a
field-chain file. `lint` SHALL compile the story and report the step count, the step `entry` names and the
step `collect` names. `trial` SHALL run the story
to its first effect: a finished run SHALL print the product, and a suspension SHALL print the effect as
a suspended run, because the CLI has no host to answer it. A story file SHALL reject `--global` and
`--product`: the story carries its own `globals` and its own step names.

#### Scenario: Linting a story

- **WHEN** `up2 lint samples/books.toscrape.com/books/site.json` runs on a valid story
- **THEN** it SHALL exit 0 and report the number of steps, its entry and its collected step

#### Scenario: Trialing a story with a request

- **WHEN** `up2 trial <story> --input text=…` reaches a `Request` step
- **THEN** it SHALL exit 0 and print the suspended state with the request it would have sent

#### Scenario: A story with --product

- **WHEN** `up2 trial <story> --product n=1` is invoked
- **THEN** it SHALL fail with a usage error naming the unsupported flag

### Requirement: A story's flow is acyclic

The compiler SHALL draw the story's flow graph over its steps, from the step `entry` names, with **one
edge per step**: the step at the next array position, or — for a step whose `type` is `Request` /
`RequestBatch`, which SHALL declare `next` — the step `next` names. A step the walk enters twice SHALL be
rejected at compile time with `UP2-E1017`.

`next` SHALL remain free to name any step of the bundle, including one written earlier in the array: a
backward `next` whose target cannot reach the jumping step again SHALL compile and run. `collect` SHALL NOT
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

### Requirement: A run carries a `public` scope, shared by every node

A run SHALL expose a third scope, `public`, beside `globals` and `locals`: it is **writable** and
**readable from any node of the run**, and it lives exactly as long as the run. It SHALL NOT be part
of the chain data, so it never enters the fingerprint: a run's `public` values are runtime notes, not
a property of the chain.

The reference root `public` SHALL be reserved, and `$public.<path>` SHALL read it. A write through
`ctx.set` SHALL accept a `public.` path; a write to `globals`, to a step's product or to any other
root SHALL still be refused.

`globals` SHALL stay read-only and `locals` SHALL stay private to the scope that wrote it, so the
three scopes read as constants / shared / private.

#### Scenario: A node writes and the next node reads

- **WHEN** a step's field map writes `["ctx","set","public.page"]` and a later step reads
  `$public.page`
- **THEN** the later step SHALL read the written value

#### Scenario: `public` is not chain data

- **WHEN** a run writes `public.page` and the chain is fingerprinted
- **THEN** the fingerprint SHALL be the same as it was before the write

#### Scenario: A write outside the writable roots is refused

- **WHEN** a step writes `["ctx","set","globals.page"]` or `["ctx","set","in.page"]`
- **THEN** compilation SHALL fail with `UP2-E1015`, naming the writable roots

#### Scenario: `public` may be collected like any scope

- **WHEN** the chain is `[["ctx","dict",{"p":"public.page"}]]`
- **THEN** the outcome SHALL be `Ok({"p": <the value of public.page>})`

### Requirement: A `try` directive guards the next stage only

A chain MAY carry a `try` stage whose parameter is one policy: `raise`, `skip` or `break`. It SHALL
guard **the stage immediately after it** and nothing else.

- `raise` SHALL be the default behaviour of a failing stage: the chain stops and the run fails.
- `skip` SHALL keep the value the chain already carried into the failing stage and continue with the
  next stage.
- `break` SHALL end the chain at that point and answer with the value the chain carried into the
  failing stage.

A guarded stage that **succeeds** SHALL disarm the guard, so a `try` never affects a later failure.
Two `try` stages in a row SHALL be a compile error, and a `try` as the last stage of a chain SHALL be a
compile error, because it would guard nothing.

The policies are **control, not degradation**: `skip` and `break` keep a value the chain already had;
neither of them SHALL turn an exception into a value.

#### Scenario: A guarded failure is skipped

- **WHEN** the chain is `[["const", "keep"], ["try", "skip"], ["py", "int", ""]]` and the input is
  `"not-a-number"`
- **THEN** the outcome SHALL be `Ok("keep")`

#### Scenario: A guarded failure breaks the chain

- **WHEN** the chain is `[["const", "keep"], ["try", "break"], ["py", "int", ""]]` and the input is
  `"not-a-number"`
- **THEN** the outcome SHALL be `Ok("keep")`, and the stages after the guarded one SHALL NOT be
  evaluated

#### Scenario: A guarded success disarms the guard

- **WHEN** the chain is `[["const", ""], ["try", "skip"], ["py", "strip", ""], ["py", "int", ""]]` and
  the input is `"not-a-number"`
- **THEN** the chain SHALL fail at the `py.int` stage — the guard covered only the stage next to it

#### Scenario: An unguarded failure fails the run

- **WHEN** the chain is `[["const", "keep"], ["py", "int", ""]]` and the input is `"not-a-number"`
- **THEN** the run SHALL fail with `UP2-E2005`

#### Scenario: Two guards in a row are a compile error

- **WHEN** the chain is `[["try", "skip"], ["try", "skip"], ["py", "strip", ""]]`
- **THEN** compilation SHALL fail with `UP2-E1005`, naming the rule

#### Scenario: A guard at the end of a chain is a compile error

- **WHEN** the chain is `[["py", "strip", ""], ["try", "skip"]]`
- **THEN** compilation SHALL fail with `UP2-E1005`, naming the rule
