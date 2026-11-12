# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and versioning follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

> The convention during `0.x`: new capabilities bump the minor, bug fixes bump the patch;
> **backward-incompatible DSL syntax changes also bump the minor** (still alpha, no pretending to be stable).

## [Unreleased]

### Changed

- **BREAKING — one stage shape, one parameter rule** (change `simplify-dsl-syntax`): a stage is
  `[operator]`, `[operator, parameter]` or `[operator, action, parameter]`, and a parameter slot is
  **omitted** when nothing required remains (`["py","strip"]`, `["json"]`) instead of carrying an
  empty-string placeholder. Two or more fixed parameters are **one positional array**
  (`["py","replace",["old","new"]]`, `["re","search",["(\\d+)",1]]`,
  `["xpath","text",["//x",{"dc":"…"}]]`); a named object is a data map only. The `const` operator is
  gone — a literal is `["py","const",value]` — and `$obj` names the value a stage received, usable in
  any parameter (`["py","or",["$locals.a","$obj"]]`).
- **BREAKING — the `py` table is trimmed and Python-shaped**: removed `list`, `strip_tags`,
  `default`, `parse_time`, `split.maxsplit` and `sort`'s key/reverse object; added `const`, `md5`,
  `between`, `find_jsons`, `strptime`, `from_timestamp`, `to_timestamp` and `sort_desc`. `bool` is
  Python's `bool` (`"false"` is true), `strip` takes an optional `chars`, `uniq` is O(n), and
  `or`/`and` include the upstream value as the first operand.
- **BREAKING — time is Python's pair on real datetimes**: `parse_time` and the `[time]` extra are
  deleted (with `UP2-E2007` / `UP2-E2008`); `strptime` parses text with an explicit literal format
  into a `datetime`, `strftime` renders one, and `from_timestamp` / `to_timestamp` convert epoch
  seconds at a fixed offset. A `datetime` may flow between stages but is not exportable — the exit
  names `py.strftime`.
- **BREAKING — operator surfaces**: `re` drops `group` (`search` takes `[pattern, group]`), encodes
  `findall`'s tuples as arrays, and gains `sub` (`[pattern, replacement]`); `each`'s array parameter
  is one chain over every element; `ctx` gains the read-only `obj` root; `code` is `["code", src]`
  with `obj`/`ctx` built-ins, silenced `print` and an `UP2_CODE=off` gate; `udf` is
  `["udf","f"]` unary or nullary with compile-time signature checks and no `ctx` injection.
- `param_form` tokens are `value` / `array` / `none`, and a JSON Pointer inside a positional
  parameter array is `/0/2/<index>`.

### Added

- **The snapshot runner answers a story's requests from the request cache** (change
  `cached-snapshot-runs`; `04` §7-S4/S5): `up2 snapshot` and `up2 test` replay the cached answers, so
  a chain that fetches can be frozen and regressed **offline**. A request with no cached answer is a
  **miss** — the runner reports it and stops, because the CLI never reaches the network. A `call`
  still needs a host, and the runner says so.
- **The request's body is base64 text** (change `cached-snapshot-runs`; `03` §4.1): a body is binary
  and the request dictionary is JSON throughout — it lives in chain data, in a cache key and in a
  journal — so `body` carries base64 and the downloader decodes it before sending. A `json` key
  carries a JSON value instead, and the two are alternatives.
- **A third scope, `public`** (change `public-scope-and-try`; `01` §4, `03` §8): the run's own
  notes — writable from any node (`ctx.set public.x`) and readable from any node (`$public.x`),
  shared across the nodes of one run and outliving an `each` element. The three scopes read as
  **constants / shared / private**: `globals` is the chain's read-only constants (fingerprinted),
  `public` is runtime state (never fingerprinted), `locals` is one field's scratch space. `globals`
  stays read-only: writing it would break "same chain, same result".
- **A `try` directive** (change `public-scope-and-try`; `02` §5): `["try","skip"]` /
  `["try","break"]` / `["try","raise"]` guard **the stage immediately after them**. `skip` keeps the
  value the chain carried into that stage and carries on, `break` ends the chain with it, and `raise`
  is the default. A guarded stage that **succeeds** disarms the guard, so a `try` never swallows a
  later failure; two in a row, or one at the end of a chain, are compile errors (`UP2-E1005`). The
  directive is **not** an operator — the operators stay pure — and it never turns an exception into a
  value.
- **A default downloader and a request cache** (change `default-host-downloader`): the new
  `uniparser2.net` package fetches the request dictionary the kernel hands over and answers with a
  response carrying `text` and `url` — the shape the sample hosts read with `py.getattr`. It is
  **synchronous and standard-library only** (the runtime dependencies stay empty), and the cached
  answers live under `.cache/requests/` — never committed — keyed by the whole request, so a second
  run replays them instead of the network.

### Fixed

- **Whole-project review fixes**: a `["type", …]` stage no longer turns a value rejection into an
  operator defect (`["type","int"]` on `"abc"` is `UP2-E2019`, not `UP2-E2099`), and a dataclass
  constructor built from a list or a scalar continues with the payload instead of `{}`; `ctx.get` /
  `set` / `del` / `dict` / `list` validate the whole path at compile time (an empty segment, an exact
  root, and a key below the root), so no path raises mid-run; `xpath text` wraps a scalar expression
  (`string(...)`, `count(...)`) as one list item and an invalid namespace map is `UP2-E1005`; a
  non-finite `tz`, `py.int(inf)` and `py.from_json("NaN")` are coded failures, and `py.from_json`,
  the `json` operator and `Response.json()` read strictly; the documented `MAX_TEXT_BYTES` (16 MiB)
  limit is now enforced as `UP2-E2013` at the evaluator entry. Smaller fixes: a product whose value
  is `None` is readable, a `try` directive with a third slot is `UP2-E1004`, an `each` field map
  with a `$`-prefixed key is read as a field map, a request's query goes before its fragment, an
  unknown response charset falls back to UTF-8, a corrupt cache entry is a miss, and
  `up2 doctor --fix` reports the same `at` it stores. `demo.py` is rewritten against the current
  syntax and a test runs it; CI is now **test-only** (the conformance audit, the committed-sample
  compile check and the catalogue freshness live in the suite), its matrix includes 3.15, and the
  GitHub release workflow is gone — publishing is a local `uv publish`. The report's case run and
  the test-tree scan are cached, so the suite no longer repeats that work; the workflow's `--extra`
  names are checked against `pyproject.toml` by a test, and `pytest-xdist` is available in the dev
  group for `-n 4` local runs (CI stays serial).
