"""Attribute mapping that records which source keys an adapter reads."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar


_T = TypeVar("_T")


class TrackingAttrs(dict):
    """Record keys read through ``get``, subscription, or membership checks."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.accessed: set[str] = set()
        self.mapping_results: dict[str, Any] = {}
        self.mapping_reasons: dict[str, str] = {}
        self._mapping_accesses: set[str] | None = None

    def map(
        self,
        target: str,
        resolver: Callable[[], _T],
        *,
        required: bool = True,
    ) -> _T:
        """Resolve one target field and retain its pre-fallback result."""
        previous_mapping_accesses = self._mapping_accesses
        mapping_accesses: set[str] = set()
        self._mapping_accesses = mapping_accesses
        try:
            value = resolver()
        finally:
            self._mapping_accesses = previous_mapping_accesses

        present_keys = [
            key for key in mapping_accesses if dict.__contains__(self, key)
        ]
        if required or value is not None or present_keys:
            self.mapping_results[target] = value

        if value is None and target in self.mapping_results:
            present_values = [
                dict.__getitem__(self, key) for key in present_keys
            ]
            if not present_keys:
                reason = "source_key_missing"
            elif all(value is None for value in present_values):
                reason = "source_value_null"
            else:
                reason = "conversion_failed"
            self.mapping_reasons[target] = reason

        return value

    def get(self, key: str, default: Any = None) -> Any:
        self.accessed.add(key)
        if self._mapping_accesses is not None:
            self._mapping_accesses.add(key)
        return super().get(key, default)

    def __getitem__(self, key: str) -> Any:
        self.accessed.add(key)
        if self._mapping_accesses is not None:
            self._mapping_accesses.add(key)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            self.accessed.add(key)
            if self._mapping_accesses is not None:
                self._mapping_accesses.add(key)
        return super().__contains__(key)
