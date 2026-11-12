# host-runtime Specification

## Purpose

The host-side half of a fetching story: a default synchronous downloader, a request cache that replays
answers, and the request object that carries binary bodies as JSON.

## Requirements

### Requirement: The package offers a default synchronous downloader

The package SHALL provide a host-side downloader `fetch(request)` that takes one request object and
answers a response object. The request keys SHALL be `url` (required), `method` (default `GET`),
`headers`, `timeout`, `body`, `params` and `json`. The response MUST carry at least `text` (the decoded
body) and `url` (the final URL after redirects), so a chain reads it with `py.getattr`.

#### Scenario: A GET request

- **WHEN** the downloader is given `{"url": "http://127.0.0.1:<port>/page", "method": "GET"}` and the
  server answers `200` with a body
- **THEN** the response's `text` SHALL be that body and its `url` SHALL be the requested URL

#### Scenario: A header and a timeout are honoured

- **WHEN** the downloader is given a `headers` object and a `timeout`
- **THEN** the request SHALL carry that header and SHALL give up after that many seconds

### Requirement: The default downloader is stdlib-only and never silent

The downloader SHALL be synchronous and use the standard library only: the package's zero-dependency
rule (`01` I1) covers it, and a missing optional dependency MUST NOT be required. A request that cannot
be sent — an unreachable host, a timeout, a non-HTTP scheme — MUST raise an error the host can report,
never a silent empty answer.

#### Scenario: A non-HTTP scheme is refused

- **WHEN** the downloader is given `{"url": "file:///etc/passwd"}`
- **THEN** it SHALL raise an error naming the scheme

### Requirement: The host-side request cache replays answers

The package SHALL provide a cache for the answers a host fetched, so a later run replays them instead of
the network. The cache MUST live outside the package's tracked files (a local `.cache/` directory) and
MUST NOT be committed. A cache entry SHALL record the response's text and final URL.

#### Scenario: A second run replays the answer

- **WHEN** a request is fetched once and the same request is asked for again
- **THEN** the second ask SHALL answer from the cache, and the server SHALL have been asked once

#### Scenario: A miss is a miss

- **WHEN** a request that was never fetched is asked for
- **THEN** the cache SHALL report no entry, and SHALL NOT answer with an empty body

### Requirement: The cache key is the whole request

The cache key SHALL be the whole request — the method, the URL, the sorted headers and the decoded body
— so two different requests never share an answer. A run against the cache SHALL produce the same
answers as the run that filled it; a request with no entry MUST be a miss, and the caller decides
whether to fetch it or fail.

#### Scenario: A different body is a different key

- **WHEN** the same URL is requested twice with two different bodies
- **THEN** the two requests SHALL have two different cache keys

#### Scenario: The same body written two ways is one key

- **WHEN** a body is cached once as base64 text and the same bytes are offered as raw bytes
- **THEN** the two SHALL share one cache key

### Requirement: The request's body is base64 text

The `body` key of a request object SHALL carry the body as base64 text, because a body is binary and the
request object is JSON throughout (it lives in chain data, in a cache key and in a journal). The `json`
key SHALL carry a JSON value instead; the two are alternatives, and a request carrying `json` sends that
value as JSON.

#### Scenario: A base64 body is sent decoded

- **WHEN** the downloader is given `{"url": "…", "method": "POST", "body": "aGVsbG8="}`
- **THEN** the server SHALL receive the five bytes `hello`

#### Scenario: A JSON body wins over a base64 body

- **WHEN** the downloader is given both `body` and `json`
- **THEN** it SHALL send the JSON value

### Requirement: Body validation is the downloader's job

The downloader SHALL decode the base64 before sending it, and MUST report a body that is not valid
base64 as an error. A body given as raw bytes by a host's own call SHALL still be accepted and encoded
on the way into the cache key.

#### Scenario: A body that is not base64 is an error

- **WHEN** the downloader is given `{"url": "…", "method": "POST", "body": "not base64!!"}`
- **THEN** it SHALL raise an error naming the body