- **`json`'s root expression works with the real engine** (change `simplify-dsl-syntax`): `02` §6.2
  says an empty expression is the root, and `["json",""]` / `["json",null]` were tested — but only
  against the stub engine, which answered `""` by itself. Real `jmespath` raises
  `EmptyExpressionError` for it, so the documented spelling failed at compile time with
  `UP2-E1005`. The operator now maps an empty expression to jmespath's `@`, and a real-engine test
  covers it.
- **Every text boundary reads and writes strict JSON** (change `reject-non-json-text`): the store and
  the sample runner still called `json.dumps` / `json.loads` bare, so a graph carrying `Infinity`
  published successfully and landed in the chain file, a snapshot containing `Infinity` was read as
  `inf`, and malformed chain text raised `JSONDecodeError` instead of `UP2-E1004`. `core.values` now
  owns one strict pair (`dumps_json` / `loads_json`), and the fingerprint, every stored row and every
  snapshot go through it: an illegal graph is refused **before** anything is written, and a corrupt
  file is reported with its path. `up2.loads` answers `UP2-E1004` for malformed text as it already
  did for a non-JSON constant. **Behaviour change**: JSON that Python accepts (`Infinity`) but JSON
  does not is now an error on these paths too.
- **A non-finite float is no longer a JSON value** (change `reject-non-finite-floats`): `inf` / `-inf`
  / `nan` passed `is_json_value`, so they survived the single exit and reached the serializers —
  `up2 trial --json` printed `{"state": "ok", "value": Infinity}`, which **no strict JSON parser
  accepts**, and `dumps` wrote `[["py","const",Infinity]]`. The predicate now requires a finite float, so a
  product carrying one (nested included) fails with `UP2-E2003` at the step that produced it, and
  chain text obeys the same rule: `loads` rejects the constants Python's decoder permits and `dumps`
  refuses to write them, both with `UP2-E1004`. The computation is untouched — `py.float("1e999")`
  still answers `inf` mid-chain; only the boundary refuses it. **Behaviour change**: a chain whose
  product was non-finite used to emit invalid JSON and now fails with a diagnostic.
- **`py`'s scalar parameters are validated at compile time, not at the first run** (change
  `literal-scalar-type-checks`): the check rejected a JSON *container* where a scalar belonged but
  let a literal of another type through, so `["py","urljoin",42]`, `["py","slice","bogus"]`,
  `["py","split",{"sep":",","maxsplit":"x"}]`, `["py","split",{"sep":42}]`,
  `["py","replace",[42,"x"]]` and `["py","getattr",42]` all passed `up2 lint` and failed during
  evaluation — `urljoin`'s with an **empty fix line**. The scalar table now carries the accepted
  types, and the two strings the runtime parses (`slice.spec`, `split.maxsplit`) are parsed with the
  runtime's own parser, so the compiler cannot fall behind it. `maxsplit` keeps its numeric strings
  and its `null` / `""` "no limit" spellings, and parameters that only coerce (`join.sep`,
  `parse_time.lang`, `default.value`) are untouched. **Behaviour narrowing**: a wrong-typed literal
  now fails at lint with `UP2-E1005`, the parameter's pointer and a fix line; no chain that produced
  a value changes meaning.
- **`{"$lit": …}` escapes at every depth, and the diagnostics name it** (change
  `literal-escape-at-depth`): the escape was recognised only at the top of a parameter slot, so a
  literal starting with `$` had no legal spelling inside an array or an object — and one failure was
  silent, because `["py","or",[{"$lit":"plain"},"b"]]` answered with the dict `{'$lit': 'plain'}`
  instead of the string. A `$`-prefixed single-key object is now a directive wherever a
  `ref_or_literal` value is read (`$lit`, or `UP2-E1005` naming the escape), a `literal` parameter
  still keeps `$` as text, and three messages say how to write the text instead: an unknown
  reference root (`UP2-E1006`) names `{"$lit": …}`, and a `$`-prefixed `ctx` path (`UP2-E1005` /
  `UP2-E1015`) says to drop the `$`. **Behaviour narrowing**: an object whose only key starts with
  `$` was passed through as data at depth and is now the escape or an error, matching what the slot
  level already did.
- **The report's input is whole, matched and scoped** (change `report-case-context`): an input was
  elided at 180 characters exactly like an output, which cut a selector's own target out of the css
  sample (the text stopped inside `<h1 cl…`), and the "sample above" link landed on a collapsed
  block. A card now shows what its selector **matched** (`1 node · h1.article-title`; `1 node ·
  script` says plainly that no `<style>` exists in the sample), the **scope** a `ctx` / `code` /
  `udf` case reads — its real input, never rendered before — and, for `const` and the reading `ctx`
  actions, that the input is **not used**, instead of presenting a document as one. The Markdown
  catalogue no longer labels the first case's value "Shared input for this section" for sections
  whose inputs differ (`py` advertised `'  text  '` to 42 actions), and the section sample is open
  by default.
- **The request cache no longer answers one page with another page's answer**: the cache key is now a
  digest of the **normalized** request — the query parameters folded into the URL, the body decoded to
  its bytes, the whole thing written as JSON with sorted keys — so `?page=1` and `?page=2` are two
  entries instead of one, and the same request written in another order is still one entry.
- **The operator report shows what a stage really did**: the steps come from the run's **trace**
  instead of from re-evaluating prefixes, so a failure a `try` guard caught is shown as the failure it
  was, and the directive itself is shown as the directive it is.
- **`uniparser2.core` no longer exports the deleted `Missing`**: the name was still in `__all__`, so
  `from uniparser2.core import *` raised `AttributeError`.
- **The `ctx` diagnostic names every readable root**: the fix line of an unreadable root said
  "globals / locals" while the accepted list said three roots, `public` among them.
- **The `dsl-operators` specification names the third scope**: the `ctx` requirement still described
  `locals` as the only writable root, which contradicted the implementation.
