# Allow host objects as values

## Why

A run's values may be host objects. A fetch returns whatever the host's HTTP client returns (an
`httpx.Response`, a `requests.Response`, or any object), and `selectolax`'s node handles are objects too.
Today `Response` is defined as a four-key dictionary, only `Opaque` (DOM handles) may flow, and a host
object is rejected at the boundary (`UP2-E2009`) — so a story must convert what it was just handed, losing
the headers' case-insensitivity, `.json()`, `.request.url`, the encoding and the timing.

The kernel already carries third-party objects (a DOM handle is one), so the rule was narrower than the
implementation and was stated too strongly ("host objects never enter a chain").

## What Changes

- **A value that flows may be an object**, using the mechanism `Opaque` already establishes.
  **Step products must still be JSON**: the host-registered type constructor converts at the step boundary,
  `export.pack` still rejects non-JSON, and the single exit therefore still holds.
- **`Response` stops being a type.** The answer to a request is whatever the host `send`s back, unwrapped;
  the `Response` key table and the `Response` built-in type are deleted. `Request` keeps its neutral
  structure (a story's outgoing intent must be library-independent; an incoming answer need not be).
- **New action `py.getattr`** — read an attribute of the value flowing in (not of a stored `ctx` value).
  An absent attribute fails with the exception class in `reason`; an attribute that is **callable** fails
  with a pointer at the operator or `udf` to use instead, so a method never turns into a value silently.
- **Reference resolution walks objects with `getattr`**, and dicts/lists with `getitem`
  (`$in.request.url`, `$resp.headers`).
- Trace keeps a preview (type name plus truncated text); snapshots compare products, which stay JSON.

## Impact

- Kernel: `core/values.py` (preview and type name for host objects), `core/refs.py` (attribute walking),
  the boundary rule and the message of `UP2-E2009`.
- New action `py.getattr`: registry, conformance case, `docs/operator-reference.md`, `up2 ops` catalogue,
  `tools/demo_report.py`.
- Docs: `03` §3.1 and §3.3 (the type list and the "host objects never enter a chain" sentence), §4.1 (the
  `Response` table is replaced by "the answer is whatever came back, read with `getattr`/`getitem`"),
  §11's examples; `01` §3.1; `02` §6.
- Any story that writes `out: "Response"` or converts a response to a dict.
