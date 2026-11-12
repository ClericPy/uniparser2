"""The host `udf` for `09-udf-slug`: the chain carries only the name."""

from __future__ import annotations


def slugify(value: str) -> str:
    return str(value).strip().lower().replace(" ", "-")


UDOFS = {"slugify": slugify}
