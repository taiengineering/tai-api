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


def register_builtin_adapters() -> None:
    """Register all built-in adapters into the global adapter_registry (idempotent).

    Only affects the module-level adapter_registry singleton.
    Tests that create their own AdapterRegistry instances are unaffected.
    """
    from services.public_data_sync.adapters.kosha_guide import KoshaGuideAdapter
    from services.public_data_sync.adapters.kosha_safety_material import KoshaSafetyMaterialAdapter
    from services.public_data_sync.adapters.kosha_incremental import KoshaIncrementalAdapter
    from services.public_data_sync.adapters.holiday import HolidayAdapter

    simple_adapters = [KoshaSafetyMaterialAdapter(), KoshaGuideAdapter(), HolidayAdapter()]
    for adapter in simple_adapters:
        if adapter.adapter_key not in adapter_registry.registered_keys():
            adapter_registry.register(adapter)

    def _make_accident_cases() -> KoshaIncrementalAdapter:
        from routers.kosha_collect import _collect_accident_cases, _get_last_collected
        return KoshaIncrementalAdapter(
            adapter_key="kosha_accident_cases",
            collect_fn=_collect_accident_cases,
            log_target="accident_cases",
            get_since_fn=_get_last_collected,
        )

    def _make_construction_accidents() -> KoshaIncrementalAdapter:
        from routers.kosha_collect import _collect_construction_accidents, _get_last_collected
        return KoshaIncrementalAdapter(
            adapter_key="kosha_construction_accidents",
            collect_fn=_collect_construction_accidents,
            log_target="construction_accidents",
            get_since_fn=_get_last_collected,
        )

    for factory in (_make_accident_cases, _make_construction_accidents):
        adapter = factory()
        if adapter.adapter_key not in adapter_registry.registered_keys():
            adapter_registry.register(adapter)


__all__ = ["SourceAdapter", "AdapterRegistry", "adapter_registry", "register_builtin_adapters"]
