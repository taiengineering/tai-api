"""MVP EXISTS 입력 필드 세트 (CURSOR-TASK-002 TASK-001).

field_code는 diagnosis_input_fields / Applicability generator 매칭 기준.
질문 문구·건수는 WO-EXISTS-ACTIVATION-SPEC-001 인계값(폴백용).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# sector → [(field_code, field_name_fallback, expected_obligation_count)]
MVP_EXISTS_FIELDS: Dict[str, List[Tuple[str, str, str]]] = {
    "INDUSTRIAL": [
        ("has_hazardous_material", "유해물질 취급", "68"),
        ("has_dust_work", "분진작업 유무", "37"),
        ("has_chemical_substance", "화학물질 취급", "32"),
        ("has_confined_space", "밀폐공간 유무", "26"),
        ("has_crane", "크레인/호이스트 유무", "25"),
        ("has_high_place_work", "고소작업 유무", "19"),
        ("has_welding", "용접 공정 유무", "18"),
    ],
    "CONSTRUCTION": [
        ("has_diving", "잠수작업 유무", "27"),
        ("has_confined_space", "밀폐공간 유무", "26"),
        ("has_asbestos_demo", "석면해체 유무", "23"),
        ("has_excavation", "굴착작업 유무", "23"),
        ("has_scaffold", "비계 사용 유무", "22"),
        ("has_pile_work", "항타/항발작업 유무", "17"),
        ("has_tower_crane", "타워크레인 유무", "7"),
    ],
    "BUILDING": [
        ("has_asbestos", "석면 사용 여부", "23"),
        ("has_confined_space", "밀폐공간 유무", "16"),
        ("has_asbestos_demo", "석면해체 유무", "7"),
    ],
}

MVP_FIELD_CODES_BY_SECTOR: Dict[str, List[str]] = {
    sector: [row[0] for row in rows]
    for sector, rows in MVP_EXISTS_FIELDS.items()
}

# public_diagnosis_requests 약식명 → 정식 field_code (TASK-003, 확인된 2건만)
FIELD_CODE_SYNONYMS: Dict[str, str] = {
    "has_gas": "has_high_pressure_gas",
    "has_hazardous": "has_hazardous_material",
}

# contract field_code → factories 컬럼 (없으면 exists_inputs 전용)
FIELD_CODE_TO_FACTORY_COLUMN: Dict[str, str] = {
    "has_hazardous_material": "is_hazardous_material",
    "has_high_pressure_gas": "has_high_pressure_gas",
    "has_chemical_substance": "has_chemical_substance",
    "has_confined_space": "has_confined_space",
    "has_tower_crane": "has_tower_crane",
    "has_asbestos_demo": "has_asbestos_demo",
    "has_diving": "has_diving",
    "has_asbestos": "has_asbestos",
    "has_boiler": "has_boiler",
    "has_blasting": "has_blasting",
    "has_safety_manager": "has_safety_manager",
    "has_excavation": "has_excavation_work",
    "has_scaffold": "has_scaffold_work",
    "has_welding": "has_welding_work",
    "has_demolition": "has_demolition_work",
    "has_high_place_work": "has_high_place_work",
}

FACTORY_COLUMN_TO_FIELD_CODE: Dict[str, str] = {
    col: code for code, col in FIELD_CODE_TO_FACTORY_COLUMN.items()
}
