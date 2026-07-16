"""LEG Runtime API Client — WO-SERVICE-002.

    tai-api  ──HTTP──>  LEG Runtime API  ──>  31,434 Approved Atom  ──>  4-Result

Repository 직접 접근 없음. DATABASE_URL 사용 금지. LEG_RUNTIME_URL만 사용.
Shadow Mode 전용 — 이 모듈은 절대 예외를 호출자에게 전파하지 않는다.
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
