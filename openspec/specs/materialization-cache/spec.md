# materialization-cache Specification

## Purpose

Keeps a run's derived parsing artifacts — an HTML document, an XML document, a parsed JSON tree —
available to every operator that consumes the same source, so one document is materialized once per
run instead of once per stage, without letting a run's memory grow without bound and without letting
two runs observe each other.

## Requirements

### Requirement: The cache is scoped to one run

The materialization cache SHALL have the lifetime of one run. A run SHALL observe only the artifacts
it materialized itself, a nested evaluation within the run (a field map, an `each` element) SHALL share
the run's cache rather than getting one of its own, and no artifact SHALL outlive the run that produced
it. Two runs of the same source SHALL NOT observe each other's entries.

#### Scenario: Two fields of one run share one artifact

- **WHEN** two field chains of the same run materialize the same document in the same format
- **THEN** the second field SHALL obtain the artifact the first field materialized

#### Scenario: A nested evaluation shares the run's cache

- **WHEN** an `each` element's field chain materializes a document its own step already materialized
- **THEN** the element SHALL obtain the step's artifact, and no second artifact SHALL be accounted

#### Scenario: Nothing is shared across runs

- **WHEN** a second run materializes the same source text
- **THEN** it SHALL materialize it again, and the first run's artifacts SHALL be gone

### Requirement: The key is the target format plus the source value

A cache entry SHALL be addressed by the target format and the source value. A lookup SHALL match the
source by object identity first and SHALL fall back to a content comparison of the source text, so the
same text reaches the same entry whether or not it is the same Python object. Text materialized as one
format SHALL NOT be served for another format: the same source text materialized as HTML and as XML
SHALL be two entries.

#### Scenario: The same text reached twice

- **WHEN** the same text is materialized in the same format twice, once by identity and once as an
  equal but distinct string
- **THEN** the second materialization SHALL be a hit and SHALL return the first artifact

#### Scenario: One text, two formats

- **WHEN** the same text is materialized as HTML and as XML in one run
- **THEN** the run SHALL hold two entries, one per format

#### Scenario: A different text is a different entry

- **WHEN** a run materializes a document and then a different document in the same format
- **THEN** the second materialization SHALL be a miss and SHALL build its own artifact

### Requirement: The cache is bounded by bytes and by artifact count, with LRU eviction

The cache SHALL be bounded by `MAX_MATERIALIZE_BYTES`, accounted in the **materialized** bytes of the
artifacts it holds rather than in the bytes of their sources, and by `MAX_MATERIALIZE_ITEMS`, the
number of artifacts one run retains. When an insertion would exceed either bound, the cache SHALL evict
least-recently-used entries until the bound holds. The accounting SHALL be observable, so a host or a
test can read the materialized bytes and the number of artifacts the run currently holds. Eviction
SHALL NOT change any result: an evicted source is materialized again on its next use.

#### Scenario: The item bound evicts the least recently used artifact

- **WHEN** a run materializes more artifacts than `MAX_MATERIALIZE_ITEMS` allows
- **THEN** the run SHALL hold at most that many, the artifact it used least recently SHALL be the one
  evicted, and a later use of that source SHALL be a miss that rebuilds it

#### Scenario: The byte bound evicts by materialized size

- **WHEN** a run materializes artifacts whose materialized bytes together exceed
  `MAX_MATERIALIZE_BYTES`
- **THEN** the cache SHALL evict least-recently-used artifacts until the accounting is within the
  bound, and the reported materialized bytes SHALL agree with the artifacts retained

#### Scenario: A hit refreshes the entry's recency

- **WHEN** an artifact is read and then the cache is pushed over a bound by another insertion
- **THEN** the artifact that was just read SHALL outlive artifacts read earlier

### Requirement: A single artifact larger than the byte cap is retained while it is in use

An artifact whose materialized size alone exceeds `MAX_MATERIALIZE_BYTES` SHALL still be retained while
it is the artifact in use, so the operator that asked for it is served a hit rather than paying a
second parse. The worst case SHALL therefore be the byte cap plus that one artifact. Such an artifact
SHALL be evictable like any other once it is no longer the one in use.

#### Scenario: An input larger than the cap

- **WHEN** a run materializes one document whose materialized size exceeds the byte cap and the same
  document is consumed again while it is in use
- **THEN** the second consumption SHALL be a hit, and the run's accounting SHALL be the cap plus that
  one artifact rather than a failure

#### Scenario: The over-cap artifact is evictable afterwards

- **WHEN** the run then materializes another document in the same format
- **THEN** the over-cap artifact SHALL be evicted and the accounting SHALL be within the bound

### Requirement: A cached artifact is never mutated, and a hit is indistinguishable from a miss

Materialization SHALL be a pure function of the source text: an artifact obtained from the cache SHALL
be observably identical to the same artifact built without the cache, so no consumer MAY depend on
whether its source was a hit or a miss. A cached artifact SHALL NOT be mutated in place by any
operator; an operator whose work would change the artifact (pruning an HTML document, for example)
SHALL apply that work to its own copy.

#### Scenario: The same document twice, with and without the cache

- **WHEN** two consumers materialize and read the same document through the cache, and the same two
  reads are performed with the cache evicting between them
- **THEN** the values extracted SHALL be equal on both paths

#### Scenario: A destructive consumer leaves the artifact intact

- **WHEN** one field prunes nodes from a document and a later field reads the same document
- **THEN** the later field SHALL see the unpruned document

#### Scenario: Eviction costs a parse and nothing else

- **WHEN** a source is evicted and then used again in the same run
- **THEN** the consumer SHALL produce the same value it produced before the eviction

### Requirement: The cache is released with the run

The run's cache SHALL be released when the run ends or is abandoned: a run that is closed before its
end SHALL not keep its artifacts, and no later run SHALL find them. Releasing the cache SHALL NOT
require IO, threads or a finalizer: the release SHALL follow from the run's own lifetime.

#### Scenario: A run that reaches its end

- **WHEN** a run completes and the host inspects the cache it was given
- **THEN** that cache SHALL no longer be the run's live cache, and the run's artifacts SHALL not be
  reachable from a new run

#### Scenario: A run abandoned before its end

- **WHEN** a host releases a run that is suspended or mid-step
- **THEN** the run's artifacts SHALL be released with it, and the run's remaining steps SHALL not run
