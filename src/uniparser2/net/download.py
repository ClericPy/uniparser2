"""The default synchronous downloader (change `default-host-downloader`).

The kernel never fetches anything: a story that produces a ``Request`` product suspends the run, and
the **host** answers (`03` §4.1, §5). This module is the host side of that answer, so it may do IO
-- it lives outside ``core/``, which stays pure (`01`` I1, N1).

The request is the kernel's own shape: the ``Request`` product's mapping (``url`` / ``method`` /
``headers`` / ``timeout`` / ``body`` / ``params`` / ``json``, ``03`` §4.1). The response is the
shape the sample hosts read with ``py.getattr``: ``text`` and ``url``.

**Standard library only.** The runtime dependencies of this package are empty by contract, so the
downloader is written against ``urllib``; a host that wants sessions, retries, cookies or rate
limiting brings its own client (see ``03`` §13 O6: what replays a run is the host's own log).
"""

from __future__ import annotations

import base64
import binascii
import json as _json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT: Final = 30.0
"""The seconds a request may take when the request does not say (``03`` §4.1's default)."""

_USER_AGENT: Final = "uniparser2 (+https://github.com/ClericPy/uniparser2)"
"""The default ``User-Agent``: a downloader that identifies itself, and names the package."""


@dataclass(frozen=True, slots=True)
class Response:
    """What a host answers a suspension with: the body and where it came from.

    ``text`` is the decoded body and ``url`` the final URL after redirects -- the two the sample
    hosts read with ``["py","getattr","text"]`` and ``["py","getattr","url"]``. ``status_code`` and
    ``headers`` are there for a host that needs them; the chain-facing minimum is the first two.
    """

    text: str
    url: str
    status_code: int = 200
    headers: Mapping[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        """The body parsed as JSON."""
        return _json.loads(self.text)


def fetch(request: Mapping[str, Any]) -> Response:
    """Send one request and answer with the response.

    The request is a request object with ``url`` (required), ``method`` (default ``GET``),
    ``headers``, ``timeout``, ``body``, ``params`` and ``json``. An unknown key is ignored.

    A request that cannot be sent raises: an unreachable host, a timeout, a refused scheme. A host
    that needs to tell "no answer" from "an empty page" has to see the difference.
    """
    url = _url_of(request)
    method = str(request.get("method") or "GET").upper()
    headers = {str(key): str(value) for key, value in _mapping_of(request, "headers").items()}
    headers.setdefault("User-Agent", _USER_AGENT)
    timeout = _timeout_of(request)
    data = _body_of(request, headers)
    target = with_params(url, _mapping_of(request, "params"))
    request_object = Request(target, data=data, headers=headers, method=method)  # noqa: S310
    try:
        # `_url_of` admits http(s) only, so `urlopen` never sees another scheme.
        with urlopen(request_object, timeout=timeout) as response:  # noqa: S310
            body = response.read()
            return Response(
                text=_decode(body, response.headers.get_content_charset()),
                url=response.geturl(),
                status_code=int(response.status),
                headers=dict(response.headers.items()),
            )
    except HTTPError as exc:
        # An HTTP error status is still an answer: the body is what the server said.
        body = exc.read()
        return Response(
            text=_decode(body, exc.headers.get_content_charset() if exc.headers else None),
            url=getattr(exc, "url", None) or target,
            status_code=int(exc.code),
            headers=dict(exc.headers.items()) if exc.headers else {},
        )


def _url_of(request: Mapping[str, Any]) -> str:
    """The target URL, and a check that it is HTTP(S): the downloader speaks no other scheme."""
    raw = request.get("url")
    if not isinstance(raw, str) or not raw:
        raise ValueError("a request needs a `url`")
    scheme = urlparse(raw).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"this downloader speaks http(s) only, got {raw!r}")
    return raw


def _mapping_of(request: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = request.get(key)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"the request's {key!r} must be an object, got {type(value).__name__}")
    return value


def _timeout_of(request: Mapping[str, Any]) -> float:
    raw = request.get("timeout")
    if raw is None:
        return DEFAULT_TIMEOUT
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"the request's timeout must be a number, got {raw!r}") from exc


def _body_of(request: Mapping[str, Any], headers: dict[str, str]) -> bytes | None:
    """The request's body: ``body`` as base64 text, ``json`` as JSON, or nothing.

    The body is **binary**, and the request dictionary is JSON throughout (it lives in chain data,
    in a cache key and in a journal), so ``body`` carries base64 **text** and is decoded here.
    Raw bytes are still accepted — a host's own call, not chain data — and are encoded on the way
    into the cache key.
    """
    payload = request.get("json")
    if payload is not None:
        headers.setdefault("Content-Type", "application/json")
        return _json.dumps(payload, ensure_ascii=False).encode("utf-8")
    body = request.get("body")
    if body is None:
        return None
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return decode_body(body)
    raise TypeError(f"the request's body must be base64 text or bytes, got {type(body).__name__}")


def decode_body(body: str) -> bytes:
    """The bytes a base64 body carries.

    A body that is not valid base64 is an error the caller can report: sending the text as-is would
    be a silently different request.
    """
    try:
        return base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"the request's body is not valid base64: {exc}") from exc


def encode_body(body: bytes) -> str:
    """The base64 text a body is carried as."""
    return base64.b64encode(body).decode("ascii")


def with_params(url: str, params: Mapping[str, Any]) -> str:
    """Append the query parameters, if the request carries any.

    The parameters are sorted by name, so the same parameter set is the same query string whatever
    order it was written in -- and the cache, whose key is over the URL the request is **sent** to,
    agrees with the downloader.
    """
    if not params:
        return url
    query = urlencode({str(key): str(value) for key, value in sorted(params.items())})
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query}"


def _decode(body: bytes, charset: str | None) -> str:
    """The body as text: the declared charset, or UTF-8 with the undecodable bytes replaced."""
    return body.decode(charset or "utf-8", errors="replace")


__all__ = [
    "DEFAULT_TIMEOUT",
    "Response",
    "decode_body",
    "encode_body",
    "fetch",
    "with_params",
]
