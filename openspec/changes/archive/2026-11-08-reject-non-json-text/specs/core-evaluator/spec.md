# Spec Delta

## ADDED Requirements

### Requirement: Chain text is read and written as strict JSON

Every conversion between a chain and text SHALL be strict: writing MUST pass `allow_nan=False`, and
reading MUST reject the non-JSON constants `Infinity`, `-Infinity` and `NaN`. A text that is not
valid JSON MUST fail with `UP2-E1004` and a fix line, never with a bare decoder exception, because
the same public entry point answers a coded diagnostic for every other kind of bad chain.

#### Scenario: Malformed chain text is a coded failure

- **WHEN** `loads("not json")` is called
- **THEN** it raises an `Up2Error` with code `UP2-E1004` whose message says the text is not valid JSON

#### Scenario: A non-JSON constant is still refused

- **WHEN** `loads('[["const",Infinity]]')` is called
- **THEN** it raises `UP2-E1004`, as it did before this change

#### Scenario: Writing stays strict

- **WHEN** `dumps` is called on a stage whose parameter is `float("nan")`
- **THEN** it raises `UP2-E1004` and writes no text
