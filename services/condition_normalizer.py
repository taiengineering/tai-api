"""services/condition_normalizer.py

Step2 Condition Layer — 공정/설비/작업 입력을 LEG eval_ctx용 boolean 조건으로 변환.

금지: Rule 수정, DB 수정, Candidate 수정.
이번 작업: 입력 표준화 계층 구축만.
"""
from __future__ import annotations

from typing import Any, Dict, List

# ── 공정 매핑 ────────────────────────────────────────────────────
PROCESS_MAP: Dict[str, str] = {
    "용접": "has_welding",
    "아크용접": "has_welding",
    "가스용접": "has_welding",
    "피복아크용접": "has_welding",
    "절단": "has_cutting",
    "산소절단": "has_cutting",
    "가스절단": "has_cutting",
    "도장": "has_painting",
    "스프레이도장": "has_painting",
    "도금": "has_plating",
    "전기도금": "has_plating",
    "주조": "has_casting",
    "사출": "has_injection",
    "압출": "has_extrusion",
    "열처리": "has_heat_treatment",
    "담금질": "has_heat_treatment",
    "소입": "has_heat_treatment",
    "화학처리": "has_chemical_process",
    "화학반응": "has_chemical_process",
    "혼합공정": "has_mixing_process",
    "분진작업": "has_dust_work",
    "연마": "has_grinding",
    "선반": "has_lathe",
    "고소작업": "has_high_work",
    "밀폐공간": "has_confined_space",
    "산소결핍": "has_confined_space",
}

# ── 설비 매핑 ────────────────────────────────────────────────────
EQUIPMENT_MAP: Dict[str, str] = {
    "보일러": "has_boiler",
    "압력용기": "has_pressure_vessel",
    "압력탱크": "has_pressure_vessel",
    "크레인": "has_crane",
    "천장크레인": "has_crane",
    "타워크레인": "has_crane",
    "이동식크레인": "has_crane",
    "승강기": "has_elevator",
    "리프트": "has_elevator",
    "고압가스설비": "has_high_pressure_gas_facility",
    "고압가스저장탱크": "has_high_pressure_gas_facility",
    "위험물저장시설": "has_hazardous_material_facility",
    "위험물탱크": "has_hazardous_material_facility",
    "집진기": "has_dust_collector",
    "국소배기장치": "has_dust_collector",
    "컨베이어": "has_conveyor",
    "전기설비": "has_electrical_facility",
    "배전반": "has_electrical_facility",
    "발전기": "has_generator",
    "압축기": "has_compressor",
    "냉동기": "has_refrigeration",
}

# ── 건설 작업 매핑 ───────────────────────────────────────────────
CONSTRUCTION_MAP: Dict[str, str] = {
    "철골공사": "construction_steel",
    "비계공사": "construction_scaffold",
    "비계": "construction_scaffold",
    "굴착공사": "construction_excavation",
    "굴착": "construction_excavation",
    "해체공사": "construction_demolition",
    "해체": "construction_demolition",
    "터널공사": "construction_tunnel",
    "터널": "construction_tunnel",
    "교량공사": "construction_bridge",
    "교량": "construction_bridge",
    "고소작업": "construction_high_work",
    "토목공사": "construction_civil",
    "토목": "construction_civil",
    "건축공사": "construction_building",
    "건축": "construction_building",
    "양중작업": "construction_lifting",
    "양중": "construction_lifting",
    "밀폐공간": "construction_confined_space",
    "전기공사": "construction_electrical",
    "화기작업": "construction_fire_work",
    "발파": "construction_blasting",
    "발파작업": "construction_blasting",
}


def normalize_process_conditions(processes: List[str]) -> Dict[str, Any]:
    """
    공정명 리스트 → {has_welding: True, ...} 형태의 boolean condition dict.

    - 중복 Condition 생성 안 함 (has_welding이 이미 있으면 덮어쓰지 않음)
    - 매핑 없는 공정명은 무시
    """
    result: Dict[str, Any] = {}
    for proc in (processes or []):
        key = PROCESS_MAP.get(str(proc).strip())
        if key and key not in result:
            result[key] = True
    return result


def normalize_equipment_conditions(equipments: List[str]) -> Dict[str, Any]:
    """
    설비명 리스트 → {has_crane: True, ...} 형태의 boolean condition dict.
    """
    result: Dict[str, Any] = {}
    for equip in (equipments or []):
        key = EQUIPMENT_MAP.get(str(equip).strip())
        if key and key not in result:
            result[key] = True
    return result


def normalize_construction_conditions(work_types: List[str]) -> Dict[str, Any]:
    """
    건설 작업종류 리스트 → {construction_steel: True, ...} 형태의 boolean condition dict.
    """
    result: Dict[str, Any] = {}
    for wt in (work_types or []):
        key = CONSTRUCTION_MAP.get(str(wt).strip())
        if key and key not in result:
            result[key] = True
    return result


def build_condition_context(
    processes: List[str],
    equipments: List[str],
    work_types: List[str],
) -> Dict[str, Any]:
    """
    공정 + 설비 + 건설 작업종류를 통합한 condition context dict.

    출력 예시:
    {
        "has_welding": True,
        "has_painting": True,
        "has_crane": True,
        "construction_steel": True,
    }

    중복 키가 발생할 경우 먼저 설정된 값을 유지.
    """
    ctx: Dict[str, Any] = {}
    ctx.update(normalize_process_conditions(processes))
    for k, v in normalize_equipment_conditions(equipments).items():
        if k not in ctx:
            ctx[k] = v
    for k, v in normalize_construction_conditions(work_types).items():
        if k not in ctx:
            ctx[k] = v
    return ctx
