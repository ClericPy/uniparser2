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
element, so a later field can read what an earlier field of the same element produced. Every field's
value MUST be written into the element scope's `$locals` under the field name. The dictionary an
element yields MUST carry the field names that do not start with `_`, in declaration order.

#### Scenario: A later field reads an earlier field's value

- **WHEN** the chain is `[["each", {"_raw": [["py","strip"]], "seen": [["ctx","get","locals._raw"]]}]]`
  and the value is `["  a  "]`
- **THEN** the result is `[{"seen": "a"}]`

#### Scenario: A product field is a local too

- **WHEN** the chain is `[["each", {"a": [["py","strip"]], "b": [["ctx","get","locals.a"]]}]]` and the
  value is `["  x  "]`
- **THEN** the result is `[{"a": "x", "b": "x"}]`

### Requirement: A `_`-prefixed key is a per-element local and never enters the dictionary

Every field of an element SHALL be stored as a local of that element. A field name beginning with `_`
MUST be absent from the element's dictionary while remaining readable by the later fields of the same
element; a field without the prefix MUST appear in the dictionary as well.

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

The argument of `each` — and a story node's field map, which is the same object shape — MUST be an
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

### Requirement: A run carries a `public` scope, shared by every node

A run SHALL expose a third scope, `public`, beside `globals` and `locals`: it is **writable** and
**readable from any node of the run**, and it lives exactly as long as the run. It SHALL NOT be part
of the chain data, so it never enters the fingerprint: a run's `public` values are runtime notes, not
a property of the chain.

The reference root `public` SHALL be reserved, and `$public.<path>` SHALL read it. A write through
`ctx.set` SHALL accept a `public.` path; a write to `globals`, `in`, `obj` or any other
root SHALL still be refused.

`globals` SHALL stay read-only and `locals` SHALL stay private to the scope that wrote it, so the
three scopes read as constants / shared / private.

#### Scenario: A node writes and the next node reads

- **WHEN** a node's field map writes `["ctx","set","public.page"]` and a later node call reads
  `$public.page`
- **THEN** the later call SHALL read the written value

#### Scenario: `public` is not chain data

- **WHEN** a run writes `public.page` and the chain is fingerprinted
- **THEN** the fingerprint SHALL be the same as it was before the write

#### Scenario: A write outside the writable roots is refused

- **WHEN** a node writes `["ctx","set","globals.page"]` or `["ctx","set","in.page"]`
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
