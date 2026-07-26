"""Attribute mapping that records which source keys an adapter reads."""

from __future__ import annotations

from typing import Any


class TrackingAttrs(dict):
    """Record keys read through ``get``, subscription, or membership checks."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.accessed: set[str] = set()

    def get(self, key: str, default: Any = None) -> Any:
        self.accessed.add(key)
        return super().get(key, default)

    def __getitem__(self, key: str) -> Any:
        self.accessed.add(key)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            self.accessed.add(key)
        return super().__contains__(key)
