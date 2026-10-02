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