- **The README, the demo and the serialization cases speak the current dialect**: the README's
  example matched on the deleted `up2.Missing`, the demo ran a chain with the retired `ctx.map`
  action (and skipped it), and the fixed-point test case used `ctx.map` as well.

### Changed

- **BREAKING — an outcome is a value or a failure** (`01` §4, `02` §5; change `empty-value-semantics`):
  the third state (`Missing`), the `MISSING` sentinel and `accepts_missing` are gone. A query that
  matches nothing answers the **empty value of its shape** — `""` for text, `[]` for a list, `None` for
  a node handle or a JSON query — and the chain keeps going; a path that cannot be walked is
  `UP2-E2001`. A field map has no absent key and a step no longer "produces nothing": every executed
  step contributes a product or fails the run. `py.default` now replaces `None` / `""` only, and the
  trace records `Ok` / `Failed`.
- **BREAKING — the story's keys are `body` / `args` / `collect`** (change `rename-and-unify`):
  `parse` → `body`, `with` → `args`, `exit` → `collect`, and a task item's `next` may be a plain
  string. The run object's methods are `go()` / `feed()`. `$fields` is deleted (`$locals` is the one
  spelling of the current scope).
- **BREAKING — `ctx.map` is split into `ctx.dict` and `ctx.list`**, and `py` gains `items`
  (change `ctx-dict-list-and-py-table`): the action name now states the result shape, and
  `py.items` (`dict → [[key, value], …]`) is the zero-dependency way to iterate an object. The
  conversion actions' `fix` text no longer recommends a fallback operator.

### Added

- **A story declares where it starts, and a dead step is a compile error** (`03` §2, §10 L13, §12.6):
  `entry` is a required top-level key naming the step the run starts at, symmetric with `collect` — a bundle
  without it is `UP2-E1005` at `/entry`, and one that names no declared step is `UP2-E1016`, listing the
  steps. `up2 lint` prints the entry beside the exit. The flow the cycle lint already walks is now asked
  the second question it can answer: every step **unreachable from the entry** is the new `UP2-E1018` at
  compile time, with the step's name and a pointer at it, so a step nobody jumps to and the fall-through
  never passes is no longer silently dead. The entry may name **any** step — including one written later —
  and the lint then reports the ones the flow cannot arrive at. Conformance: 72 declared pairs, 37
  implemented error codes, each with a case.
- **A chain may be a reference, and that is the only identity** (`03` §2, §12.6): wherever a chain is
  expected — a field-map value, or a step's `body` — a **string beginning with `$`** means "the value the
  reference names, unchanged": `"url": "$in"` is the step's own input, `"$in.url"` is a field of it, and a
  chain may open with one (`["$globals.base", ["py","strip"]]`). It is the same spelling `args` already
  uses for an argument, and it is the **only** way to express identity: no single-element stage form was
  added. `py.id` is **deleted** with its two uses in the samples — `py` now holds 41 functions and the
  registry 72 pairs (from 42 and 73) — and a chain that opened with the identity stage simply drops it,
  because a chain's first stage already receives the input. Both sample bundles lost their identity stages
  and gained `entry`, and both host recipes take the seed URL from the command line (the site root by
  default) instead of passing `globals.base_url`, which is the urljoin base of the chains rather than the
  URL a run starts at.

- **A story's flow is now acyclic, checked at compile time** (`03` §10 L12, §12.5; closes `03` §13 O9):
  `next` stays free to name any step, including one written *earlier* — the samples' own fan-out shape
  does that — but a run may not come back to a step it is already executing, and the new `UP2-E1017`
  refuses it at compile time, carrying the travel path (`the flow of this story closes a loop: feed ->
  page -> again -> feed`) and a pointer at the backward `next`. The lint is drawn over the flow the
  executor actually walks: **one edge per step**, the next array position or the step a request step's
  `next` names. The stronger "union reachability" reading (a step's fall-through edge and its receiver
  edges at the same time) was rejected because it refuses `samples/books.toscrape.com`: `channels` fans
  out to `shelf_page`, which falls through to `shelf`, whose own `next` is `book` — every one of those
  steps runs exactly once, yet the union graph calls the format's central shape a cycle. `MAX_STORY_STEPS`
  (64) bounds that graph, not the number of steps a run may take: a forward jump remains legal.

