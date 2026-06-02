"""services/code_condition_resolver.py

Step2 Code-Based Condition Resolver

역할:
  process_id / equipment_type_code / work_type → DB Lookup → boolean condition dict

원칙:
  하드코딩 금지
  TAI 표준 코드체계(process_id, equipment_type_code)만 허용
  텍스트 작업명 직접 판정 금지
→ DB에서 코드를 조회한 값으로만 Condition 생성
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── process_lv3 → condition key 매핑 (DB 조회 후 lv3값으로 매핑) ──
# lv3는 v_process_unified.process_lv3 실데이터 기준
PROCESS_LV3_CONDITION_MAP: Dict[str, str] = {
    # 제조 공정
    "용접": "has_welding",
    "용접·찾기": "has_welding",
    "절단": "has_cutting",
    "원목 절단 및 선별": "has_cutting",
    "도장": "has_painting",
    "도금": "has_plating",
    "산세·도금": "has_plating",
    "주조": "has_casting",
    "열처리": "has_heat_treatment",
    "가열 및 유지": "has_heat_treatment",
    "가열·냉각": "has_heat_treatment",
    "성형": "has_molding",
    "사출기구 운전": "has_injection",
    "반응": "has_chemical_reaction",
    "반응기 운전": "has_chemical_reaction",
    "배합": "has_mixing",
    "분쇄·혼합": "has_mixing",
    "분스": "has_dust_work",
    "분진작업": "has_dust_work",
    "미장": "has_plastering",
    "배관": "has_piping",
    "배관공급": "has_piping",
    "배관배선": "has_piping",
    "보일러·열원": "has_boiler",
    "벌크가스 저장": "has_high_pressure_gas",
    "가스배관": "has_gas_piping",
    "방폭가스": "has_explosive_gas",
    "방폭구역 설계": "has_explosive_zone",
    # 건설 공정
    "굴착": "has_excavation",
    "굴착기 작업": "has_excavation",
    "군착": "has_excavation",
    "거푸집": "has_formwork",
    "기초거푸집": "has_formwork",
    "철근": "has_rebar",
    "기초배근": "has_rebar",
    "철골": "has_steel_frame",
    "비계": "has_scaffold",
    "발파": "has_blasting",
    "하역공사": "has_excavation_work",
    "교량": "has_bridge",
    "터널": "has_tunnel",
    "구조물해체": "has_demolition",
    "내부철거": "has_interior_demolition",
    "데크플레이트": "has_deck_plate",
    # 지원 공정
    "가설/준비": "has_temporary_work",
    "도로": "has_road_work",
}

# ── equipment_type_code → condition key 매핑 (DB 실데이터 기준) ──
# 숫자코드: equipment_assets.equipment_type_code (001~040)
# 문자코드: CRANE, CONVEYOR, PRESS, PRESSURE_VESSEL
EQUIPMENT_CODE_CONDITION_MAP: Dict[str, str] = {
    # 수전/변압기/전기설비
    "001": "has_transformer",
    "002": "has_circuit_breaker",
    "006": "has_switchboard",
    "007": "has_distribution_board",
    "008": "has_welding_power",   # 용접전원장치 → has_welding도 함꼬
    # 발전기/혼합/분쇄
    "010": "has_generator",
    "011": "has_mixer",
    "012": "has_grinder",
    "013": "has_heat_exchanger",
    # 보일러/압력
    "014": "has_boiler",
    "015": "has_mixing_tank",
    "016": "has_hazardous_valve",
    "017": "has_industrial_piping",
    "018": "has_ventilation_fan",
    "019": "has_refrigeration",
    # 크레인/컨베이어/프레스
    "021": "has_crane",
    "023": "has_press",
    "024": "has_conveyor",
    # 승강기/에스칼레이터
    "025": "has_elevator",
    "026": "has_escalator",
    # 가스/위험물
    "027": "has_high_pressure_gas",
    "028": "has_lpg_storage",
    "029": "has_hazardous_material_facility",
    "030": "has_hazardous_storage",
    # 소방
    "031": "has_sprinkler",
    "032": "has_fire_detector",
    "033": "has_fire_extinguisher",
    "034": "has_fire_hydrant",
    # 집진/도장
    "036": "has_dust_collector",
    # 배수/오수
    "037": "has_wastewater_treatment",
    # 공조
    "039": "has_air_conditioning",
    # 기타 설비
    "040": "has_cnc_machine",
    # 문자코드 체계
    "CRANE": "has_crane",
    "CONVEYOR": "has_conveyor",
    "PRESS": "has_press",
    "PRESSURE_VESSEL": "has_pressure_vessel",
}

# 용접전원장치(008)는 has_welding도 수반
_EQUIPMENT_EXTRA_CONDITIONS: Dict[str, List[str]] = {
    "008": ["has_welding_power", "has_welding"],
}

# ── Process Resolver ────────────────────────────────────────────────────
def resolve_process_conditions(
    processes: List[Dict[str, Any]],
    supabase=None,
) -> Dict[str, Any]:
    """
    Step2 processes 입력을 boolean condition으로 변환.

    Args:
        processes: [
            {"process_id": "IP000005", "process_path": "...", ...}
        ]
        supabase: Supabase 클라이언트 (다중 process_id DB 조회에 사용)

    Returns:
        {"has_cutting": True, "has_welding": True, ...}
    """
    if not processes:
        return {}

    result: Dict[str, Any] = {}
    process_ids = [
        p.get("process_id") for p in processes
        if isinstance(p, dict) and p.get("process_id")
    ]

    if not process_ids:
        logger.warning("[CodeResolver] processes에 process_id 없음. 스킵.")
        return {}

    # DB 조회: process_id → process_lv3
    lv3_by_id: Dict[str, str] = {}
    if supabase and process_ids:
        try:
            # 최대 50개만 한 번에 조회
            rows = (
                supabase.table("v_process_unified")
                .select("process_id,process_lv3")
                .in_("process_id", process_ids[:50])
                .execute()
                .data or []
            )
            for row in rows:
                pid = row.get("process_id")
                lv3 = (row.get("process_lv3") or "").strip()
                if pid and lv3 and pid not in lv3_by_id:
                    lv3_by_id[pid] = lv3
        except Exception as e:
            logger.error("[CodeResolver] process DB 조회 실패: %s", e)

    for p in processes:
        if not isinstance(p, dict):
            continue
        pid = p.get("process_id")
        if not pid:
            continue

        lv3 = lv3_by_id.get(pid)

        # DB에 없으면 process_path에서 마지막 세그먼트 대체 사용
        if not lv3:
            path = p.get("process_path") or ""
            parts = [x.strip() for x in path.split(">")] if path else []
            lv3 = parts[-1] if parts else ""

        if not lv3:
            logger.debug("[CodeResolver] process_id=%s lv3 바닥 없음", pid)
            continue

        condition_key = PROCESS_LV3_CONDITION_MAP.get(lv3)
        if condition_key and condition_key not in result:
            result[condition_key] = True
            logger.debug("[CodeResolver] %s(%s) → %s", pid, lv3, condition_key)
        elif not condition_key:
            logger.debug("[CodeResolver] lv3='%s' 매핑 없음 (process_id=%s)", lv3, pid)

    return result


# ── Equipment Resolver ────────────────────────────────────────────────────
def resolve_equipment_conditions(
    equipment_codes: List[str],
) -> Dict[str, Any]:
    """
    equipment_type_code 리스트 → boolean condition dict.

    Args:
        equipment_codes: ["021", "CRANE", "014", ...]

    Returns:
        {"has_crane": True, "has_boiler": True, ...}
    """
    result: Dict[str, Any] = {}
    for code in (equipment_codes or []):
        code_str = str(code).strip()
        # 매핑 단일
        condition_key = EQUIPMENT_CODE_CONDITION_MAP.get(code_str)
        if condition_key and condition_key not in result:
            result[condition_key] = True
        # 추가 Condition (용접전원장치 등)
        extras = _EQUIPMENT_EXTRA_CONDITIONS.get(code_str, [])
        for extra_key in extras:
            if extra_key not in result:
                result[extra_key] = True
        if not condition_key:
            logger.debug("[CodeResolver] equipment_type_code='%s' 매핑 없음", code_str)
    return result


# ── 통합 Context Builder ────────────────────────────────────────────────────
def build_code_condition_context(
    processes: List[Dict[str, Any]],
    equipments: List[str],
    work_types: List[str],
    supabase=None,
) -> Dict[str, Any]:
    """
    process_id + equipment_type_code + construction_work_type → 통합 condition dict.

    입력:
        processes     : [{"process_id": "IP000005", "process_path": "..."}, ...]
        equipments    : ["021", "CRANE", ...]
        work_types    : ["터널공사", ...] (construction_work_types, 대략 한국어)
        supabase      : DB 클라이언트

    출력:
        {"has_cutting": True, "has_crane": True, "has_tunnel": True, ...}
    """
    ctx: Dict[str, Any] = {}

    # 1. 공정 코드 기반
    proc_ctx = resolve_process_conditions(processes, supabase=supabase)
    ctx.update(proc_ctx)

    # 2. 설비 코드 기반
    equip_ctx = resolve_equipment_conditions(equipments)
    for k, v in equip_ctx.items():
        if k not in ctx:
            ctx[k] = v

    # 3. 건설 작업종류 (construction_work_types)
    # 현재 DB 코드가 없으므로 CONSTRUCTION_MAP 텍스트 매핑 사용
    # (다음 단계에서 work_type DB 코드화 시 코드기반로 교체)
    from services.condition_normalizer import normalize_construction_conditions
    const_ctx = normalize_construction_conditions(work_types)
    for k, v in const_ctx.items():
        if k not in ctx:
            ctx[k] = v

    logger.info("[CodeResolver] condition_ctx=%s", ctx)
    return ctx
