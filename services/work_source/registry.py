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
    # WO-E2E-OBJ01-SEM002-ART57A-CONSUMER-INPUT-WIRING-001:
    # SCAFFOLD family. Same-entity binding: each row = one specific
    # scaffold (equipment_ref) with its type/height and the activity
    # being performed on THAT scaffold. Projector never cross-combines
    # attributes across rows. Adds no per-law boolean to the DB.
    "SCAFFOLD": {
        "label": "비계 작업",
        "subtypes": {
            "ASSEMBLY": "비계 조립 작업",
            "DISMANTLE": "비계 해체 작업",
            "MODIFICATION": "비계 변경 작업",
        },
        "attributes": {
            "is_dalbi": {"type": "boolean", "label": "달비계 여부"},
            "height_m": {"type": "number", "label": "비계 최고높이(m)"},
            # WO-E2E-OBJ01-SEM002-ART57B-FASTLANE-IMPLEMENT-001:
            # SCAFFOLD kind for Art.57 제2항 (강관비계/통나무비계 조립 → 쌍줄).
            # Single enum, not two booleans, so a row's scaffold type stays
            # unique per entity and same-entity binding is preserved by the
            # projector's per-row evaluation. missing != OTHER: omit the key
            # rather than defaulting to OTHER.
            "scaffold_kind": {
                "type": "enum",
                "label": "비계 종류",
                "options": (
                    {"code": "STEEL_PIPE", "label": "강관비계"},
                    {"code": "LOG", "label": "통나무비계"},
                    {"code": "OTHER", "label": "기타 비계"},
                ),
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


def _attribute_metadata(code: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """UI-facing attribute descriptor. Adds `options` only when the spec defines them."""
    out: Dict[str, Any] = {
        "code": code,
        "label": meta.get("label"),
        "type": meta.get("type", "boolean"),
    }
    options = meta.get("options")
    if options:
        out["options"] = [
            {"code": o.get("code"), "label": o.get("label")} for o in options
        ]
    return out


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
                    _attribute_metadata(ac, am)
                    for ac, am in (spec.get("attributes") or {}).items()
                ],
                "optional_fields": list(spec.get("optional_fields") or ()),
            }
        )
    return {"work_types": items}


def work_type_spec(work_type: str) -> Optional[Dict[str, Any]]:
    return WORK_TYPES.get(work_type)