- **The trace, and `up2 trial --trace`** (`06` §5.1, `03` §4.4): a run can now be read stage by stage.
  `Trace` collects one event per **evaluated stage** (a stage a failure stopped the chain before records
  nothing) plus one per **suspension**, each carrying `seq`, `step`, `item`, `field`, `stage`, `op`,
  `action`, `params`, `input`, `output`, `state`, `detail` and `ms`. `params` are the **compiled** named
  parameters, so a default the author never wrote — or an `each`'s compiled field map — is visible;
  `input` / `output` are `type` / `preview` (200 characters) / `size` views whose whole value is fetched
  on demand by `get_value(seq)`; and `item` is the fan-out index, which is the `each` element's position
  or the position of the answer a `RequestBatch`'s receiving step is running — what makes "the third
  result's title is missing" locatable. A suspension is an event too (`"effect": "request" | "batch" |
  "call"`, carrying what the kernel handed the host, with a `call`'s function name in `action`), so a UI
  can show "it suspended here, and this is what it handed out". `up2 trial --trace [--json]` reports the
  events in evaluation order, and a run that asks for no trace behaves exactly as before: `start(bundle,
  value, trace=…)` and `eval_field(…, trace=…)` are the only two injection points, no clock is read
  without one, and `core/` stays stdlib-only, IO-free and synchronous. `003` §13 O6 is settled with it:
  **the trace is a debugging aid, not the replay format** — it is lossy by construction and holds no
  answer, while what replays a run is the host's own log of the suspensions it answered. Conformance is
  untouched: 73 declared pairs, 35 implemented error codes, each with a case.

- **A run-scoped materialization cache, so one document is parsed once** (`03` §6): `css` / `css1`,
  `xpath` and `json` no longer each build their own tree, so twenty fields over one page cost one
  parse instead of twenty (measured on a 5 MB page: 1976.7 ms → 48.6 ms). The cache is **not an
  optimization but correctness-of-performance** — `007` §3's "500 items × 20 fields within 3 s" is
  unreachable without it — so it is bounded and asserted: `MAX_MATERIALIZE_BYTES` (64 MiB, accounted
  in materialized bytes) and `MAX_MATERIALIZE_ITEMS` (8 artifacts), both with LRU eviction, one
  over-cap artifact retained while it is in use ("one document, one parse" always holds). It belongs
  to the run's evaluation scope, is inherited by nested field-map / `each` scopes, and is released
  with the run: nothing is shared across runs, and a cached tree is never mutated in place.

- **A step's `type` is now built, not just declared**: `register_type(name, constructor)` (with
  `unregister_type` / `type_names` / `get_type`) lands, and the kernel builds the declared type from
  the product **at the step boundary**, where the author can see which key is wrong. An unregistered
  name is `UP2-E1011` at that step, listing the registered names; a constructor that refuses the
  product is the new `UP2-E2019`, carrying the constructor's own exception text. The constructor is a
  **validator, not a container** — the product continues as JSON, so the single exit still holds —
  and the JSON basics (`null` / `bool` / `str` / `int` / `float` / `list` / `dict`) and the effect
  types (`Request` / `RequestBatch`) are registered for free, with a host registration winning over a
  built-in name.

- **The first story executor, and the naming that makes a story readable** (`03` §2, §5): a bundle is
  a linear sequence of typed steps, driven by `start(bundle, value)` → `run.next()` / `run.send(answer)`.
  A `Request` / `RequestBatch` step **suspends** the run and the answer resumes the same run, so the
  kernel still performs no IO. A step's keys are `name` and `type` (they were `key` / `out`); the
  `chains` table is gone, because a parse rule is a step; a request step declares **`next`**, the step
  that receives the answers (a single task may override it, and the kernel strips it before the host
  sees the request); and a top-level **`collect`** names the step whose products are the run's output.
  `$in` names this step's own input, so `["py","id",""]` replaces the `["py","str"]` workaround.
  `up2 lint` and `up2 trial` accept a story file and report a suspension as such.

- **A host object is a value**: a value that flows through a chain may be an object — an HTTP
  response, a `udf` result, a DOM handle — because the kernel already carried third-party objects.
  **Step products must still be JSON** (`export.pack` still rejects anything else, and the
  host-registered type constructor converts at the step boundary), so the single exit is unchanged.
  `Response` stops being a type: the answer to a request is whatever the host `send`s back, unwrapped,
  and it is read with the new **`py.getattr`** action (an absent attribute fails with the exception
  class in `reason`; a **callable** attribute fails with a pointer at the operator or `udf` to use
  instead, so a method never turns into a value silently). Dotted references now walk objects with
  `getattr` and containers with `getitem`, so `$in.request.url` and `$resp.headers` work.

- **The template store (`04` §1–§6), the first slice of L3**: a chain is bound to a business identity
  (`root_domain` / `tpl_key`), which appears nowhere in L1/L2. One row per chain (`Template`:
  `chain_id` from one pure `new_chain_id()`, the tri-state `status`, the three-value `source`, the
  `graph` as data, `create_time` / `update_time`; **no `dsl_version`**), an append-only `template_audit`
  that keeps **fingerprints only**, and a `blake2s(digest_size=16)` fingerprint over the canonicalised
  graph alone — so `status` / `source` / the timestamps cannot enter it, and re-publishing the same
  graph writes **no** row at all. The new `store/` layer is the only layer that touches disk: the
  `TemplateStore` protocol (four methods, exactly as `04` §4) with two implementations — `FileStore`
  (one file per chain, atomic `os.replace`, `audit.jsonl`) and `SqliteStore` (the two tables of
  `04` §4.2, WAL, one `BEGIN IMMEDIATE` transaction per publish) — over one shared publish algorithm
  (validate → compile → read and recompile → no-op → write → audit → commit → verify the read-back).
  `UP2-E3001`–`UP2-E3005` land with it. `up2 publish` runs the `04` §6 gates: G1 lint is mandatory, G2
  (`--skip-tests` needs `--note`, which the audit row records) is refused with `UP2-E3005`, and a `ready`
  row needs `--confirm-overwrite`; `up2 get` prints the row with its fingerprint (`--graph` prints the
  chain data, the backup material) and **recompiles** what it read, because a stored graph is data and
  is never trusted (`01` §8). The regression the gate runs, and the repair command, are in the entry
  below. Conformance: 73 declared pairs, 35 implemented error codes, each with a case.

- **The publish gate is real, and the SOP around it runs** (`04` §6, §7): `up2 snapshot` freezes one
  case's product as `expected.json` — and `--accept` is the **only** way to write one, so "it ran
  once" cannot record a wrong product as the right one — while `up2 test <domain> <tpl_key>` runs the
  frozen chain over every case under `samples/<domain>/<tpl_key>/<case>/` and prints each mismatch as
  a **JSON Pointer difference** (`/0/title expect "a" got "b"`), never a text diff. `publish` now
  regresses that same set **before it writes**, so a red snapshot refuses the write with `UP2-E3005`
  unless `--skip-tests --note` says why; a case that carries an input but no snapshot is red, and a
  key with no case at all is green. `up2 doctor` reports the `UP2-E3003` inconsistencies, and
  `up2 doctor --fix` writes the audit row a chain is missing (the row records actor `doctor` and a
  note, because an audit row has nowhere else to say it was synthesized). `samples/local/demo/` is
  the committed example of the layout, and `04` §7 was corrected wherever it named a command that
  does not exist.

- **Predicate actions on `py`, spelled the way Python spells them**: `==` / `!=` / `<` / `<=` / `>` /
  `>=` / `in` answer with a boolean in one stage, and `or` / `and` follow Python's **value** semantics
  (`or` answers with the first truthy operand, else the last, `and` with the first falsy, else the
  last), so `[["py","or",["$locals._a","fallback"]]]` is the "take A, else B" shape. The four orderings
  take a comparable pair only (`UP2-E2002` names both types, instead of letting a Python `TypeError`
  escape as `UP2-E2099`), `in` keeps Python's operand order (the parameter is the container:
  `["py","in",[200,301,302]]`), and `!=` against a boolean is the negation — there is deliberately no
  `not` action. `css` / `css1` gained `exists`, which answers `true` / `false` and **never** `Missing`:
  `nodes` reports a missing value when nothing matches, so its answer is decided by the missing-value
  policy, which no predicate can rely on. `py` now holds 41 functions; the conformance audit reports 72
  declared pairs and 26 error codes.

- **`each`, the iteration operator** (`["each", {"title": [["css1","text","a"]]}]`): the stage above
  produces a list, the argument is a **field map** (`field name → chain`, the same shape a node's
  `fields` block has) and the result is **one dictionary per element**, in input order. It is a 2-slot
  operator with a single action, so the field map is its only slot. A field name starting with `_` is a
  **temporary of that element** (readable by later fields, never a key of the dictionary), every
  element is evaluated in **its own scope** (reads fall back outward **by name**, writes stay in the
  element), the
  effective policy is applied per element, and no element is ever dropped silently. An empty list
  yields `[]`, a non-list input is `UP2-E2002`, a list longer than `MAX_EACH_ITER` (10 000) is
  `UP2-E2012` before anything runs, and a field map nested deeper than `MAX_EACH_DEPTH` (3) is
  `UP2-E1012` at compile time.
- A **structured parameter kind** (`fields`): a parameter whose value is a field map has every
  sub-chain compiled recursively, so a mistake inside it is reported at compile time with a pointer that
  reaches the offending stage (`/0/1/fields/title/0/0`), and each sub-chain answers to the per-chain
  stage limit. `Scope` gained a parent link for the per-element scope, and the call context a
  sub-chain runner, so a structural operator never imports the evaluator and a sub-chain runs under the
  policy in force.
- `py.parse_time` reaches the natural-language engine **without a parameter**: the decision order is now
  an explicit `format` → the built-in table (which still loads nothing) → automatic language detection →
  `UP2-E2007`, so a chain no longer has to name a language to read one. The engine stays an optional
  extra: without `uniparser2[time]` that path reports `UP2-E2008` and names it, instead of returning a
  different value. `lang` keeps its meaning and now only restricts the detection. Two optional
  parameters arrive with it: `date_order` (`MDY` / `DMY` / `YMD`) and `now` (a `ref_or_literal`, e.g.
  `"$globals.now"`) which pins the base clock of a relative expression (`yesterday`, `3 days ago`) that
  otherwise follows the wall clock.
- `py.strftime` renders the canonical time string in another layout
  (`[["py","parse_time",""],["py","strftime","%Y/%m/%d"]]` → `2026/09/24`). It is a single-parameter
  action, so it takes a plain value, and its layout is validated at compile time against an allowlist of
  directives that no locale or platform decides (`%a`/`%A`/`%b`/`%B`/`%p`/`%c`/`%x`/`%X` are
  locale-decided, `%z`/`%Z` are empty on a zone-less value, `%e`/`%k`/`%l`/`%G`/`%V` are
  platform-dependent and `%s` would have to assume a zone). There is deliberately **no** `to_datetime`:
  the canonical string is a lossless representation of a datetime, while an object inside a chain would
  break the JSON value domain (the store, a UDF argument, and what `up2 trial` prints).

### Changed

- Version `0.3.0` → `0.4.0` → `0.5.0` (`005` §7: a new capability bumps the minor). Both bumps belong
  to this unreleased section: `0.4.0` with the L2 story model and the materialization cache, `0.5.0`
  with the type registry, the template store and the SOP commands.
- **A missing value has one outcome and a failure has one outcome**: the settlement policy is retired,
  so `eval_field` no longer takes `policy`, the `policy` block is gone from a story bundle, and
  `up2 trial` lost `--on-missing` / `--on-error` (they are rejected as unknown flags rather than
  silently ignored). A miss is "not there" — the key is absent from a field-map product, the item is
  skipped in a batch, and no `""` or `null` is invented — while a failure always raises, carrying its
  code and its JSON Pointer.
- **`py.get` is merged into `py.getitem`**: there is one subscript action now, and it follows Python
  semantics — a list / tuple by index, a dict by key, a string by character. Its parameter is named
  `at` and takes a reference, so a computed key works (`["py","getitem","$globals.field"]`, where a
  literal alone was required before), and a key or index that is not there is now an **error**
  (`UP2-E2018`, carrying the exception class and the key) instead of a `Missing` value, with no
  coercion (a string index on a list is never converted to an integer). `py.getattr` stays separate:
  a response object is not subscriptable, so only `getattr` reads its attributes.
- Version `0.2.0` → `0.3.0` (`005` §7: a new capability bumps the minor). Conformance: 60 → 61 pairs;
  implemented error codes: 25 → 26.
- The ambiguous slash writings are decided by one documented knob. Measured before: `03/04/2026` gave
  `2026-04-03` (the built-in table is day-first) while `03/04/2026 15:30` gave `2026-03-04` (the engine
  defaulted to month-first) — the same writing meaning two dates. `date_order` now orders the table's
  pair **and** the engine, its default is `DMY` (what the table always did), and the default is stated in
  the notes and in the operator reference.
- `format` and `lang` together are a compile-time `UP2-E1005`: the explicit format wins over the language
  fallback, so the language could never have an effect. The `UP2-E2007` fix line no longer advises
  "add lang" (the engine is reached by default now).
- Version `0.1.0` → `0.2.0` (`005` §7: a new capability bumps the minor).

### Removed

- **`Response` is no longer a type**: the answer to a request is whatever the host hands back, and a
  chain reads it, so the built-in `Response` key table went with it. A bundle whose step declares
  `"type": "Response"` now fails at that step with `UP2-E1011`; declare a host-registered type, or the
  built-in `dict` when the answer needs no validation.
- The chain layer's iteration construct is now **one operator** instead of three mechanisms: the
  node-level `select` fan-out, the `callback` operator with its named `presets` chains and the `$map`
  result-template directive are all retired (an inline field map plus the input from the stage above
  says the same thing once). The `item` scope root went with them — inside `each` the current element
  is simply the input value of every field chain — which also removed the `UP2-E1006` "deferred root"
  branch that existed only to explain `$item`, so the reserved roots are now `globals` / `locals` /
  `fields`. Lint L20 is retired (there is no container left to reference itself). Per-item structure is
  therefore assembled in `fields`, and an `emit` node has to name the field it exports — the exact key
  and its placement are left open for the node-layer change (`07` §4 question `i`). None of this
  changes implemented behavior: `select` / `callback` / `presets` / `$map` were
  never implemented, so the retirement is a design-level one.

### Fixed

- The natural-language path's own parse failure (`dateparser` raised) reported `UP2-E2007` with an
  **empty fix line**; it now names the text and the two remedies.
- Review follow-ups on `each`: a field map is now validated **before** anything is compiled — an empty
  map, and a field name that is empty or contains `.` (a key no `$…` path can address), are `UP2-E1005`
  at that key, while a map holding more than `MAX_FIELDS_PER_MAP` (256) fields is `UP2-E1012`; the
  per-element scope rule is now documented as implemented (a read falls back outward **by name**, so a
  key missing under a name the element wrote does not fall through to an outer scope); `each` writes
  per-element locals through `Scope.write_local`; `loads(source=…)` accepts its parameter by keyword
  again; and `Scope.chain()` became the private `Scope._lineage()`.

- `up2 ops` states, per action, which writing slot 3 takes: `param_form` is `none` (no parameter),
  `value` (the value itself) or `named` (a named object), derived from the parameters the action still
  has to fill — a parameter the action slot itself provides does not count. Both the human view
  (`[slot3=value]`) and `--json` report it, so a chain writer no longer has to infer the rule from the
  DSL spec.
- [`docs/operator-reference.md`](docs/operator-reference.md): a hand-maintained reference for the eleven
  operators — what each action means, which writing its parameter slot takes, and worked examples with
  their real outputs. The registry stays the authority (`up2 ops --json`); this page is the map next
  to it.
- [`docs/report/up2-report.md`](docs/report/up2-report.md): the machine-written catalogue — one case per
  declared `(operator, action)` pair, the multi-stage compositions and the compile-time invalid forms,
  each produced by a real run. `tests/report/test_catalogue.py` compares it with a fresh render, so the
  suite is both where freshness is enforced and where the file is refreshed
  (`UP2_UPDATE_REPORT=1 uv run pytest tests/report`); the timestamped HTML build stays local in
  `.cache/report/`.

### Fixed

- `parse_time.format` is validated without depending on the platform. The check probed the format
  with `strftime`, whose strictness comes from the C library: glibc passes an unknown directive
  through verbatim while the Windows CRT raises, so the same chain was rejected on Windows and
  compiled on Linux (caught by CI on 3.12). It now asks `strptime`, whose directive table lives in
  Python's `_strptime`, is identical across platforms and is what the operator actually runs — which
  also stops rejecting `%T` / `%-d` on Windows, where `strptime` reads them.
- Two report fixtures were wrong and are corrected, now guarded by the widened self-check (it covers
  the multi-stage compositions, not only the single-action cases): `["css", …, ["code", …]]` fed the
  sandbox a *list* (it needed a string), and the XPath namespace demo put the `{"expr", "ns"}` object
  in slot 2 instead of slot 3, so it never compiled. A rendered outcome is stable now as well: the
  measured sandbox duration in a limit message differed on every run and moved the tail of the
  180-character truncation window, so it is collapsed before truncation.
- `up2 ops` printed `[slot3=…]` for the 2-slot operators (`json` / `const` / `code`) whose parameter
  slot is slot 2; the label now follows the operator's arity.
- `py` validates its scalar parameters at compile time, as every other operator already did: a JSON
  container written where the function needs a string or an integer (`urljoin.base`, `slice.spec`,
  `split.sep` / `split.maxsplit`, `getitem.index`, `get.key`, `replace.old` / `replace.new`) and an
  unknown `sort.key` now fail `up2 lint` with `UP2-E1005`, a pointer at the parameter and a fix line
  showing the accepted writing — previously they passed lint and failed during evaluation with
  `UP2-E2002` and an empty fix. `default.value` (any JSON value), `join.sep` and `parse_time.lang`
  (both coerced) are deliberately unchanged.
- `02` §4 no longer claims that a reference inside a positional array or a named object is always
  resolved: resolution is leaf by leaf, by that leaf's own parameter kind. Measured,
  `["py","replace",["$locals.old","X"]]` replaces the literal text `$locals.old`, because both of
  `replace`'s parameters are `literal`.
- The sandbox isolation claims were corrected to the measured facts. Inside the `code` sandbox
  `compile` / `__import__` and `import socket` / `import subprocess` do **not exist**, `open` and
  `os.getenv` **exist and are blocked** (the rejection is the Monty runtime's default, not a policy
  this repository pins), and the language features `eval` / `exec` **do** exist and carry no
  capability. `N6` of design note `00` is restated as "no code capability inside a rule" with the
  opt-in `code` sandbox named as its single exception, and the statements in notes `01` §8, `02`
  §6.12, `04` §11.3 and `05` §9 item 7 were aligned with it.
- Stale status rows in the design notes were corrected against the repository's actual state: `05` §1
  no longer lists pytest / ruff / mypy / bandit as "pending", the `05` §2.1 dev-group sketch matches
  `pyproject.toml` (bandit and pip-audit are fetched with `uvx` in CI, not pinned in the dev group),
  and `07` §5 item 9 no longer reports the design/OpenSpec migration as pending.

### Changed

- `uniparser2[all]` no longer includes `ui`: the extra stays declared for the not-yet-implemented
  `up2 studio`, but installing everything no longer pulls in a GUI toolkit that no code imports.
- `demo_report.py` moved from the repository root to `tools/demo_report.py` (still not shipped in the
  wheel or the sdist); mypy's file list and the script's own usage text follow it.
- The READMEs state that `demo.py` and `tools/demo_report.py` exist only in a source checkout, and
  `tools/demo_report.py` is documented in the development section.
- The READMEs gained three sections: `What you get today (L1)` (an operator/engine/action table, with
  `up2 ops --json` named as the authoritative action list), `Not there yet (L2–L4)` (the
  implemented/unimplemented boundary, which until now had to be inferred from one clause), and an
  end-to-end HTML example (`css1 @href` → `py.urljoin`, RFC 822 → `py.parse_time`) whose printed
  outputs are the measured ones.
- The OpenSpec change `add-code-sandbox-operator` was archived
  (`openspec/changes/archive/2026-09-29-add-code-sandbox-operator/`) and its `code-execution`
  capability merged into `openspec/specs/code-execution/spec.md`.

### Planned

- The `up2 studio` trial bench (`06`, still a design draft). The chain-level structure it would
  exercise has landed: the story model replaced the v0.1 graph (`03` D-03-3), so there are no
  `seed` / `body` / `emit` node types and no `result` assembly, the fan-out is the `each` operator,
  and `up2 trial` / `snapshot` / `test` run a story today. The `ui` extra stays declared for the
  bench and is excluded from `all`.

## [0.1.0] - 2026-09-26

**One syntax convergence pass before L2**: the chain-step shape is unified as `[operator, mode, argument]`
(see below), `time` / `cast` are folded into `py`, and every `$` prefix is gone.

**L1 (the DSL operator layer) is complete**: all 10 operators (including `ctx` and `code`) are
implemented behaviorally with test coverage, the conformance audit is green on all 59 pairs, the engine
contract assertions (selectolax / lxml) pass, and `core/` coverage is 98%.

### Added

- **Kernel** (`src/uniparser2/core/`, zero third-party dependencies, no IO, no coroutines)
  - `values`: JSON value tree + `Opaque` handles + the `MISSING` sentinel
  - `errors`: the three states `Ok`/`Missing`/`Failed` and 25 implemented error codes
  - `ast`: chain-step triple parsing and a **character-for-character stable** serialization round-trip;
    `refs`: reference syntax (a leading `$` is a reference, `{"$lit": …}` escapes) and scopes
  - `registry`: explicit `@op` registration (two-phase, no half-registration), `find_spec` dependency
    probing, **per-action dependency declarations**, a dynamic action space, **arguments carried by the
    mode slot** (e.g. `@href` bound to `attr`), capability self-description
  - `udfs`: a pure registry for host-defined functions; `compile`: argument-slot shape classification →
    argument schema → precompilation
  - `evaluator`: three-state short-circuiting + `on_missing`/`on_error` policies + the
    `accepts_missing` exception; `export`: the single exit boxing point
  - `conformance`: the pure set-operation part of the conformance audit
- **Operators** (59 `(operator, action)` pairs in total, 10 operators)
  - **Chain-step syntax**: `[operator, mode, argument]`, where slot 2 is the behavior enum declared by
    that operator (`py`/`udf` use a function name) and slot 3 is any value (CSS selector / XPath /
    regex / function argument); operators with a single mode take only two slots (`json`/`const`/`code`).
    `Op.slot_roles` names only the two slots, and `action_slot` is derived from the arity (always 1 for
    three-slot operators, `null` for two-slot ones). A chain step's length must equal the operator's
    arity exactly (`UP2-E1004`), and diagnostics carry a **full JSON Pointer** (e.g. `/0/2/selector`).
  - `css` / `css1`: CSS selectors (HTML), `["css1", "@href", "a.download"]`; value modes
    `text`/`html`/`outer`/`self`/`nodes`/`remove`/`@attr-name` (no `$` prefix); the two differ only in
    cardinality — `css` takes every match (value actions yield a `list`) and `css1` takes only the first
    (yielding a scalar); `remove` is a pure function (it returns a pruned copy); `text` excludes text
    from `script`/`style`/`noscript`; nodes are boxed as `DomNode(Opaque)` and are always rejected at
    the exit
  - `xpath`: XPath queries (XML, lxml), `["xpath", "text", "//item/title"]`; value modes
    `text`/`nodes`/`self`; attributes are taken directly as strings with `//a/@href`, so there is
    **no** `@attr` value mode; namespaces go through an `ns` mapping; at compile time it runs against
    an empty document to surface errors such as undefined prefixes early; when the result is empty and
    the document root carries a default namespace, `Missing` calls out that silent trap
  - `json`: jmespath dotted-path queries, `["json", "data.html"]` (**two slots**; the single behavior
    takes no mode slot), with the expression precompiled at compile time
  - `re`: `["re", "search", "\\d+"]`; modes `search` / `group` / `findall` (`search` = `group(0)`,
    `group` takes a capture group, `findall` = every match) plus static detection of nested quantifiers
    (ReDoS)
  - `py`: **31 whitelisted functions**, `["py", "urljoin", "$globals.base_url"]` (write `""` in slot 3
    for a no-argument action); includes `parse_time` (time parsing, with a stdlib format table and
    **no required dependency**, plus optional `dateparser`) and
    `str`/`int`/`float`/`bool`/`list`/`from_json` (type conversion)
  - `udf`: host-registered named functions (the chain contains no code); unregistered names fail at
    compile time with `UP2-E1010`
  - `code`: **sandboxed execution of in-chain code** (`["code", {"src": "len(obj)"}]`, **two slots** —
    the single behavior takes no mode slot). `src` is a snippet of statements and **the value of the
    last expression is the return value** (if the tail is an assignment / `print` / a comment, it is
    `None`); the fixed inputs are `obj` (the upstream value) and `ctx` (the **scope object**, read as
    attributes: `ctx.locals.x` / `ctx.globals.y`, where `locals` automatically holds the temporary
    variables produced while parsing this node), with an optional `inputs` named entry point (whose
    only benefit is validating references at compile time); `ctx` holds JSON values only — handles are
    excluded and **no error is raised** (same principle as `UP2-E2003`); assignments to `ctx` inside
    the sandbox **do not flow back** into the engine scope (use `ctx.set` in the chain to write to the
    scope). **Isolation**: the sandbox has no files, environment variables, network or process
    operations, mounts no host capability at all, and only JSON values go in and out, so classic escape
    chains fail at the language level; the sandbox ships subsets of `json`/`re`/`math`/`base64`/
    `datetime`/`collections`/`itertools`/`functools`/`unicodedata`, and the `py` whitelisted functions
    are callable without an `import` (each such call counts as one host round-trip). **Limits live on
    the host side only** (`uniparser2.ops.code.configure`: 64 MB of memory, 0.5 s per execution, 5 s
    request timeout, a round-trip budget of 1000); passing a limit name inside a chain is just an
    unknown argument (`UP2-E1005`); **deterministic by default** (frozen clock + fixed timezone +
    no `sleep` + seeded randomness), and the host can explicitly switch back to following the host
    (giving up the cross-machine replay guarantee). **The optional extra `uniparser2[code]`
    (`pydantic-monty`) does not exist by default and is not part of `all`**; without it, the operator
    fails at compile time with `UP2-E1107`. New error codes `UP2-E2016` (sandbox execution limit
    exceeded) and `UP2-E2017` (sandbox code error, including syntax and unsupported constructs); the
    `UP2-E2009` wording was generalized from "`udf` returned…" to "operator returned…"; the
    conformance pair count went 58 → 59 (adding `("code", "run")`). It shares the same argument
    conventions as `udf` (the upstream value is the first argument, named configuration goes in the
    slot-3 object, `ctx` is injected by function signature and is a reserved name)
  - `ctx`: `["ctx", "get", "locals.x"]` (`get`/`set`/`del`/`map`, with writes hard-limited to
    `locals`/`fields`)
  - `const`: `["py","const", "article"]` (two slots; emits the literal as-is)
