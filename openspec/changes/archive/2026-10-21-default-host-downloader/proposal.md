# Proposal

## Why

The two committed live samples (`books.toscrape.com`, `quotes.toscrape.com`) each carry a **host
script** that fetches the pages — and each script writes its own `urllib` call, its own timeout
handling, its own redirect and cookie story. Every new site repeats that file, and nothing in the
package offers a starting point, so the first thing a user writes is a network client.

The same two samples have **no regression coverage**: a snapshot runner has no host to answer a
suspension, so a chain that fetches cannot be regressed offline at all.

## What Changes

- **A default synchronous downloader** in a new `uniparser2/host/` package: it takes the request
  dictionary the kernel hands over (`url`, `method`, `headers`, `timeout`, `body`, `params`, `json`)
  and answers with a response object carrying `text` and `url` — the shape the samples already read
  with `py.getattr`. It uses the **standard library only** (`urllib`), so the package's zero-
  dependency rule (`01` I1) holds; `morebuiltins`' request helper was read for its parameter handling
  but **not adopted as a dependency**.
- **The two sample hosts use it**, so the duplicated fetching code is gone and the samples double as
  the downloader's documentation.
- **A request cache** under `.cache/` (git-ignored, never committed): the host writes every answer
  it fetches, keyed by the request, and a later run replays from the cache instead of the network.
  This is what makes a live sample testable offline.

## Capabilities

### New Capabilities

- `host-runtime`: the host-side helpers a caller needs to drive a story — the default downloader and
  the request cache.

### Modified Capabilities

- `template-store`: the sample case layout gains the optional cached responses.

## Impact

- New package: `src/uniparser2/host/` (downloader, cache, the response shape).
- Samples: both `samples/*/host.py` use the default downloader; the cache directory is created on
  demand and is not committed.
- Docs: notes `04` §7 (the sample layout), `03` §4.1 (the host's answer), `docs/operator-reference.md`,
  both READMEs, `CHANGELOG.md`.
- Tests: the downloader against a local HTTP server (no network), the cache's hit / miss / key rules.
