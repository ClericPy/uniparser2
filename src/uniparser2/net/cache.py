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

import base64
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from .download import Response, decode_body
from .download import with_params as _with_params

CACHE_DIR: Final = Path(".cache") / "requests"
"""Where the cached answers live: a local directory, never committed.

The path is **relative to the working directory**, so the cache belongs to the project the command
runs in. A caller that wants one place for several projects passes an absolute root to
:class:`RequestCache`.
"""

DIGEST_SIZE: Final = 16
"""The digest width in bytes: 128 bits keep an accidental collision out of reach."""


def request_key(request: Mapping[str, Any]) -> str:
    """The cache key of one request: a digest of the **normalized** request.

    The request is normalized first -- the query parameters folded into the URL, the body decoded
    to its bytes -- and the result is written as JSON with sorted keys, so the key is a digest of
    what the request actually *is* rather than of how it was spelled. Two spellings of the same
    request (a body as base64 text and as raw bytes, a parameter order that differs) are one
    request, hence one key; two different requests (``POST`` and ``GET`` on one URL, ``?page=1``
    and ``?page=2``) are two keys, because reusing the first answer for the second is a silent
    wrong answer.
    """
    normalized = _normalized(request)
    blob = json.dumps(normalized, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.blake2b(blob, digest_size=DIGEST_SIZE).hexdigest()


def _normalized(request: Mapping[str, Any]) -> dict[str, Any]:
    """The request as it will be sent: the URL with its query, the body as bytes, the rest as is."""
    params = request.get("params") or {}
    headers = request.get("headers") or {}
    normalized: dict[str, Any] = {
        "method": str(request.get("method") or "GET").upper(),
        "url": _with_params(str(request.get("url") or ""), params),
        "headers": {str(key): str(value) for key, value in headers.items()},
    }
    body = _body_bytes(request)
    if body:
        normalized["body"] = base64.b64encode(body).decode("ascii")
    return normalized


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
        answer, because an empty answer would look like a successful fetch of nothing. That includes
        an entry whose fields have the wrong type (a hand-edited file, a partial write), not only
        one with broken JSON syntax.
        """
        path = self.path_for(request)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or "text" not in raw:
                return None
            return Response(
                text=str(raw["text"]),
                url=str(raw.get("url", "")),
                status_code=int(raw.get("status_code", 200)),
                headers={str(key): str(value) for key, value in (raw.get("headers") or {}).items()},
            )
        except (OSError, ValueError, TypeError, AttributeError):
            return None

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
