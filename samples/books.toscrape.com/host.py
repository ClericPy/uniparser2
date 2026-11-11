"""Host recipe for `samples/books.toscrape.com`: the domain type, `fetch`, and the store function.

A story is **library-independent data** (`03` §3.1): it names its types and its host functions, and
the host owns both. This script is the smallest complete host for that sample — it registers the
`Book` type, answers `fetch` with the package's default downloader (through the request cache), and
prints the node's product. Run it from the repository root:

    uv run python samples/books.toscrape.com/host.py                  # seeds the site root
    uv run python samples/books.toscrape.com/host.py <seed URL>       # or any page of the site
    uv run python samples/books.toscrape.com/host.py --no-cache       # ignore the cached answers

The `Book` type is registered here because the story's `["type","Book"]` stage refuses an unknown
name (`UP2-E1011`, `03` §3.3), and a constructor is a **validator**: it receives the product's own
parts (`Cls(**payload)`), and the run keeps carrying JSON.

The fetching is the package's default (`uniparser2.net`): `fetch` accepts a URL string or a request
object and answers a response carrying `text`, `url` and `status_code` — the ones the story reads
with `py.getattr`. Every answer is cached under `.cache/requests/` (never committed), so a second
run replays it instead of the network.
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
    """One book record; a field the kernel could not produce fails at the `type` stage."""

    url: str
    title: str
    price: str
    availability: str
    description: str


def store_books(records: Any) -> dict[str, Any]:
    """The `store` node's host function: a JSON receipt, never the records themselves."""
    if not isinstance(records, list):
        raise TypeError(f"store_books needs the list of records, got {type(records).__name__}")
    return {"table": "books", "stored": len(records), "titles": [row["title"] for row in records]}


def run_story(bundle: dict[str, Any], seed: str, *, cache: RequestCache | None) -> Any:
    """Run the story synchronously: `fetch` and `store_books` are the only host functions."""

    def cached_fetch(request: Any) -> Any:
        if not isinstance(request, Mapping):
            raise TypeError(f"fetch needs a request object, got {type(request).__name__}")
        if cache is not None:
            cached = cache.get(request)
            if cached is not None:
                return cached
        response = fetch(request)
        if cache is not None:
            cache.put(request, response)
        return response

    return up2.run(
        bundle,
        input=seed,
        udfs={"fetch": cached_fetch, "store_books": store_books},
    )


up2.register_type("Book", Book)
"""The domain type, registered at import time: the kernel refuses an unknown name (`03` §3.3)."""


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
