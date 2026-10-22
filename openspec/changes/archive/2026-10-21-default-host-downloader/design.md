# Design

## Context

See `proposal.md` — Why. The kernel never fetches anything: a story that produces a `Request` product
suspends the run, and the host answers (`03` §4.1, §5). The two committed samples each carry a host
script that does the fetching with `urllib`, and the scripts are near-copies of each other.

`morebuiltins` (the author's own package) has a request helper built on `urllib`; its parameter
handling (`params` / `headers` / `json` / `form` / `method` / `timeout` / `proxy` / `verify`) and its
response conveniences (`text` / `content` / `status_code` / `ok` / `json()`) are the right shape. It is
**not** adopted as a dependency: `uniparser2`'s runtime dependencies are empty by contract (`01` I1,
asserted in CI), so the downloader is written against the standard library and the helper is a
reference, not an import.

## Goals / Non-Goals

**Goals:**

- One obvious way to drive a story that fetches, with no third-party requirement.
- The same code path for the samples, for tests, and for a user's first project.
- A cache that makes a live sample replayable offline.

**Non-Goals:**

- An async downloader, a session with connection pooling, retries, robots, or rate limiting — those
  are a host's business (`03` §13 O6: what replays a run is the host's own log).
- A `httpx` / `requests` wrapper.

## Decisions

### D1 — The downloader lives in `uniparser2/host/`, a layer beside `core` and `cli`

The layering rule (`01` §1) puts IO in the layers beside `core`. `ops/` is the operator layer (pure
functions), so a downloader there would break the operator contract; `cli/` is the command entry, so
a library-level helper does not belong there either. `host/` is a thin package that depends on
`core` and does the IO the host is allowed to do.

### D2 — The response is a small dataclass with `text` and `url`

The samples read the answer with `["py","getattr","text"]` and `["py","getattr","url"]`, so those two
are the contract. The dataclass also carries `status_code` and `headers`, because a real client
exposes them and a host will want them — but the chain-facing minimum stays two.

### D3 — The request dictionary is the kernel's own shape

The kernel hands over a `Request` product: a mapping with `url`, `method`, `headers`, `timeout`,
`body`, `params`, `json` (`03` §4.1). The downloader takes **that mapping**, so a host does not
translate. Unknown keys are ignored; a missing `url` is an error.

### D4 — The cache key is the whole request, hashed

`method + "\n" + url + "\n" + sorted headers + "\n" + body` hashed with blake2b. The body is in the
key because two POSTs to one URL are two requests — the failure mode the downstream list recorded
("the same URL with a different body reused the first response"). The cache stores one file per key
under `.cache/requests/`, so it is inspectable and trivially deletable.

### D5 — The cache is opt-in and miss-tolerant

The host asks the cache first; a miss means "fetch it" (and the host may then store it). The cache
never fetches by itself and never returns an empty body for a miss — that would turn a missing entry
into a silently wrong answer.

### D6 — The samples' hosts shrink to the loop

A host script becomes: build the request, ask the cache, fetch on a miss, answer the effect. The
per-site logic (which URL, which selector) stays in the bundle; the fetching machinery is shared.

## Risks / Trade-offs

- **A cache can hide a changed site.** That is the point of a regression cache, but it also means a
  stale cache makes a "fixed" chain still look broken. Mitigation: the cache directory is not
  committed and is trivially cleared, and a `--no-cache` / `--refresh` switch is the escape hatch.
- **The standard library's `urllib` is not a modern client** (no connection pooling, no HTTP/2, and
  `urlopen` has quirks). It is the right trade for a zero-dependency default: a host that needs more
  brings its own client and ignores this one.
- **Redirects and cookies.** `urlopen` follows redirects by default but keeps no cookie jar. A host
  that needs cookies brings its own client. The downloader's contract says so.
