"""The host type for `08-typed-invoice`: a validator, not a container."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Invoice:
    number: str
    total: float


TYPES = {"Invoice": Invoice}
