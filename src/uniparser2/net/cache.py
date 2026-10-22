"""The host-side request cache (change `default-host-downloader`).

What makes a live sample testable offline: the answers a host fetched are kept on disk, keyed by the
**whole request**, and a later run replays them instead of the network.

The cache lives under ``.cache/requests/`` -- a local, git-ignored directory (``05`` §3 puts the
committed samples in the repository; this is the opposite: runtime state, never committed). The key
is a digest of the method, the URL, the sorted headers and the body, so two different requests never
share an answer (``POST`` and ``GET`` on one URL are two requests).

A **miss is a miss**: the cache never answers with an empty body for a request it has not seen, and
it never fetches by itself. The host decides what a miss means.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from .download import Response, decode_body

CACHE_DIR: Final = Path(".cache") / "requests"
"""Where the cached answers live: a local directory, never committed."""

DIGEST_SIZE: Final = 16
"""The digest width in bytes: 128 bits keep an accidental collision out of reach."""


def request_key(request: Mapping[str, Any]) -> str:
    """The cache key of one request: a digest of the method, the URL, the headers and the body.

    The body is part of the key because two POSTs to one URL are two requests -- reusing the first
    answer for the second is a silent wrong answer. The key is over the **decoded** bytes, so the
    same body written as base64 text and offered as raw bytes is one request, hence one key.
    """
    method = str(request.get("method") or "GET").upper()
    url = str(request.get("url") or "")
    headers = request.get("headers") or {}
    header_text = "\n".join(f"{key}={value}" for key, value in sorted(headers.items()))
    body = _body_bytes(request)
    blob = b"\n".join(
        [method.encode("utf-8"), url.encode("utf-8"), header_text.encode("utf-8"), body]
    )
    return hashlib.blake2b(blob, digest_size=DIGEST_SIZE).hexdigest()


def _body_bytes(request: Mapping[str, Any]) -> bytes:
    """The request's body as bytes: the base64 text decoded, the JSON value, or nothing."""
    body = request.get("body")
    if body is not None:
        if isinstance(body, bytes):
            return body
        return decode_body(str(body))
    payload = request.get("json")
    if payload is None:
        return b""
    return json.dumps(payload, sort_keys=True, default=str).encode("utf-8")


class RequestCache:
    """The cached answers, on disk.

    One file per key under the cache directory, so the cache is inspectable and a single entry
    can be deleted. The directory is created on the first write -- a host that never caches writes
    nothing.
    """

    __slots__ = ("_root",)

    def __init__(self, root: Path | str = CACHE_DIR) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        """The directory the entries live in."""
        return self._root

    def path_for(self, request: Mapping[str, Any]) -> Path:
        """Where one request's entry lives."""
        return self._root / f"{request_key(request)}.json"

    def get(self, request: Mapping[str, Any]) -> Response | None:
        """The cached answer for one request, or ``None`` for a miss.

        A miss is a miss: an entry that cannot be read is treated as absent rather than as an empty
        answer, because an empty answer would look like a successful fetch of nothing.
        """
        path = self.path_for(request)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict) or "text" not in raw:
            return None
        return Response(
            text=str(raw["text"]),
            url=str(raw.get("url", "")),
            status_code=int(raw.get("status_code", 200)),
            headers={str(key): str(value) for key, value in (raw.get("headers") or {}).items()},
        )

    def put(self, request: Mapping[str, Any], response: Response) -> None:
        """Store one answer, so the next run replays it."""
        self._root.mkdir(parents=True, exist_ok=True)
        payload = {
            "text": response.text,
            "url": response.url,
            "status_code": response.status_code,
            "headers": {str(key): str(value) for key, value in response.headers.items()},
        }
        path = self.path_for(request)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    def clear(self) -> int:
        """Drop every cached answer; return how many were removed."""
        if not self._root.is_dir():
            return 0
        entries = list(self._root.glob("*.json"))
        for entry in entries:
            entry.unlink()
        return len(entries)


__all__ = [
    "CACHE_DIR",
    "DIGEST_SIZE",
    "RequestCache",
    "request_key",
]
