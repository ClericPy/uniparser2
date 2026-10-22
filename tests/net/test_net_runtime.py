"""The network-side downloader and the request cache (change `default-host-downloader`).

The downloader is tested against a **local** HTTP server, so the suite never touches the network.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from uniparser2.net import RequestCache, Response, encode_body, fetch, request_key


class _Handler(BaseHTTPRequestHandler):
    """A tiny server: echoes what it was asked for, so a case can assert on the request."""

    seen: ClassVar[list[dict[str, Any]]] = []

    def do_GET(self) -> None:
        type(self).seen.append({"method": "GET", "path": self.path, "headers": dict(self.headers)})
        body = b"<html><h1>page</h1></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        payload = self.rfile.read(length)
        type(self).seen.append(
            {"method": "POST", "path": self.path, "body": payload.decode("utf-8")}
        )
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the stdlib's spelling
        """Keep the test output clean."""


@pytest.fixture
def server() -> Iterator[str]:
    """A local HTTP server; the fixture yields its base URL."""
    _Handler.seen = []
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------------------------------------------------------- the downloader


def test_a_get_request_answers_with_the_body_and_the_url(server: str) -> None:
    response = fetch({"url": f"{server}/page"})
    assert response.text == "<html><h1>page</h1></html>"
    assert response.url == f"{server}/page"
    assert response.status_code == 200


def test_a_header_is_sent(server: str) -> None:
    fetch({"url": f"{server}/page", "headers": {"X-Test": "1"}})
    assert _Handler.seen[0]["headers"].get("X-Test") == "1"


def test_a_user_agent_is_sent_by_default(server: str) -> None:
    fetch({"url": f"{server}/page"})
    assert "uniparser2" in _Handler.seen[0]["headers"].get("User-Agent", "")


def test_query_parameters_are_appended(server: str) -> None:
    fetch({"url": f"{server}/page", "params": {"q": "x"}})
    assert _Handler.seen[0]["path"] == "/page?q=x"


def test_a_base64_body_is_sent_decoded(server: str) -> None:
    """The body is binary, so the request carries it as base64 text."""
    response = fetch({"url": f"{server}/page", "method": "POST", "body": encode_body(b"hello")})
    assert _Handler.seen[0]["body"] == "hello"
    assert response.status_code == 201
    assert response.json() == {"ok": True}


def test_a_body_that_is_not_base64_is_an_error() -> None:
    with pytest.raises(ValueError, match="base64"):
        fetch({"url": "http://x/", "method": "POST", "body": "not base64!!"})


def test_raw_bytes_are_still_accepted(server: str) -> None:
    """A host's own call may hand over bytes; the chain data may not."""
    fetch({"url": f"{server}/page", "method": "POST", "body": b"hello"})
    assert _Handler.seen[0]["body"] == "hello"


def test_a_json_body_is_sent_as_json(server: str) -> None:
    fetch({"url": f"{server}/page", "method": "POST", "json": {"a": 1}})
    assert _Handler.seen[0]["body"] == '{"a": 1}'


def test_a_json_body_wins_over_a_base64_body(server: str) -> None:
    fetch({"url": f"{server}/page", "method": "POST", "body": encode_body(b"x"), "json": {"a": 1}})
    assert _Handler.seen[0]["body"] == '{"a": 1}'


def test_a_refused_scheme_is_an_error() -> None:
    with pytest.raises(ValueError, match="http"):
        fetch({"url": "file:///etc/passwd"})


def test_a_missing_url_is_an_error() -> None:
    with pytest.raises(ValueError, match="url"):
        fetch({"method": "GET"})


def test_a_non_mapping_header_is_an_error() -> None:
    with pytest.raises(TypeError, match="headers"):
        fetch({"url": "http://x/", "headers": "nope"})


def test_an_unreachable_host_raises() -> None:
    with pytest.raises(OSError):
        fetch({"url": "http://127.0.0.1:1/", "timeout": 1.0})


# ---------------------------------------------------------------- the cache


def test_the_key_covers_the_whole_request() -> None:
    base = {"url": "http://x/", "method": "GET"}
    assert request_key(base) == request_key(dict(base))
    assert request_key(base) != request_key({**base, "method": "POST"})
    assert request_key(base) != request_key({**base, "url": "http://y/"})


def test_the_key_covers_the_body() -> None:
    """Two POSTs to one URL are two requests."""
    base = {"url": "http://x/", "method": "POST"}
    assert request_key({**base, "body": encode_body(b"a")}) != request_key(
        {**base, "body": encode_body(b"b")}
    )


