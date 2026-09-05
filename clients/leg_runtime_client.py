"""LEG Runtime API Client — WO-SERVICE-002.

    tai-api  ──HTTP──>  LEG Runtime API  ──>  31,434 Approved Atom  ──>  4-Result

Repository 직접 접근 없음. DATABASE_URL 사용 금지. LEG_RUNTIME_URL만 사용.
Shadow(run_shadow_compare)는 예외를 전파하지 않는다.
WO-PIPE-004 소비자 경로(build_facility/evaluate_rtm)는 실패를 예외로 올려 호출자가 처리한다(TAI fallback 금지).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger("clients.leg_runtime")

LEG_RUNTIME_URL = os.getenv("LEG_RUNTIME_URL", "").rstrip("/")
LEG_RUNTIME_TIMEOUT = float(os.getenv("LEG_RUNTIME_TIMEOUT", "5.0"))

# Input Contract에 있는 필드만 전달한다. 신규 필드 생성 금지.
# DiagnoseStep1Body 속성명 -> LEG Input Contract field_code
_FIELD_MAP = {
    "worker_count": "worker_count",
    "total_floor_area": "total_floor_area",
    "building_use_type": "building_use_type",
    "ksic_major": "ksic_major",
    "construction_type": "construction_type",
}


class LegRuntimeError(RuntimeError):
    pass


def is_enabled() -> bool:
    return bool(LEG_RUNTIME_URL)


def build_compiler_output(step1_body: Any) -> Dict[str, Any]:
    """DiagnoseStep1Body -> LEG compiler_output. 값 보정·추정 없음."""
    out: Dict[str, Any] = {}
    for attr, field_code in _FIELD_MAP.items():
        val = getattr(step1_body, attr, None)
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue          # 빈 문자열은 미제공으로 취급 (값을 만들지 않는다)
        out[field_code] = val
    return out


def evaluate(compiler_output: Dict[str, Any], max_results: Optional[int] = 0,
             timeout: Optional[float] = None) -> Dict[str, Any]:
    """POST {LEG_RUNTIME_URL}/evaluate. retry 0, fail fast."""
    if not is_enabled():
        raise LegRuntimeError("LEG_RUNTIME_URL 미설정")
    url = "{}/evaluate".format(LEG_RUNTIME_URL)
    try:
        resp = httpx.post(
            url,
            json={"compiler_output": compiler_output, "max_results": max_results},
            timeout=timeout or LEG_RUNTIME_TIMEOUT,
        )
    except Exception as e:
        raise LegRuntimeError("request failed: {}".format(e))
    if resp.status_code != 200:
        raise LegRuntimeError("HTTP {}: {}".format(resp.status_code, resp.text[:200]))
    try:
        return resp.json()
    except Exception as e:
        raise LegRuntimeError("invalid json: {}".format(e))


def run_shadow_compare(step1_body: Any, diagnosis_id: str,
                       legacy_engine_version: str, legacy_rule_version: str,
                       legacy_obligation_count: int) -> Dict[str, Any]:
    """Shadow 실행 + 비교 로그. 절대 예외를 던지지 않는다.

    실패 시 shadow_status='SKIP' 을 반환하고 기존 진단은 그대로 진행된다.
    비교 결과는 application log에만 남긴다 (DDL/DML 없음).
    """
    record: Dict[str, Any] = {
        "diagnosis_id": diagnosis_id,
        "legacy_engine_version": legacy_engine_version,
        "legacy_rule_version": legacy_rule_version,
        "legacy_obligation_count": legacy_obligation_count,
        "shadow_status": "SKIP",
        "v3_rule_version": None,
        "v3_applicable": None,
        "v3_not_applicable": None,
        "v3_required_input": None,
        "v3_undecidable": None,
        "v3_total": None,
        "v3_checksum": None,
        "execution_time": None,
        "error": None,
    }
    if not is_enabled():
        record["error"] = "LEG_RUNTIME_URL not set"
        log.info("leg_runtime_shadow %s", record)
        return record

    t0 = time.perf_counter()
    try:
        compiler_output = build_compiler_output(step1_body)
        record["consumer_input"] = compiler_output
        data = evaluate(compiler_output, max_results=0)
        counts = data.get("counts") or {}
        record.update({
            "shadow_status": "OK",
            "v3_rule_version": data.get("rule_version"),
            "v3_applicable": counts.get("applicable"),
            "v3_not_applicable": counts.get("not_applicable"),
            "v3_required_input": counts.get("required_additional_input"),
            "v3_undecidable": counts.get("undecidable"),
            "v3_total": counts.get("total"),
            "v3_checksum": data.get("checksum"),
            "execution_time": round(time.perf_counter() - t0, 4),
        })
    except LegRuntimeError as e:
        record["error"] = str(e)
        record["execution_time"] = round(time.perf_counter() - t0, 4)
    except Exception as e:                       # 어떤 예외도 밖으로 나가지 않는다
        record["error"] = "unexpected: {!s}".format(e)
        record["execution_time"] = round(time.perf_counter() - t0, 4)

    log.info("leg_runtime_shadow %s", record)
    return record


# ── WO-PIPE-004: LEG 전용 소비자 경로 (/rtm/evaluate) ─────────────────────────
# LEG Runtime이 판정에 참조하는 input_field_code 전체(실측: requirement_input_resolution_v3).
# 추정 금지 — step1_body에 없는 필드는 미포함(LEG가 NO_APPLICABLE/EVIDENCE_GAP 반환).
_LEG_INPUT_FIELDS = (
    "worker_count", "total_floor_area", "building_use_type", "construction_type",
    "ksic_major", "has_chemical", "has_elevator", "has_noise_work", "has_asbestos",
    "has_crane", "has_excavation", "has_concrete_work", "has_hazardous_material",
    "has_gas", "is_multi_use", "has_safety_manager", "has_subcontractor", "has_scaffold",
    "has_diving", "has_dust_work", "has_forklift", "has_high_pressure_gas", "has_pile_work",
    "has_confined_space", "has_welding", "has_mech_parking", "has_pressure_vessel",
    "has_demolition", "has_radiation", "has_rolling", "has_boiler", "has_conveyor",
    "has_steel_frame", "is_energy_intensive", "has_grinding", "has_painting", "has_blasting",
    "has_high_place_work", "gas_capacity_kg", "has_gondola", "has_water_tank", "has_press",
    "has_fire_hydrant", "has_emergency_broadcast", "has_hazmat_storage", "has_sprinkler",
    "has_emergency_gen", "has_casting", "has_plating",
    # WO-LEG-SAFETY-3-CONSUMER-INPUT-IMPLEMENT-01: 산안49/187/665 소비자 입력 5축(append).
    # numeric은 canonical_applicability VERBATIM 경로로 float 보존(Nexas _NUMERIC_FIELDS 미등록).
    "work_height_m", "has_truck_loading_unloading", "truck_loading_height_m",
    "has_manual_heavy_handling", "manual_handling_weight_kg",
    # WO-OBJ-WIRING-SAFETY-SPECIFIC-PASSTHROUGH-IMPLEMENT-01: specific consumer-vocab 축 2개(append).
    # production mapped_field(has_asbestos_demo·has_tower_crane)과 exact-name 일치 → RTM이
    # specific atom(석면해체 7·타워크레인 5)만 매칭. generic has_asbestos/has_crane 무접촉
    # (alias 없음 — SPECIFIC INPUT→SPECIFIC KEY→SPECIFIC mapped_field 원칙). derived/추정 없음.
    "has_asbestos_demo", "has_tower_crane",
    # WO-BLD-MKT-CONSUMER-INPUT-WIRING-016 STEP-2: BUILDING N1 raw primitive 32축(append).
    # building_use_type 은 이미 위 목록에 존재(중복 추가 안 함). derived/proxy 없음 — exact-name passthrough.
    # numeric(ratio 포함)/enum/boolean 모두 step1_body.input 통로로 전달, build_facility 가 None/blank 만 omit.
    # WP-C(applicable.py) frozen tree 의 Leaf.field 와 exact 일치. LEG condition/의미 불변.
    "floor_count", "building_height_m", "floor_area_sum_at_or_above_11f",
    "performance_use_floor_area_sum", "cantilever_projection_m", "column_span_m",
    "flat_plate_column_section_ratio", "occupancy_capacity",
    "underground_connection_entrance_distance_m", "connection_open_space_floor_area_m2",
    "connection_open_space_open_area_ratio", "stair_or_ramp_effective_width_m",
    "building_activity_type", "building_use_category",
    "has_performance_assembly_use", "is_target_facility_in_basement",
    "has_gas_boiler_heating_system", "has_centralized_gas_supply",
    "is_collapse_risk_land", "has_land_preparation", "has_building_construction_activity",
    "has_wet_land", "has_water_seepage_risk", "has_landfill_or_similar_ground",
    "has_flat_plate_structure", "authority_designated_special_structure",
    "article32_3_alternative_confirmation_subject",
    "has_wall_between_connection_entrances", "wall_between_connection_entrances_is_fire_resistant",
    "has_stair_or_ramp_in_open_space", "is_connected_to_subway_or_underground_mall",
    "has_hazardous_material_in_out_event",
    # WO-006 PATCH-2A: numeric 11 + trigger 4 (verbatim passthrough; no alias/derivation).
    "scaffold_height_m", "grinding_wheel_diameter_cm", "breathing_gas_cylinder_pressure_kgf_cm2",
    "structure_height_m", "object_drop_height_m", "construction_machine_weight_ton",
    "hazmat_designated_quantity_multiple", "rotor_peripheral_speed_m_s", "rotor_shaft_weight_ton",
    "same_site_construction_count", "diving_worker_count",
    "has_structure", "has_object_drop", "has_construction_machine", "has_high_speed_rotor",
)

# WO-FIX-BUILDFACILITY-SECTOR-GATE-001: WIRING-016 append BUILDING N1 raw primitive 32축.
# build_facility 는 이 축들을 sector=="BUILDING" 일 때만 facility 에 넣는다(다른 sector 유입 차단).
# building_use_type 은 base 56 축(INDUSTRIAL 업종 등 공용)이라 여기 미포함(gate 대상 아님).
# floor_count 등 이름 공유 축도 포함 — INDUSTRIAL/CONSTRUCTION 은 WIRING-016 이전에도 이 축을
# build_facility 로 소비하지 않았으므로(원 56축 부재) gate 로 인한 회귀 0.
_BUILDING_N1_FIELDS = frozenset({
    "floor_count", "building_height_m", "floor_area_sum_at_or_above_11f",
    "performance_use_floor_area_sum", "cantilever_projection_m", "column_span_m",
    "flat_plate_column_section_ratio", "occupancy_capacity",
    "underground_connection_entrance_distance_m", "connection_open_space_floor_area_m2",
    "connection_open_space_open_area_ratio", "stair_or_ramp_effective_width_m",
    "building_activity_type", "building_use_category",
    "has_performance_assembly_use", "is_target_facility_in_basement",
    "has_gas_boiler_heating_system", "has_centralized_gas_supply",
    "is_collapse_risk_land", "has_land_preparation", "has_building_construction_activity",
    "has_wet_land", "has_water_seepage_risk", "has_landfill_or_similar_ground",
    "has_flat_plate_structure", "authority_designated_special_structure",
    "article32_3_alternative_confirmation_subject",
    "has_wall_between_connection_entrances", "wall_between_connection_entrances_is_fire_resistant",
    "has_stair_or_ramp_in_open_space", "is_connected_to_subway_or_underground_mall",
    "has_hazardous_material_in_out_event",
})


# 소비자 스키마 필드명 -> LEG Input Contract field_code (WO-E2E-SEM-001 승인: 의미 동일, 이름만 상이)
# has_fall_risk 는 제외(추락위험 != 고소작업대, UNDECIDABLE — 별도 WO 승인 전 금지).
_LEG_CODE_TO_CONSUMER = {
    "has_chemical": "has_chemical_substance",
    "has_high_place_work": "has_high_work",
}


def build_facility(step1_body: Any) -> Dict[str, Any]:
    """DiagnoseStep1Body -> LEG /rtm/evaluate facility(consumer_input dict).

    값 출처: step1_body 최상위 속성 우선, 없으면 step1_body.input dict.
    None/빈 문자열은 미포함. 추정/임의 매핑 없음.
    """
    inp = getattr(step1_body, "input", None) or {}
    if not isinstance(inp, dict):
        inp = {}
    facility: Dict[str, Any] = {}
    _sector = getattr(step1_body, "sector", None)
    for code in _LEG_INPUT_FIELDS:
        # WO-FIX-BUILDFACILITY-SECTOR-GATE-001: BUILDING N1 32축은 BUILDING sector 에만 노출.
        if code in _BUILDING_N1_FIELDS and _sector != "BUILDING":
            continue
        val = getattr(step1_body, code, None)
        if val is None:
            val = inp.get(code)
        if val is None:
            # PATCH-A-1: BUILDING has_chemical alias 차단(이중생성 방지).
            #   has_chemical_substance 명시 시 has_chemical 순회가 alias 로 그 값을 집어
            #   facility["has_chemical"] 이중 생성. BUILDING 은 exact-key(아래 blocks)로만.
            _alias = None if (_sector == "BUILDING" and code == "has_chemical") else _LEG_CODE_TO_CONSUMER.get(code)
            if _alias:
                val = getattr(step1_body, _alias, None)
                if val is None:
                    val = inp.get(_alias)
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        facility[code] = val
    # WO-LEG-ELEVATOR-OPTION-A: 건물 승강기(승강기법) 축.
    # has_building_elevator는 derived-only canonical field — consumer passthrough 금지.
    # (_LEG_INPUT_FIELDS 미등록: sector 무관 복사 통로를 차단하여 direct injection 방지)
    # 명시적 sector==BUILDING gate — INDUSTRIAL/CONSTRUCTION elevator_count 오염 방지.
    # 산업 리프트(has_elevator, 산안규칙)와 분리된 축이며, has_elevator는 무접촉.
    if _sector == "BUILDING":
        _ec = getattr(step1_body, "elevator_count", None)
        if _ec is None:
            _ec = inp.get("elevator_count")
        # WP1-HOTFIX-001: elevator_count 명시값이면 has_building_elevator boolean 화.
        #   None → absent (미확인). 0 → False (명시적 없음, 이전엔 absent 로 유실).
        #   1+ → True. (승강기법 조항이 '승강기 없음' 을 판정하려면 False 가 필요.)
        if isinstance(_ec, (int, float)) and not isinstance(_ec, bool):
            facility["has_building_elevator"] = (_ec > 0)
    # WO-FE-CST-GAP-IMPL-001 CODE-C2: CONSTRUCTION has_chemical_substance exact-name.
    # PSR mapped_field=has_chemical_substance (has_chemical=0 atom). facility key 를 exact 로 교정.
    # sector-gated — 산업/건축은 기존 has_chemical 유지(INDUSTRIAL 동작 불변).
    if _sector == "CONSTRUCTION" and "has_chemical" in facility:
        facility["has_chemical_substance"] = facility.pop("has_chemical")
    # WO-BLD-FINALIZATION PATCH-A: BUILDING has_chemical_substance exact-key.
    #   has_chemical_substance 는 _LEG_INPUT_FIELDS 미등록(순회 누락)이나 SafeBuildingConsumerInput 이
    #   C1(화관법 도급) 명시 입력으로 받는다. BUILDING sector 에서 input 의 명시값을 facility 에
    #   exact key 로 전달(화관법 atom has_chemical_substance 발동). has_chemical 자동변환 금지
    #   (building 은 construction rename 대상 아님 — 명시 exact-key 만).
    if _sector == "BUILDING":
        _hcs = getattr(step1_body, "has_chemical_substance", None)
        if _hcs is None:
            _hcs = inp.get("has_chemical_substance")
        if _hcs is not None:
            facility["has_chemical_substance"] = _hcs
    return facility


def evaluate_rtm(facility: Dict[str, Any], *, timeout: Optional[float] = None) -> Dict[str, Any]:
    """POST {LEG_RUNTIME_URL}/rtm/evaluate. 사업장 배치 판정 -> obligations. retry 0, fail fast.

    반환(그대로): {status, obligations[], obligation_count, provenance, contract,
                  trace_id, error_code, error}. 4xx/5xx도 body를 반환하며 호출자가 status로 분기.
    네트워크/파싱 실패만 LegRuntimeError로 올린다(호출자가 처리, fallback 금지).
    """
    if not is_enabled():
        raise LegRuntimeError("LEG_RUNTIME_URL 미설정")
    url = "{}/rtm/evaluate".format(LEG_RUNTIME_URL)
    try:
        resp = httpx.post(
            url,
            json={"facility": facility},
            timeout=timeout or LEG_RUNTIME_TIMEOUT,
        )
    except Exception as e:
        raise LegRuntimeError("request failed: {}".format(e))
    try:
        return resp.json()
    except Exception as e:
        raise LegRuntimeError("invalid json: {}".format(e))


# ── WO-DQ-WHAT-05C: LEG canonical source-text batch fetch (/rtm/source-texts) ──
# atom_ids[] -> LEG Runtime source-text 계약(dict). retry 0 · fallback 0 · LEG DB direct 0.
# non-200 에서 response body 를 예외문구에 싣지 않는다(status code 까지만 — raw repo detail leak 금지).

def fetch_source_texts(atom_ids: Any, *, timeout: Optional[float] = None) -> Dict[str, Any]:
    """POST {LEG_RUNTIME_URL}/rtm/source-texts. payload EXACT {"atom_ids":[...]}. fail fast.

    반환(그대로): {version, source_mode, items[], unresolved[]}.
    LEG_RUNTIME_URL 미설정 / network / non-200 / invalid JSON -> LegRuntimeError.
    """
    if not is_enabled():
        raise LegRuntimeError("LEG_RUNTIME_URL 미설정")
    url = "{}/rtm/source-texts".format(LEG_RUNTIME_URL)
    try:
        resp = httpx.post(
            url,
            json={"atom_ids": list(atom_ids)},
            timeout=timeout or LEG_RUNTIME_TIMEOUT,
        )
    except Exception as e:
        raise LegRuntimeError("request failed: {}".format(e))
    if resp.status_code != 200:
        # status code 만 노출. resp.text(=LEG repository detail)는 싣지 않는다.
        raise LegRuntimeError("HTTP {}".format(resp.status_code))
    try:
        return resp.json()
    except Exception as e:
        raise LegRuntimeError("invalid json: {}".format(e))


# ── WO-DQ-WHAT-05D-A0: LEG law_master/law_article row fetch (/rtm/evidence-rows) ──
# law_names[] + article_nos[] -> LEG Runtime evidence-rows 계약(dict).
# retry 0 · fallback 0 · LEG DB direct 0. non-200 body 미노출.

def fetch_evidence_rows(law_names, article_nos, *, timeout: Optional[float] = None) -> Dict[str, Any]:
    """POST {LEG_RUNTIME_URL}/rtm/evidence-rows. payload EXACT {"law_names":[...],"article_nos":[...]}. fail fast."""
    if not is_enabled():
        raise LegRuntimeError("LEG_RUNTIME_URL 미설정")
    url = "{}/rtm/evidence-rows".format(LEG_RUNTIME_URL)
    try:
        resp = httpx.post(
            url,
            json={"law_names": list(law_names), "article_nos": list(article_nos)},
            timeout=timeout or LEG_RUNTIME_TIMEOUT,
        )
    except Exception as e:
        raise LegRuntimeError("request failed: {}".format(e))
    if resp.status_code != 200:
        raise LegRuntimeError("HTTP {}".format(resp.status_code))   # body 미노출
    try:
        data = resp.json()
    except Exception as e:
        raise LegRuntimeError("invalid json: {}".format(e))
    # malformed contract → LegRuntimeError (C08). 최소 shape 검증만(resolver 의미 판단 아님).
    if (not isinstance(data, dict)
            or data.get("version") != 1
            or data.get("source_mode") != "LIVE_LEG_EVIDENCE"
            or not isinstance(data.get("laws"), list)
            or not isinstance(data.get("articles"), list)):
        raise LegRuntimeError("malformed evidence-rows contract")
    return data
