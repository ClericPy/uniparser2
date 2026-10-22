# Spec Delta

## MODIFIED Requirements

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

#### Scenario: A step declares both parse and call

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

The run SHALL be done when execution passes the last step, and its product SHALL be the products of
the step named by `collect`, collected in order as a list. A step whose chain product is a missing value
SHALL be skipped, so the list SHALL hold the products that exist and nothing else: no `null` is invented
for a step that produced nothing. A run whose collected step never executed SHALL be done with an empty
list.

#### Scenario: A per-answer exit step

- **WHEN** the step named by `collect` runs once per answer of a batch of thirty
- **THEN** the run's product SHALL be a list of thirty products, in task order

#### Scenario: An exit step that never runs

- **WHEN** execution ends without reaching the step named by `collect`
- **THEN** the run SHALL be done with an empty list

#### Scenario: An exit step that produced nothing

- **WHEN** the step named by `collect` runs but its chain product is a missing value
- **THEN** the run's product SHALL be an empty list, and that step SHALL NOT contribute a `null`

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