def test_the_key_is_over_the_decoded_body() -> None:
    """The same bytes written two ways are one request, hence one key."""
    base = {"url": "http://x/", "method": "POST"}
    assert request_key({**base, "body": encode_body(b"hello")}) == request_key(
        {**base, "body": b"hello"}
    )


def test_the_key_covers_the_query_parameters() -> None:
    """Two pages of one URL are two requests: reusing the first answer is a silent wrong answer."""
    base = {"url": "http://x/list"}
    assert request_key({**base, "params": {"page": 1}}) != request_key(
        {**base, "params": {"page": 2}}
    )


def test_the_key_is_over_the_url_the_request_is_sent_to() -> None:
    """The parameters are folded into the URL, so the two spellings are one request."""
    with_params = {"url": "http://x/list", "params": {"a": 1, "b": 2}}
    in_the_url = {"url": "http://x/list?a=1&b=2"}
    assert request_key(with_params) == request_key(in_the_url)


def test_the_key_does_not_depend_on_the_order() -> None:
    """The same request written in another order is the same request."""
    assert request_key({"url": "http://x/", "headers": {"A": "1", "B": "2"}}) == request_key(
        {"url": "http://x/", "headers": {"B": "2", "A": "1"}}
    )
    assert request_key({"url": "http://x/", "params": {"a": 1, "b": 2}}) == request_key(
        {"url": "http://x/", "params": {"b": 2, "a": 1}}
    )


def test_two_pages_are_two_entries(tmp_path: Path) -> None:
    """The regression this key shape exists for: page 1 must not answer page 2."""
    cache = RequestCache(tmp_path)
    first = {"url": "http://x/list", "params": {"page": 1}}
    second = {"url": "http://x/list", "params": {"page": 2}}
    cache.put(first, Response(text="PAGE ONE", url="http://x/list?page=1"))
    cache.put(second, Response(text="PAGE TWO", url="http://x/list?page=2"))
    one = cache.get(first)
    two = cache.get(second)
    assert one is not None
    assert one.text == "PAGE ONE"
    assert two is not None
    assert two.text == "PAGE TWO"


def test_a_miss_is_a_miss(tmp_path: Path) -> None:
    cache = RequestCache(tmp_path)
    assert cache.get({"url": "http://x/"}) is None


def test_a_second_ask_replays_the_answer(tmp_path: Path) -> None:
    cache = RequestCache(tmp_path)
    request = {"url": "http://x/page"}
    cache.put(request, Response(text="hello", url="http://x/page"))
    found = cache.get(request)
    assert found is not None
    assert found.text == "hello"
    assert found.url == "http://x/page"


def test_the_cache_keeps_the_headers_and_the_status(tmp_path: Path) -> None:
    cache = RequestCache(tmp_path)
    request = {"url": "http://x/page"}
    cache.put(request, Response(text="hi", url="u", status_code=201, headers={"A": "b"}))
    found = cache.get(request)
    assert found is not None
    assert found.status_code == 201
    assert found.headers == {"A": "b"}


def test_two_different_bodies_are_two_entries(tmp_path: Path) -> None:
    cache = RequestCache(tmp_path)
    first = {"url": "http://x/", "method": "POST", "body": encode_body(b"a")}
    second = {"url": "http://x/", "method": "POST", "body": encode_body(b"b")}
    cache.put(first, Response(text="A", url="u"))
    cache.put(second, Response(text="B", url="u"))
    first_found = cache.get(first)
    second_found = cache.get(second)
    assert first_found is not None and first_found.text == "A"
    assert second_found is not None and second_found.text == "B"


def test_a_broken_entry_is_a_miss(tmp_path: Path) -> None:
    """An entry that cannot be read must not answer with an empty body."""
    cache = RequestCache(tmp_path)
    request = {"url": "http://x/page"}
    cache.put(request, Response(text="hello", url="u"))
    cache.path_for(request).write_text("{not json", encoding="utf-8")
    assert cache.get(request) is None


def test_clear_removes_every_entry(tmp_path: Path) -> None:
    cache = RequestCache(tmp_path)
    cache.put({"url": "http://x/"}, Response(text="a", url="u"))
    assert cache.clear() == 1
    assert cache.get({"url": "http://x/"}) is None
    assert cache.clear() == 0


def test_the_cache_writes_one_file_per_request(tmp_path: Path) -> None:
    cache = RequestCache(tmp_path)
    request = {"url": "http://x/"}
    cache.put(request, Response(text="a", url="u"))
    written = cache.path_for(request)
    assert written.exists()
    assert written.suffix == ".json"
    assert json.loads(written.read_text(encoding="utf-8"))["text"] == "a"
