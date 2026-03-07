"""Shared Hatchet client — lazy-initialized so tests can import agents without a live token."""

from __future__ import annotations

from functools import lru_cache

from hatchet_sdk import Hatchet


@lru_cache(maxsize=1)
def get_hatchet() -> Hatchet:
    return Hatchet()
