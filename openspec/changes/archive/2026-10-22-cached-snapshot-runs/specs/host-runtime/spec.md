# Spec Delta

## ADDED Requirements

### Requirement: The request's body is base64 text

The `body` key of a request dictionary SHALL carry the body as **base64 text**, because a body is
binary and the request dictionary is JSON throughout (it lives in chain data, in a cache key and in a
journal). The `json` key SHALL carry a JSON value instead, and the two are alternatives: a request
with a `json` key sends that value as JSON.

The downloader SHALL decode the base64 before sending it, and SHALL report a body that is not valid
base64 as an error. A body given as raw bytes (a host's own call, not chain data) SHALL still be
accepted and encoded on the way into the cache key.

#### Scenario: A base64 body is sent decoded

- **WHEN** the downloader is given `{"url": "…", "method": "POST", "body": "aGVsbG8="}`
- **THEN** the server SHALL receive the five bytes `hello`

#### Scenario: A body that is not base64 is an error

- **WHEN** the downloader is given `{"url": "…", "method": "POST", "body": "not base64!!"}`
- **THEN** it SHALL raise an error naming the body

#### Scenario: A JSON body wins over a base64 body

- **WHEN** the downloader is given both `body` and `json`
- **THEN** it SHALL send the JSON value

## MODIFIED Requirements

### Requirement: The host-side request cache is keyed by the request

The package SHALL provide a cache for the answers a host fetched, so a later run replays them
instead of the network. The cache SHALL live outside the package's tracked files (a local `.cache/`
directory), MUST NOT be committed, and SHALL be keyed by the **whole request** — the method, the URL,
the sorted headers and the **decoded** body — so two different requests never share an answer.

A cache entry SHALL record the response's text and final URL. A run against the cache SHALL produce
the same answers as the run that filled it; a request with no entry SHALL be a miss, and the caller
decides what to do with a miss (fetch it, or fail).

#### Scenario: A second run replays the answer

- **WHEN** a request is fetched once and the same request is asked for again
- **THEN** the second ask SHALL answer from the cache, and the server SHALL have been asked once

#### Scenario: A different body is a different key

- **WHEN** the same URL is requested twice with two different bodies
- **THEN** the two requests SHALL have two different cache keys

#### Scenario: The same body written two ways is one key

- **WHEN** a body is cached once as base64 text and the same bytes are offered as raw bytes
- **THEN** the two SHALL share one cache key

#### Scenario: A miss is a miss

- **WHEN** a request that was never fetched is asked for
- **THEN** the cache SHALL report no entry, and SHALL NOT answer with an empty body

