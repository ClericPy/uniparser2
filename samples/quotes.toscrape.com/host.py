"""Host recipe for `samples/quotes.toscrape.com`: the domain type plus the fetch loop.

A story is **library-independent data** (`03` §3.1): it names its types and its `call` target, and
the host owns both. This script is the smallest complete host for that sample — it registers the
`Author` type, answers every suspension (`03` §5) with a stdlib `urllib` fetch, and prints the exit
product. Run it from the repository root:

    uv run python samples/quotes.toscrape.com/host.py

`Author` is registered here because the kernel refuses an unknown name at the step that declares it
(`UP2-E1011`, `03` §3.3), and a constructor is a **validator**: it receives the product's own parts
(`Cls(**payload)` for a dictionary, `03` §3.2) and the run keeps carrying JSON.
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
BUNDLE = HERE / "quotes" / "site.json"


@dataclass(slots=True)
class Author:
    """One author record; a field the kernel could not produce fails here, at that step."""

    url: str
    name: str
    born_date: str
    born_location: str
    description: str


def request_of(task: Any) -> Mapping[str, Any]:
    """One task the host must send: the kernel hands over request objects (`03` §4.1)."""
    if not isinstance(task, Mapping):
        raise TypeError(f"a task must be a request object, got {type(task).__name__}")
    return task


def run_story(bundle: dict[str, Any], seed: str) -> Any:
    """The host loop of `03` §5: read the effect, answer it, repeat until the run is done.

    The kernel's effect is a tagged tuple: a ``request`` carries one task and a ``batch`` a list of
    them. This story declares no ``call``, so any other effect kind is a host bug.
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
            raise RuntimeError(f"this story declares no host function, got {kind}: {rest!r}")


def main() -> int:
    up2.register_type("Author", Author)
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    product = run_story(bundle, bundle["globals"]["base_url"])
    print(json.dumps(product, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
