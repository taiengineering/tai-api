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
            get_since_fn=lambda target: _get_last_collected(target, strict=True),
        )

    def _make_construction_accidents() -> KoshaIncrementalAdapter:
        from routers.kosha_collect import _collect_construction_accidents, _get_last_collected
        return KoshaIncrementalAdapter(
            adapter_key="kosha_construction_accidents",
            collect_fn=_collect_construction_accidents,
            log_target="construction_accidents",
            get_since_fn=lambda target: _get_last_collected(target, strict=True),
        )

    for factory in (_make_accident_cases, _make_construction_accidents):
        adapter = factory()
        if adapter.adapter_key not in adapter_registry.registered_keys():
            adapter_registry.register(adapter)

    from services.public_data_sync.adapters.keco_chemical import KecoChemicalAdapter
    keco = KecoChemicalAdapter()
    if keco.adapter_key not in adapter_registry.registered_keys():
        adapter_registry.register(keco)

    from services.public_data_sync.adapters.csi_accident import CsiAccidentAdapter
    csi = CsiAccidentAdapter()
    if csi.adapter_key not in adapter_registry.registered_keys():
        adapter_registry.register(csi)

    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter
    ext132 = Ext132HazardousMaterialAdapter()
    if ext132.adapter_key not in adapter_registry.registered_keys():
        adapter_registry.register(ext132)

    from services.public_data_sync.adapters.ext165_chemical_accident import Ext165ChemicalAccidentAdapter
    ext165 = Ext165ChemicalAccidentAdapter()
    if ext165.adapter_key not in adapter_registry.registered_keys():
        adapter_registry.register(ext165)

    from services.public_data_sync.adapters.ext037_chemical_safety import Ext037ChemicalSafetyAdapter
    ext037 = Ext037ChemicalSafetyAdapter()
    if ext037.adapter_key not in adapter_registry.registered_keys():
        adapter_registry.register(ext037)


__all__ = ["SourceAdapter", "AdapterRegistry", "adapter_registry", "register_builtin_adapters"]
