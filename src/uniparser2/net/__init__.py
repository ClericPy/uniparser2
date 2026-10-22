"""The network side of a run: the things a caller needs to drive a story that fetches (`03` §4, §5).

The kernel performs no IO: a story that produces a ``Request`` product suspends the run, and the
host answers it (`03` §4.1, §5). This package is that host side -- a **default** downloader and a
request cache -- so that driving a story that fetches is a few lines rather than a networking
library. A host that needs sessions, retries, cookies or rate limiting brings its own client and
ignores these; what replays a run is the host's own log (`03` §13 O6).

The runtime dependencies of the whole package are empty by contract (`01` I1), so the downloader is
written against the standard library.
"""

from __future__ import annotations

from .cache import CACHE_DIR, RequestCache, request_key
from .download import DEFAULT_TIMEOUT, Response, decode_body, encode_body, fetch

__all__ = [
    "CACHE_DIR",
    "DEFAULT_TIMEOUT",
    "RequestCache",
    "Response",
    "decode_body",
    "encode_body",
    "fetch",
    "request_key",
]
