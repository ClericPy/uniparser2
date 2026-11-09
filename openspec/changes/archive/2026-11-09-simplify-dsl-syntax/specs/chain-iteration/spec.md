# Spec Delta

## MODIFIED Requirements

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
