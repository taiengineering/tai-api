"""Domain adapters that connect each Domain SoT to the Shared Search
Foundation.

WO-TAI-SHARED-SEARCH-F2. Each adapter:

- reads its own SoT (via injected client / reader)
- decides its own publication eligibility (Domain-native gate)
- normalizes rows into SearchDocument payloads

Every adapter goes through the Common Writer + Common Indexer +
SearchStore. Direct writes against `search_documents` from adapter
code are forbidden — the F2 audit test catches this.

RISK adapter deliberately yields empty until RISK-C02 opens the
ACTIVE gate.
"""
from services.shared_search.adapters.base import DomainAdapter, AdapterBlockedSubtype
from services.shared_search.adapters.guide import GuideAdapter
from services.shared_search.adapters.safety_material import SafetyMaterialAdapter
from services.shared_search.adapters.csi_accident import CsiAccidentAdapter
from services.shared_search.adapters.chem import ChemAdapter
from services.shared_search.adapters.knowledge import KnowledgeAdapter
from services.shared_search.adapters.precedent import PrecedentAdapter
from services.shared_search.adapters.legal import LegalAdapter
from services.shared_search.adapters.risk import RiskAdapter

__all__ = [
    "DomainAdapter", "AdapterBlockedSubtype",
    "GuideAdapter", "SafetyMaterialAdapter", "CsiAccidentAdapter",
    "ChemAdapter", "KnowledgeAdapter", "PrecedentAdapter",
    "LegalAdapter", "RiskAdapter",
]
