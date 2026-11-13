"""The host type for `08-typed-invoice`: a constructor, so its instance flows mid-chain.

`["type","Invoice"]` builds it from the parsed JSON; the stages after it read the instance's fields
and build a JSON record; the run would also accept the instance itself as the product (`03` §3.3).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Invoice:
    number: str
    total: float


TYPES = {"Invoice": Invoice}
