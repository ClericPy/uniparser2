"""Host recipe for `samples/books.toscrape.com`: the domain types plus the fetch loop.

A story is **library-independent data** (`03` §3.1): it names its types and its `call` target, and
the host owns both. This script is the smallest complete host for that sample — it registers the
two domain types, answers every suspension (`03` §5) with a stdlib `urllib` fetch, and prints the
exit product. Run it from the repository root:

    uv run python samples/books.toscrape.com/host.py

The three types the sample declares are registered here because the kernel refuses an unknown name
at the step that declares it (`UP2-E1011`, `03` §3.3), and a constructor is a **validator**: it
receives the product's own parts (`Cls(**payload)` for a dictionary, `Cls(*items)` for a list,
`03` §3.2) and the run keeps carrying JSON.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uniparser2 as up2

HERE = Path(__file__).resolve().parent
BUNDLE = HERE / "books" / "site.json"


@dataclass(slots=True)
class Book:
    """One book record; a field the kernel could not produce fails here, at that step."""

    url: str
    title: str
    price: str
    availability: str
    description: str


def ShelfPage(*links: dict[str, str]) -> list[dict[str, str]]:  # noqa: N802 - the name a step writes
    """One shelf page: the links the step's chain produced (`Cls(*items)`, `03` §3.2).

    A ``type`` is a **validator**, and what a list product carries is its items — so this one is a
    plain callable that proves the shape (every item carries the ``url`` the next step reads) and
    answers the same list the run carries on. The name is what the bundle declares, so it is the
    step's vocabulary rather than a Python naming choice.
    """
    if not all(isinstance(link, dict) and "url" in link for link in links):
        raise TypeError("a ShelfPage link must be an object carrying a url")
    return list(links)


@dataclass(slots=True)
class Answer:
    """The answer's shape is the **host's** choice (`03` §4.1).

    The story reads an answer with `py.getattr`, so this host answers an object carrying the body
    text and the final URL after redirects — the same two things an `httpx`/`requests` response
    already exposes, which is why a real client could be handed over unwrapped.
    """

    text: str
    url: str


def target_of(request: Mapping[str, Any]) -> str:
    """The URL to fetch: this host only speaks HTTP, so no other scheme is handed to ``urlopen``."""
    url = str(request["url"])
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"this host fetches http(s) only, got {url!r}")
    return url


def fetch(request: Mapping[str, Any]) -> Answer:
    """One request from the story; the answer is whatever this client returns (`03` §4.1)."""
    target = target_of(request)  # http(s) only, so `urlopen` never sees another scheme
    timeout = request.get("timeout", 30.0)
    with urllib.request.urlopen(target, timeout=timeout) as response:  # noqa: S310  # nosec B310 — target_of admits http(s) only
        return Answer(
            text=response.read().decode("utf-8", errors="replace"),
            url=response.geturl(),
        )


def store_books(**arguments: Any) -> dict[str, Any]:
    """The `call` target: a receipt that is JSON, never the records themselves (`03` §4.2).

    Its signature is exactly the step's ``with`` keys (`03` §4.2), so the host loop can hand the
    kernel's argument object straight over.
    """
    records = arguments["records"]
    if not isinstance(records, list):
        raise TypeError("store_books needs the step's records")
    return {"table": "books", "stored": len(records), "titles": [row["title"] for row in records]}


def request_of(task: Any) -> Mapping[str, Any]:
    """One task the host must send: the kernel hands over request objects (`03` §4.1)."""
    if not isinstance(task, Mapping):
        raise TypeError(f"a task must be a request object, got {type(task).__name__}")
    return task


def call_arguments(arguments: Any) -> Mapping[str, Any]:
    """A `call` step's arguments: the kernel hands over the step's ``with`` object (`03` §4.2)."""
    if not isinstance(arguments, Mapping):
        raise TypeError(
            f"a call must carry its arguments as an object, got {type(arguments).__name__}"
        )
    return arguments


def run_story(bundle: dict[str, Any], seed: str) -> Any:
    """The host loop of `03` §5: read the effect, answer it, repeat until the run is done.

    The kernel's effect is a tagged tuple: a ``request`` carries one task, a ``batch`` a list of
    them, and ``call`` the arguments of a host function.
    """
    run = up2.start(bundle, seed)
    while True:
        effect = run.next()
        if effect[0] == "done":
            return effect[1]
        kind, payload, *rest = effect
        if kind == "request":
            run.send(fetch(request_of(payload)))
        elif kind == "batch":
            if not isinstance(payload, list):
                raise TypeError(f"a batch must be a list of tasks, got {type(payload).__name__}")
            run.send([fetch(request_of(task)) for task in payload])
        else:
            run.send(store_books(**call_arguments(rest[0])))


def main() -> int:
    up2.register_type("ShelfPage", ShelfPage)
    up2.register_type("Book", Book)
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    product = run_story(bundle, bundle["globals"]["base_url"])
    print(json.dumps(product, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