- **Host integration**: explicit `register_udf` registration plus automatic discovery through the
  `entry_points` group `uniparser2.udfs` (IO is confined to the `host` layer)
- **Command line** `up2`: `ops --json` (operator capability self-description with full
  dependency/availability data), `conformance --check` (the conformance-audit gate), `lint`
  (compile-time validation), `trial` (local trial runs: `--input`/`--global`/`--product`/policy
  overrides)
- **Engineering**: uv managing dependencies and publishing, src layout, `uv.lock` committed, ruff
  (including the C901 complexity gate) / mypy strict / pytest config, CI (a 3.12–3.14 matrix) and a
  tag-triggered release workflow, `py.typed` (PEP 561), and an OpenSpec spec-driven process
- **Tests**: 363 passed / 3 skipped (every skip is a "dependency absent" branch, covered by an
  equivalent monkeypatched case once the dependency is installed), covering the operator behavior
  dictionary, compile-time and runtime error codes case by case, the serialization fixed point, CLI
  end-to-end runs and the conformance audit; `core/` coverage is 98% (gate:
  `--cov=uniparser2.core --cov-fail-under=95`)

### Known limitations

- **No runtime timeout for regular expressions**: Python's `re` has no `timeout` parameter (measured),
  so ReDoS protection is limited to static detection of nested quantifiers at compile time, missing
  shapes such as overlapping alternations
