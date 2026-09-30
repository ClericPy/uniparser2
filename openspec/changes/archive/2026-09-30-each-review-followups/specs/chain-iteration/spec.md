# Spec Delta

## MODIFIED Requirements

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
- **THEN** the result is `[{"kids": [{}]}]` under a dropping policy: the inner element owns `_a`, so the
  read is a miss, never the outer element's `{"b": 1}`

#### Scenario: An element's local does not outlive the element

- **WHEN** the chain is `[["each", {"_t": [["py","strip",""]]}], ["ctx","get","locals._t"]]` and the
  value is `["a"]`
- **THEN** the final read resolves as a missing value under the effective policy, never as the
  element's temporary
