"""services/canonical/industrial_www.py — WO-DUAL-IND-STEP2-IMPLEMENT-001 / GATE-2 Path A.

Pipeline Definition(45cminc/leg docs/leg/check-contract-wiring/DEFINITION_consumer-pipeline_v1.md) conformant
WWW INDUSTRIAL Canonical 계층. 소비자 form_data를 EXACT 29 canonical values로 표준화만 한다(판정/값생성 없음).

    [Consumer form_data]
      -> build_industrial_www_canonical  (Canonical: present->verbatim / absent->None)
      -> build_industrial_www_step1      (Runtime Input Adapter: DiagnoseStep1Body(sector=INDUSTRIAL, input=canonical29))
      -> run_leg_diagnosis(step1_body)   (Runtime Delegate, 무변경)
      -> build_facility(step1_body)      (무변경; top-level None -> input 사용)
      -> POST /rtm/evaluate -> STOP

엄격 규칙(전부 준수):
  - present -> value 그대로 / absent -> None. False/0/0.0/[] 는 보존.
  - default/추정/법적판단/fuzzy/SAFE asset fallback = 0. 400/false/0/[] 생성 = 0.
  - assemble_industrial_marketing_contract(SAFE asset DB source) 호출 금지 — WWW source(form_data)와 상이.
  - global canonical(materialization/adapters/service)·build_facility·run_leg_diagnosis 수정 0. 신규 alias 0.
  - 29 denominator = frozen constant 재사용.
  - top-level 29 미복제: canonical 값은 DiagnoseStep1Body.input 에만 싣는다
    (total_floor_area/has_chemical_substance top-level=None -> build_facility 가 input 사용 -> shadow 불가).
"""
from __future__ import annotations

from typing import Any, Dict

from schemas.legal_engine import DiagnoseStep1Body
from services.safe_industrial_canonical_assembler import TARGET_FIELDS

SECTOR = "INDUSTRIAL"


def build_industrial_www_canonical(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """WWW consumer form_data -> EXACT 29 canonical values.

    present -> verbatim(False/0/0.0/[] 보존), absent -> None. 값 생성/추정/판단 없음.
    """
    fd = form_data if isinstance(form_data, dict) else {}
    return {f: (fd[f] if f in fd else None) for f in TARGET_FIELDS}


def build_industrial_www_step1(body: Any) -> DiagnoseStep1Body:
    """canonical29 -> 공식 Runtime 입력(DiagnoseStep1Body).

    sector="INDUSTRIAL"(consumer 의미 유지; MANUFACTURING legacy 매핑 미사용).
    input=canonical29, top-level 29 미복제 -> build_facility 가 input 을 읽어 shadow 불가.
    """
    form_data = getattr(body, "form_data", None) or {}
    canonical = build_industrial_www_canonical(form_data)
    factory_id = (getattr(body, "factory_id", None) or None)
    return DiagnoseStep1Body(sector=SECTOR, input=canonical, factory_id=factory_id)
