# Spec Delta

## ADDED Requirements

### Requirement: The package offers a default synchronous downloader

The package SHALL provide a host-side downloader that takes the request dictionary the kernel hands
over and answers with a response object. The request dictionary's keys SHALL be the ones the request
product declares (`03` §4.1): `url` (required), `method` (default `GET`), `headers`, `timeout`,
`body`, `params` and `json`. The response SHALL carry at least `text` (the decoded body) and `url` (the
final URL after redirects), so a chain can read it with `py.getattr`.

The downloader SHALL be **synchronous** and SHALL use the **standard library only**: the kernel's
zero-dependency rule (`01` I1) covers the whole package. A missing optional dependency MUST NOT be
required for it to work.

A request that cannot be sent — an unreachable host, a timeout, a non-HTTP scheme — SHALL raise an
error the host can report, never a silent empty answer.

#### Scenario: A GET request

- **WHEN** the downloader is given `{"url": "http://127.0.0.1:<port>/page", "method": "GET"}` and the
  server answers `200` with a body
- **THEN** the response's `text` SHALL be that body and its `url` SHALL be the requested URL

#### Scenario: A non-HTTP scheme is refused

- **WHEN** the downloader is given `{"url": "file:///etc/passwd"}`
- **THEN** it SHALL raise an error naming the scheme

#### Scenario: A header and a timeout are honoured

- **WHEN** the downloader is given a `headers` object and a `timeout`
- **THEN** the request SHALL carry that header and SHALL give up after that many seconds

### Requirement: The host-side request cache is keyed by the request

The package SHALL provide a cache for the answers a host fetched, so a later run replays them
instead of the network. The cache SHALL live outside the package's tracked files (a local `.cache/`
directory), MUST NOT be committed, and SHALL be keyed by the **whole request** — the method, the URL,
the sorted headers and the body — so two different requests never share an answer.

A cache entry SHALL record the response's text and final URL. A run against the cache SHALL produce
the same answers as the run that filled it; a request with no entry SHALL be a miss, and the caller
decides what to do with a miss (fetch it, or fail).

#### Scenario: A second run replays the answer

- **WHEN** a request is fetched once and the same request is asked for again
- **THEN** the second ask SHALL answer from the cache, and the server SHALL have been asked once

#### Scenario: A different body is a different key

- **WHEN** the same URL is requested twice with two different bodies
- **THEN** the two requests SHALL have two different cache keys

#### Scenario: A miss is a miss

- **WHEN** a request that was never fetched is asked for
- **THEN** the cache SHALL report no entry, and SHALL NOT answer with an empty body
