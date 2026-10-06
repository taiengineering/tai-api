"""Adapter registry — maps adapter_key → SourceAdapter instance.

Each AdapterRegistry instance owns its own state dict (no shared module global).
"""
from __future__ import annotations

from services.public_data_sync.adapters.base import SourceAdapter
from services.public_data_sync.errors import AdapterNotRegisteredError


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        self._adapters[adapter.adapter_key] = adapter

    def get(self, adapter_key: str) -> SourceAdapter:
        adapter = self._adapters.get(adapter_key)
        if adapter is None:
            raise AdapterNotRegisteredError(adapter_key)
        return adapter

    def registered_keys(self) -> list[str]:
        return list(self._adapters.keys())


adapter_registry = AdapterRegistry()

__all__ = ["SourceAdapter", "AdapterRegistry", "adapter_registry"]
