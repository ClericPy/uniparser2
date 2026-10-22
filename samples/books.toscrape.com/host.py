"""Host recipe for `samples/books.toscrape.com`: the domain types plus the fetch loop.

A story is **library-independent data** (`03` §3.1): it names its types and its `call` target, and
the host owns both. This script is the smallest complete host for that sample — it registers the
two domain types, answers every suspension (`03` §5) with the package's default downloader, and
prints the exit product. Run it from the repository root:

    uv run python samples/books.toscrape.com/host.py                  # seeds the site root
    uv run python samples/books.toscrape.com/host.py <seed URL>       # or any page of the site
    uv run python samples/books.toscrape.com/host.py --no-cache       # ignore the cached answers

The three types the sample declares are registered here because the kernel refuses an unknown name
at the step that declares it (`UP2-E1011`, `03` §3.3), and a constructor is a **validator**: it
receives the product's own parts (`Cls(**payload)` for a dictionary, `Cls(*items)` for a list,
`03` §3.2) and the run keeps carrying JSON.

The fetching is the package's default (`uniparser2.net`): the request dictionary the kernel
hands over is the request, and the answer carries `text` and `url` — the two the story reads
with `py.getattr`. Every answer is cached under `.cache/requests/` (never committed), so a
second run replays it instead of the network.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uniparser2 as up2
from uniparser2.net import RequestCache, fetch

HERE = Path(__file__).resolve().parent
BUNDLE = HERE / "books" / "site.json"
SITE_ROOT = "https://books.toscrape.com/"
"""Where this site's crawl starts, and the default seed: `globals.base_url` is the urljoin base."""


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


def store_books(**arguments: Any) -> dict[str, Any]:
    """The `call` target: a receipt that is JSON, never the records themselves (`03` §4.2).

    Its signature is exactly the step's ``args`` keys (`03` §4.2), so the host loop can hand the
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


def run_story(bundle: dict[str, Any], seed: str, *, cache: RequestCache | None) -> Any:
    """The host loop of `03` §5: read the effect, answer it, repeat until the run is done.

    The kernel's effect is a tagged tuple: a ``request`` carries one task, a ``batch`` a list of
    them, and a ``call`` the arguments of a host function.
    """
    run = up2.start(bundle, seed)
    while True:
        effect = run.go()
        if effect[0] == "done":
            return effect[1]
        kind, payload, *rest = effect
        if kind == "request":
            run.feed(answer(request_of(payload), cache))
        elif kind == "batch":
            if not isinstance(payload, list):
                raise TypeError(f"a batch must be a list of tasks, got {type(payload).__name__}")
            run.feed([answer(request_of(task), cache) for task in payload])
        else:
            run.feed(store_books(**call_arguments(rest[0])))


def answer(request: Mapping[str, Any], cache: RequestCache | None) -> Any:
    """One request answered: from the cache when it is there, from the network otherwise."""
    if cache is not None:
        cached = cache.get(request)
        if cached is not None:
            return cached
    response = fetch(request)
    if cache is not None:
        cache.put(request, response)
    return response


up2.register_type("ShelfPage", ShelfPage)
up2.register_type("Book", Book)
"""The domain types, registered at import time: the kernel refuses an unknown name (`03` §3.3)."""


def main() -> int:
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    # The seed is the caller's, not `globals.base_url`: `base_url` is the urljoin base of the
    # chains, while the seed is the URL the run starts at (the site root unless one is passed).
    arguments = [item for item in sys.argv[1:] if not item.startswith("--")]
    use_cache = "--no-cache" not in sys.argv[1:]
    seed = arguments[0] if arguments else SITE_ROOT
    product = run_story(bundle, seed, cache=RequestCache() if use_cache else None)
    print(json.dumps(product, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
