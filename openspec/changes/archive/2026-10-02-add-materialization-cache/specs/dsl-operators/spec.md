# Spec Delta

## ADDED Requirements

### Requirement: A text-consuming operator materializes through the run's cache

Every operator that must turn text into structure — `css` / `css1` (HTML), `xpath` (XML) and `json`
(JSON text) — SHALL obtain that structure from the run's materialization cache, keyed by its own target
format and the source text, instead of building one structure per stage. The operator SHALL behave
identically whether the structure was freshly materialized or came from the cache, and it SHALL NOT
depend on the cache being present: a chain evaluated outside a run SHALL still materialize on demand.

#### Scenario: Two stages over one document

- **WHEN** two stages of one run select from the same document text
- **THEN** the document SHALL be materialized once, and both stages SHALL produce the values they
  produce without a cache

#### Scenario: A format an operator does not own is not reused

- **WHEN** a chain selects from a document as HTML and another stage queries the same text as XML
- **THEN** each SHALL materialize the structure of its own format, and neither SHALL be served the
  other's artifact

#### Scenario: Evaluation without a run

- **WHEN** a single field chain is evaluated outside any run
- **THEN** each consuming stage SHALL still materialize what it needs, with no error

### Requirement: An operator never mutates a cached structure

An operator whose work would alter the materialized structure SHALL apply that work to a copy of its
own, so a second consumer of the same source sees the structure as materialized. This holds for every
consuming operator, not only for the ones whose pruning is visible today.

#### Scenario: Pruning leaves the cached document alone

- **WHEN** one stage prunes nodes from a document and a later stage selects from the same document
- **THEN** the later stage SHALL select from the unpruned document

#### Scenario: A node a stage handed on

- **WHEN** a stage hands out a node of a materialized document and a later stage reads that node
- **THEN** the node SHALL resolve against the document it came from, unchanged
