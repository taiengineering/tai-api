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
)


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
    for code in _LEG_INPUT_FIELDS:
        val = getattr(step1_body, code, None)
        if val is None:
            val = inp.get(code)
        if val is None:
            _alias = _LEG_CODE_TO_CONSUMER.get(code)
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
    _sector = getattr(step1_body, "sector", None)
    if _sector == "BUILDING":
        _ec = getattr(step1_body, "elevator_count", None)
        if _ec is None:
            _ec = inp.get("elevator_count")
        if isinstance(_ec, (int, float)) and not isinstance(_ec, bool) and _ec > 0:
            facility["has_building_elevator"] = True
    # WO-FE-CST-GAP-IMPL-001 CODE-C2: CONSTRUCTION has_chemical_substance exact-name.
    # PSR mapped_field=has_chemical_substance (has_chemical=0 atom). facility key 를 exact 로 교정.
    # sector-gated — 산업/건축은 기존 has_chemical 유지(INDUSTRIAL 동작 불변).
    if _sector == "CONSTRUCTION" and "has_chemical" in facility:
        facility["has_chemical_substance"] = facility.pop("has_chemical")
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
