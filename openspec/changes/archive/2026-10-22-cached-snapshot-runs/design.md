# Design

## Context

See `proposal.md` — Why. The request cache exists (`default-host-downloader`) and the two sample hosts
already write to it, but the snapshot runner does not read it: `cli/samples.py::_run_story` reports
"a snapshot runner has no host to answer it" and stops. The two live samples therefore have no
regression coverage at all.

## Goals / Non-Goals

**Goals:**

- A story that fetches can be frozen and regressed offline.
- The request dictionary stays JSON throughout, so it can live in chain data, in a cache key and in a
  journal.
- The runner never reaches the network.

**Non-Goals:**

- The runner fetching anything (the CLI has no business making requests; a host does that).
- A "record" command: the recording already happens — the sample hosts write the cache on every run,
  so "run the host once, then the runner can replay" needs no new command.
- Caching a `call`'s result: that is a host function's business, not a network answer's.

## Decisions

### D1 — The body is base64 text

A body is binary, and the request dictionary is JSON data (it is part of a chain, of a cache key and
of a journal). So `body` carries base64 **text** and the downloader decodes it before sending. The
`json` key stays as the alternative for a JSON payload. This is the only spelling that keeps one
request dictionary usable in all three places.

### D2 — The cache key hashes the *decoded* body

The key is over the bytes, not over the spelling: the same body offered as base64 text and as raw
bytes is one request, so it is one key. A body given as text (a host's own convenience) is encoded to
UTF-8 first, so the two spellings of the same bytes agree.

### D3 — The runner reads the cache; a miss is an error

The runner asks the cache for each request the story makes. A hit continues the run; a miss is
reported with the request that was missing, and the run stops. The alternative — the runner fetching —
would make `up2 test` a network client, which no CLI in this repository is.

### D4 — The cache is a parameter, so the tests can point it elsewhere

`run_graph` takes the cache as an argument (defaulting to the package's cache directory). A test
therefore uses a temporary directory, and the CLI uses `.cache/requests/`.

### D5 — The answer is handed over as the cached `Response`

The cached entry carries `text` and `url`; the runner hands the story an object with those attributes,
which is what `py.getattr` reads. The story's own reading code does not change.

## Risks / Trade-offs

- **The cache is a fixture, not a contract.** It lives outside version control, so a fresh clone has
  no cached answers and the live samples cannot be regressed until someone fetches them once. That is
  the honest state of affairs: a committed fixture of a live site would rot.
- **A stale cache hides a changed site** — the point of a regression cache, and the escape hatch is
  deleting the cache directory (or `--no-cache` in the host).
- **A base64 body in chain data is unreadable.** It is still better than an unreadable binary, and a
  chain that posts binary is rare.
