# Proposal

## Why

The two live samples still have **no regression coverage**: a snapshot runner has no host to answer a
suspension, so `up2 snapshot` / `up2 test` report "a snapshot runner has no host to answer it" and stop
(`03` §4.1). The request cache now exists (`default-host-downloader`), so the answers are already on
disk — the runner simply does not know about it.

The second gap is the request's **body**. A body is binary, so it cannot be JSON; today the downloader
accepts a text body and the cache hashes it as text, which means the same bytes written two ways are
two cache entries and a binary body cannot be expressed in the chain data at all.

## What Changes

- **The request body is base64**, always: the `body` key carries base64 **text**, and the `json` key
  carries a JSON value. The request dictionary is therefore JSON throughout, which is what lets it
  live in a chain, in a cache key and in a journal.
- **The snapshot runner answers a suspension from the cache**: `up2 snapshot` and `up2 test` replay the
  cached answers, so a story that fetches can be frozen and regressed **offline**. A request with no
  cached answer is a **miss** — the runner reports it and stops, rather than reaching the network
  (the CLI has no business fetching on its own).
- **The cache is what the runner reads**, so the two live samples become regression cases as soon as
  their answers have been fetched once.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `host-runtime`: the request's body is base64; the cache's key covers the decoded body.
- `template-store`: the snapshot runner replays a suspended story from the request cache.

## Impact

- `uniparser2.net`: the body is base64 text (decoded on the way out, hashed as bytes on the way into
  the key).
- `uniparser2/cli`: `up2 snapshot` / `up2 test` answer a suspension from the cache; a miss is reported
  as a plain error.
- The two sample hosts: they answer the same request dictionary, so the cache they write is the cache
  the runner reads.
- Docs: notes `03` §4.1, `04` §7-S4/S5, `docs/operator-reference.md`, `CHANGELOG.md`.