- `py.html_to_markdown` takes no arguments: the selected library `html-to-markdown` has no concept of a
  base URL, so use `py.urljoin` to complete relative links
- **The default-namespace trap in `xpath`**: in a document such as `<urlset xmlns="…">`, `//loc`
  returns empty **without raising**; the diagnostic calls this out and gives the fix
  (`//*[local-name()='loc']` or an `ns` mapping), but XPath itself cannot turn this step into a
  compile-time error
- **The `code` sandbox implements only a subset of CPython 3.14**: class inheritance, generators
  (`yield`), `match`, `del`, `async with` / `async for`, wildcard imports and the like are rejected at
  parse time (`UP2-E2017`), and the syntax of `src` is validated **at runtime only**
- **`code` is a language-level sandbox, not OS-level isolation**: there are no file / environment
  variable / network / process operations in the sandbox and it mounts no host capability, but it does
  not promise to withstand vulnerabilities in the interpreter itself (Monty and its worker binary) or
  in other components of the host process
- Chain-level structure (`seed`/`parse`/`emit`, `select` fan-out, `result` assembly) belongs to L2 and
  is not implemented yet

### Changed

- **The slot shape is unified as `[operator, mode, argument]`**: slot 2 is the behavior enum declared
  by that operator (`py` / `udf` use a function name), slot 3 is any value (CSS selector / XPath /
  regex / function argument); operators with a single mode take two slots
  (`["json", "data.html"]` / `["py","const", "article"]`). The **enumeration strength increases** across the
  three positions: operator (registry) → mode (declared by each operator) → argument (any value).
  `up2 ops` prints the slot roles of every operator.
  > Midway, `css` / `xpath` were flipped to "selector first" and then **reverted**, because it broke
  > this zero-exception rule (two shapes to remember, diagnostics pointing in two forms); the uniform
  > shape won.
