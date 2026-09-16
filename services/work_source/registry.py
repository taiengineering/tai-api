"""Declarative Common Work Source registry.

WO-E2E-OBS009-COMMON-WORK-SOURCE-IMPLEMENT-001.
Display labels are not legal authority. Codes are.
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, Optional, Tuple

WORK_TYPES: Dict[str, Dict[str, Any]] = {
    "ELECTRICAL": {
        "label": "전기 작업",
        "subtypes": {
            "DEENERGIZED": "정전된 회로 전기작업",
            "NEAR_DEENERGIZED": "정전된 회로 인근 전기작업",
            "ENERGIZED": "충전된 회로 전기작업",
        },
        "attributes": {},
        "optional_fields": ("equipment_ref", "location_ref"),
    },
    "HIGH_PLACE": {
        "label": "고소·추락위험 작업",
        "subtypes": {
            "ROOF": "지붕 작업",
        },
        "attributes": {
            "fall_risk": {"type": "boolean", "label": "추락 위험이 있는 작업"},
            "roof": {"type": "boolean", "label": "지붕에서 수행하는 작업"},
        },
        "optional_fields": ("equipment_ref", "location_ref"),
    },
    "FORKLIFT": {
        "label": "지게차 작업",
        "subtypes": {},
        "attributes": {},
        "optional_fields": ("equipment_ref", "location_ref"),
        "canonical_meaning": "actual forklift use, not possession",
    },
    "PAINTING": {
        "label": "도장 작업",
        "subtypes": {},
        "attributes": {
            "spray": {"type": "boolean", "label": "분무 도장"},
            "flammable_liquid": {"type": "boolean", "label": "인화성 액체 사용"},
            "enclosed_space": {"type": "boolean", "label": "밀폐된 공간에서 수행"},
        },
        "optional_fields": ("material_ref", "location_ref"),
    },
    "MAINTENANCE": {
        "label": "정비 작업",
        "subtypes": {
            "POWERED_MACHINERY": "동력기계 정비· greasing / servicing",
        },
        "attributes": {
            "powered_machinery": {
                "type": "boolean",
                "label": "동력기계의 정비 또는 서비싱",
            },
        },
        "optional_fields": ("equipment_ref", "location_ref"),
    },
}

# Fix the accidental space in MAINTENANCE subtype label
WORK_TYPES["MAINTENANCE"]["subtypes"]["POWERED_MACHINERY"] = "동력기계 정비·서비싱"

ALLOWED_WORK_TYPES: FrozenSet[str] = frozenset(WORK_TYPES)
ALLOWED_PAYLOAD_KEYS: FrozenSet[str] = frozenset(
    {
        "work_type",
        "work_subtype",
        "equipment_ref",
        "material_ref",
        "location_ref",
        "attributes",
        "active",
    }
)
CANONICAL_ATTR_PREFIXES: Tuple[str, ...] = (
    "has_",
    "performs_",
    "uses_",
    "is_",
)


def registry_public() -> Dict[str, Any]:
    """UI metadata. Labels are display-only."""
    items = []
    for code, spec in WORK_TYPES.items():
        items.append(
            {
                "code": code,
                "label": spec["label"],
                "subtypes": [
                    {"code": sc, "label": sl}
                    for sc, sl in (spec.get("subtypes") or {}).items()
                ],
                "attributes": [
                    {
                        "code": ac,
                        "label": am.get("label"),
                        "type": am.get("type", "boolean"),
                    }
                    for ac, am in (spec.get("attributes") or {}).items()
                ],
                "optional_fields": list(spec.get("optional_fields") or ()),
            }
        )
    return {"work_types": items}


def work_type_spec(work_type: str) -> Optional[Dict[str, Any]]:
    return WORK_TYPES.get(work_type)
