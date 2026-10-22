# Spec Delta

## ADDED Requirements

### Requirement: The snapshot runner answers a suspension from the request cache

The snapshot runner (`up2 snapshot`, `up2 test`) SHALL answer a story's `Request` and `RequestBatch`
suspensions from the **request cache** (`host-runtime`), so a chain that fetches can be frozen and
regressed **offline**. The runner SHALL NOT reach the network: a request with no cached answer is a
**miss**, and a miss SHALL be reported as a plain error naming the request, not guessed at and not
fetched.

A `call` suspension SHALL still be reported as needing a host: the cache holds network answers, not
the result of a host function.

#### Scenario: A suspended story runs from the cache

- **WHEN** the cache holds the answer for the request the story makes, and `up2 snapshot` runs the
  story
- **THEN** the run SHALL continue with the cached answer and reach its exit product

#### Scenario: A missing answer is reported

- **WHEN** the cache holds no answer for the request the story makes
- **THEN** the command SHALL report that the request is not cached, and SHALL write no snapshot

#### Scenario: A call suspension still needs a host

- **WHEN** the story declares a `call` step
- **THEN** the command SHALL report that a snapshot runner has no host to answer it
