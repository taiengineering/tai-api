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
            "NEAR_ENERGIZED": "충전된 회로 인근 전기작업",
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
            "edge_or_opening_fall_risk": {"type": "boolean", "label": "작업발판·통로 끝 또는 개구부의 추락위험"},
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
            # PR-W1-D: FC-018/019C/019D exact equipment type.
            "equipment_type": {
                "type": "enum",
                "label": "정비 대상 설비 종류",
                "options": (
                    {"code": "AIR_PURIFICATION", "label": "공기정화설비"},
                    {"code": "TRAIN",            "label": "열차"},
                    {"code": "CENTRIFUGE",       "label": "원심기"},
                    {"code": "CRUSHER",          "label": "분쇄기"},
                ),
            },
            # PR-W1-D FC-019C: periodic inspection/maintenance (열차 정기적 점검·정비).
            "periodic": {
                "type": "boolean",
                "label": "정기적 점검·정비 여부",
            },
        },
        "optional_fields": ("equipment_ref", "location_ref"),
    },
    # PR-W1-E FC-011: 굴착작업 시 굴착기계등 실제 사용 여부.
    # generic has_excavation(굴착공사 존재)과 분리; uses_machinery=True만 exact fact 방출.
    "EXCAVATION": {
        "label": "굴착 작업",
        "subtypes": {},
        "attributes": {
            "uses_machinery": {
                "type": "boolean",
                "label": "굴착기계등 실제 사용 여부",
            },
        },
        "optional_fields": ("equipment_ref", "location_ref"),
    },
    # A5 FC-024: 산업안전보건기준에 관한 규칙 제497조.
    # 석면을 1% 이상 함유한 폐기물을 처리하는 작업으로서 석면분진이 발생할 우려가 있는 작업.
    # ASBESTOS_DEMOLITION·ASBESTOS_WASTE 등 broader types와 혼용 금지.
    "ASBESTOS_WASTE_DUST_PROCESSING": {
        "label": "석면 함유 폐기물 처리(분진발생우려) 작업",
        "subtypes": {},
        "attributes": {},
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
            # WO-E2E-OBJ03-L3-55-SEMANTIC-INPUT-INTEGRATION-001 PATCH-1 Phase 3:
            # FC-015B USE_WITH_WORKERS (DEEPEN G005/G007/G009 등).
            "USE_WITH_WORKERS": "근로자 탑승 작업 (설치된 비계 위에서 작업)",
            # PR-W1-A SEMANTIC CORRECTION-2: FC-015B INSTALLATION.
            # 설치 = 별개의 operation (Art.63 곤돌라형/작업의자형, Art.66의2 걸침비계).
            "INSTALLATION": "비계 설치 작업",
        },
        "attributes": {
            "is_dalbi": {"type": "boolean", "label": "달비계 여부"},
            "height_m": {"type": "number", "label": "비계 최고높이(m)"},
            # WO-E2E-OBJ01-SEM002-ART57B-FASTLANE-IMPLEMENT-001 +
            # WO-E2E-OBJ03-L3-55-SEMANTIC-INPUT-INTEGRATION-001 PATCH-1 Phase 3:
            # Extend scaffold_kind to 9 DEEPEN-defined values (FC-015A).
            # STEEL_PIPE and LOG kept for Art.57-B backward compatibility.
            "scaffold_kind": {
                "type": "enum",
                "label": "비계 종류",
                "options": (
                    {"code": "STEEL_PIPE_SCAFFOLD", "label": "강관비계"},
                    {"code": "STEEL_FRAME_SCAFFOLD", "label": "강관틀비계"},
                    {"code": "SUSPENDED_GONDOLA_SCAFFOLD", "label": "달비계(곤돌라형)"},
                    {"code": "WORK_CHAIR_SUSPENDED_SCAFFOLD", "label": "달비계(작업의자형)"},
                    {"code": "HANGING_SCAFFOLD", "label": "달대비계"},
                    {"code": "HORSE_TRESTLE_SCAFFOLD", "label": "말비계"},
                    {"code": "MOBILE_SCAFFOLD", "label": "이동식비계"},
                    {"code": "SYSTEM_SCAFFOLD", "label": "시스템비계"},
                    {"code": "LEANING_SCAFFOLD", "label": "걸침비계"},
                    {"code": "HOOK_SCAFFOLD", "label": "선박비계(걸침형)"},
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
