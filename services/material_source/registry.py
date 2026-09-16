"""Declarative Common Material Source registry.

Display labels are not legal authority. Codes are.
Family-specific registries are forbidden.
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, Optional

CLASSIFICATION_CODES: Dict[str, Dict[str, str]] = {
    "MANAGED_HAZARDOUS_SUBSTANCE": {
        "label": "관리대상 유해물질",
        "source_axis": "산업안전보건기준에 관한 규칙 별표 12",
    },
    "PERMIT_REQUIRED_HAZARDOUS_SUBSTANCE": {
        "label": "허가대상 유해물질",
        "source_axis": "산업안전보건법 시행령 제88조",
    },
    "SPECIAL_MANAGEMENT_SUBSTANCE": {
        "label": "특별관리물질",
        "source_axis": "산업안전보건기준에 관한 규칙 별표 12 명시 표기",
    },
}

ALLOWED_CLASSIFICATION_CODES: FrozenSet[str] = frozenset(CLASSIFICATION_CODES)

ALLOWED_FACTORY_PAYLOAD_KEYS: FrozenSet[str] = frozenset(
    {
        "material_name",
        "material_category_code",
        "handling_mode_codes",
        "material_master_key",
        "is_active",
    }
)


def registry_public() -> Dict[str, Any]:
    """UI metadata. Labels are display-only. Users cannot create authority here."""
    return {
        "classifications": [
            {
                "code": code,
                "label": spec["label"],
                "source_axis": spec["source_axis"],
                "user_editable": False,
            }
            for code, spec in CLASSIFICATION_CODES.items()
        ]
    }


def classification_spec(code: str) -> Optional[Dict[str, str]]:
    return CLASSIFICATION_CODES.get(code)
