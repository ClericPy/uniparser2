# Proposal

## Why

The current story model is a linear sequence of typed steps with step-level effects (`Request` /
`RequestBatch` / `call`) and a `next` routing key. It cannot express the flow the product is for —
"fetch a list, run one detail parse per item, and fetch inside that parse" — without turning `each`
into a fan-out of effects and giving every receiving step a routing target. The model also carries
vocabulary the user has rejected: `entry`, `collect`, `body`, `next`, `args`, and "step vs effect
step".

This change replaces that model with **nodes that are called**: a story is a map of named chains,
a chain may call another node, and a node call is the only composition primitive. The kernel stays
pure and synchronous; a host function (`fetch`) is an ordinary `udf`, not an effect. The same change
adds the two missing `py` actions (`sleep`, `filter`) and makes the documentation and README describe
one vocabulary.

## What Changes

- **BREAKING** the story JSON becomes `{"globals": {...}, "nodes": {...}}`. `entry`, `collect` and
  the `steps` array are removed. Every node is an entry point; the first node is the default for
  tools that need one.
- **BREAKING** a node is a **chain** (array) or a **field map** (object). `[]` is identity. A field
  map evaluates every field against the node's input, writes **every** field into `$locals`, and
  puts the non-`_` fields into the product.
- **BREAKING** a chain stage may call a node: `["node", "name"]`, with the current value as the
  callee's `$in`. Node-call cycles are rejected at compile time.
- **BREAKING** `["type", "Name"]` is a chain-tail stage: it validates the value against the host's
  type registry and carries the validated JSON on.
- **BREAKING** `udf` is the only host extension point and is resolved per run
  (`run(..., udfs={...})`). Its argument forms are: omitted = the upstream value as one DTO,
  a literal/reference = one argument, `"*"` = spread the upstream list, `"**"` = spread the
  upstream mapping. A udf may return a host object mid-chain; only the run exit and a `type` stage
  require JSON.
- **BREAKING** `Request`, `RequestBatch`, `start`, `StoryRun`, `go` and `feed` are removed. A story
  that fetches calls the host's `fetch` udf synchronously with **one request object**; a URL string
  becomes `{"url": …}` with `["ctx","dict",{"url":"obj"}]`.
- `py` gains `sleep` (blocking, returns the upstream value) and `filter` (keep truthy/falsy
  elements). `py` keeps its named-parameter allowlist; the `*` / `**` argument forms are the `udf`
  contract.
- `run(story, node=None, input=None, *, globals=None, udfs=None, trace=None)` is the synchronous
  facade. `globals` merges over the story's constants for that run.
- The CLI, the snapshot runner, the samples, the trace and both READMEs move to the node model.
- Version 0.7.0.

## Capabilities

### New Capabilities

- `story-nodes`: the story shape (`globals` + `nodes`), node calls, field-map locals, the `type`
  stage, the run facade and the synchronous contract.

### Modified Capabilities

- `chain-iteration`: `each` keeps its behavior, but every field now lands in `$locals`; the old
  step/effect story requirements move to `story-nodes`.
- `dsl-operators`: two new `py` actions (`sleep`, `filter`), the `node` and `type` stages, and the
  `udf` argument forms.
- `story-trace`: stage events locate a node instead of a step, and suspension events are removed.

## Impact

- `src/uniparser2/core/story.py` is rewritten around nodes and `run`; `ast`, `compile`, `evaluator`,
  `refs`, `trace` and `types` lose the whole-chain-reference and effect paths.
- `src/uniparser2/ops/`: new `node` and `type` operators, `udf` argument binding, `py.sleep` /
  `py.filter`; `each` writes every field to the element scope.
- `src/uniparser2/cli/` and `src/uniparser2/store/`: story lint/trial, the snapshot runner and the
  publish gate use `run`; a story trial takes `--node`.
- `samples/*/site.json` and `samples/*/host.py` are migrated; the hosts register `fetch` and their
  `udf`s.
- `tests/`: the story, trace, type, CLI, store and sample tests are rewritten for the node model;
  new cases cover `node`, `type`, `sleep`, `filter` and the `udf` argument forms.
- `docs/specs/002`, `docs/specs/003`, the operator reference, the generated report, and both
  READMEs.
- No new dependency. The package stays standard-library only in `core/`.
