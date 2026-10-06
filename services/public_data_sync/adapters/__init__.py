"""Adapter registry — maps source_id → SourceAdapter instance."""
from __future__ import annotations

from services.public_data_sync.adapters.base import SourceAdapter
from services.public_data_sync.errors import AdapterNotRegisteredError

_adapters: dict[str, SourceAdapter] = {}


class AdapterRegistry:
    def register(self, adapter: SourceAdapter) -> None:
        _adapters[adapter.source_id] = adapter

    def get(self, source_id: str) -> SourceAdapter:
        adapter = _adapters.get(source_id)
        if adapter is None:
            raise AdapterNotRegisteredError(source_id)
        return adapter

    def registered_ids(self) -> list[str]:
        return list(_adapters.keys())


adapter_registry = AdapterRegistry()

__all__ = ["SourceAdapter", "AdapterRegistry", "adapter_registry"]