- **`time` / `cast` are folded into `py`**: time parsing → `py.parse_time` (no required dependency plus
  optional `dateparser`); type conversion →
  `py.str`/`py.int`/`py.float`/`py.bool`/`py.list`/`py.from_json`. The operator count went from 11 down
  to 9, with the conformance declarations unchanged (the functions folded into `py` are carried by
  `py`'s action count); the `code` operator was added afterwards, bringing the operator count to 10 and
  the declarations to 59 pairs.
- **Every `$` prefix is gone**: `$text`→`text`, `$nodes`→`nodes`, `$remove`→`remove`, `$get` (the mode
  slot of `json`) removed, `$parse` removed; `@attr-name` keeps its `@`. `$` now means only references
  (`$globals.x`) and directive objects (`{"$lit": …}`).
- **`re` modes were renamed**: `$match`→`search` (the implementation is `re.search(...).group(0)`,
  whereas `re.match` is anchored), `$all`→`findall` (aligning with `re.findall`); `$group`→`group`.
- **A chain step's length now matches the operator arity exactly**: three-slot operators must write
  three positions (write `""` in position 3 for a no-argument action) and two-slot operators write two;
  the "omit the tail" form is gone.
- **Diagnostics carry a full JSON Pointer**: precompilation errors inside an operator are now joined
  with the step index and the argument position (e.g. `/0/2/selector`, `/0/2/format`), and an unknown
  action also points at its position (`/0/1`).
- **`css1` was removed at one point and restored after measuring**: both cardinalities (`css` = all →
  `list`; `css1` = first → scalar) are explicitly safer; `nodes` cannot carry "take every value" in L1
  (it hands over an `Opaque` handle, and taking text has to wait for L2 fan-out); `css_first` measured
  as **not** a fast path (1.0–1.1x across 5000–20000 matches), the real gain being N-1 fewer value
  extractions (`text` over 5000 matches: 4.25 ms vs 108.9 ms)
- **The `beautifulsoup4` fallback engine and the `any_requires` mechanism were removed**: the two
  engines behave identically on HTML, and XML moved to `xpath` (lxml)
- **Extras were renamed**: `html-bs4` → `xml` (lxml), and `html` now installs selectolax only

[Unreleased]: https://github.com/ClericPy/uniparser2/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ClericPy/uniparser2/releases/tag/v0.1.0
