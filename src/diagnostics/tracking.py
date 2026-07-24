"""Attribute dict that records which keys an adapter actually read.

Wrap an OTLP attribute dict before handing it to an adapter; after
normalization, ``set(self) - self.accessed`` is the set of source keys the
adapter never looked at — candidate fields being silently dropped.
"""

from __future__ import annotations

from typing import Any


class TrackingAttrs(dict):
    """dict wrapper that records looked-up keys.

    Only key *reads* are recorded (``get`` / ``[]`` / ``in``). Iteration and
    ``keys()`` are left untouched so the leftover diff can scan every key
    without polluting ``accessed``.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.accessed: set[str] = set()

    def get(self, key, default=None):
        self.accessed.add(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.accessed.add(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        self.accessed.add(key)
        return super().__contains__(key)
