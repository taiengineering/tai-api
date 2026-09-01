#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/safe_building_leg_handoff.py — STEP4 canonical 36 → 기존 LEG Runtime handoff (v1.0.0)
WO-SAFE-LEGAL-BLD-CANONICAL-IMPLEMENT-001 / STEP5 (HANDOFF ONLY).

책임 정확히 2개:
  1. build_building_leg_facility: STEP4 assemble 결과(canonical_contract["values"] 36개)를 LEG facility 로 projection
  2. send_building_canonical_to_leg: facility 생성 → 기존 evaluate_rtm(facility) 호출 → LEG raw response 그대로 반환

정책(전부 준수):
  - LEG 인터페이스는 기존 clients/leg_runtime_client 만 사용(신규 LEG API/allowlist/alias/default/sector rule 0).
  - projection 은 기존 leg_runtime_client.build_facility 재사용 → exact-name(_LEG_INPUT_FIELDS) + 승인 alias + sector gate.
  - sector="BUILDING" 고정 → build_facility 의 기존 BUILDING gate(elevator>0 → building elevator=True) 재사용.
    (STEP5 신규 파생 아님; if elevator>0 직접 작성 금지. 산업 리프트 신규 생성 금지.)
  - CONSTRUCTION 전용 chemical rename(has_chemical→has_chemical_substance)은 BUILDING 미적용 → has_chemical 유지.
  - values ONLY. STEP5 에서 factories/buildings/facility_profiles/form_data 재조회 0(DB READ 0).
  - E5(building_use_type 등)는 STEP4 에서 NULL/unresolved → build_facility None 자동 미포함(STEP5 재계산 0).
  - _LEG_INPUT_FIELDS 미소비 Marketing field(address/floor_count/multi_use_type/has_smoke_control 등)는 억지 전달 0.
  - None/blank 미전달, false/0 보존(build_facility 규율). 신규 default/추정/판단/파생 0.
  - unresolved_fields 로 실행 차단 판단 0(READINESS POLICY 0). 결과 가공/저장/billing 0(raw passthrough).
"""
from __future__ import annotations

from typing import Any, Dict

from clients import leg_runtime_client

SECTOR = "BUILDING"


class _CanonicalStep1Adapter:
    """canonical_contract["values"] 를 기존 build_facility(step1_body) 가 읽는 형태로 노출하는 얇은 어댑터.

    build_facility 는 getattr(step1_body, code)/step1_body.input.get(code) 로 값을 읽는다.
    __getattr__ 이 values 의 해당 key 를 반환(없으면 None). 신규 매핑/보정 없음 — 순수 노출만.
    sector="BUILDING" 고정 → build_facility 의 기존 BUILDING gate(승강기 수>0→건물승강기 True) 발동.
    """

    def __init__(self, values: Dict[str, Any]):
        object.__setattr__(self, "_values", dict(values or {}))
        object.__setattr__(self, "input", {})   # 최상위 속성만 사용(중복 소스 방지)
        object.__setattr__(self, "sector", SECTOR)

    def __getattr__(self, name):
        # 정상 조회 실패 시에만 호출됨(input/sector/_values 는 실제 속성). values 의 값을 반환(없으면 None).
        return object.__getattribute__(self, "_values").get(name)


def build_building_leg_facility(canonical_contract: Dict[str, Any]) -> Dict[str, Any]:
    """STEP4 canonical_contract → LEG facility(consumer_input dict). 기존 build_facility 재사용."""
    values = (canonical_contract or {}).get("values") or {}
    step1 = _CanonicalStep1Adapter(values)
    return leg_runtime_client.build_facility(step1)   # exact-name + 승인 alias + 기존 BUILDING sector gate


def send_building_canonical_to_leg(canonical_contract: Dict[str, Any]) -> Dict[str, Any]:
    """facility 생성 → 기존 evaluate_rtm(facility) 호출 → LEG raw response 그대로 반환. 결과 가공 0."""
    facility = build_building_leg_facility(canonical_contract)
    return leg_runtime_client.evaluate_rtm(facility)
