"""services/canonical/saas_leg_source_adapter.py — WO-010 STEP-2C PR-A.

SaaS 3 sector(safe_industrial/construction/building) LEG runtime 이 공통으로 경유하는
source-facts → unified LEG input contract adapter. 책임 = source facts merge → 승인된 기존
alias/derived 만 적용 → build_unified_leg_input.

FREEZE 규칙:
  - 새 alias/derivation/synthetic 생성 = 0.
    · 승인 alias 는 clients.leg_runtime_client._LEG_CODE_TO_CONSUMER 2개(has_chemical,
      has_high_place_work) 뿐이고, BUILDING 은 has_chemical 승격 스킵(BUILDING patch-A
      exact-key 경로 유지 = STEP-2B 파리티 규약과 동일).
    · elevator_count 는 103 vocabulary 밖의 derived source 로만 사용(build_facility 가
      elevator_count>0 을 has_building_elevator 로 파생). BUILDING 에서만 setattr.
    · construction_type "건축" synthetic 은 SaaS 에서 새로 만들지 않는다(GATE-0 정정 반영).
      source 에 있으면 전달, 없으면 ABSENT.
  - False / 0 / [] / {} = 보존 (truthy filter 금지). None / blank string = ABSENT.
  - source 없는 축은 ABSENT/UNRESOLVED 유지 — 발명·추론 금지.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from clients.leg_runtime_client import _LEG_CODE_TO_CONSUMER
from schemas.legal_engine import DiagnoseStep1Body
from services.canonical.leg_input_contract import build_unified_leg_input


def build_saas_leg_step1(
    *,
    sector: str,
    source_facts: Dict[str, Any],
    factory_id: Optional[str] = None,
) -> DiagnoseStep1Body:
    """SaaS source facts → DiagnoseStep1Body via unified LEG input contract.

    Parameters
    ----------
    sector : "INDUSTRIAL" | "CONSTRUCTION" | "BUILDING"
        build_facility 가 sector-gate(N1 32 / BUILDING patch-A / CST rename) 를 적용할 때 사용.
    source_facts : dict
        assembler(canonical29/27) values + consumer override(RUNTIME_INPUT_FIELDS/SAFE_UI_OVERRIDE_FIELDS/
        SafeBuildingConsumerInput) 병합 dict. 상한(29/27) 없이 전량 전달 — 이 adapter 가
        _LEG_INPUT_FIELDS(103) 로 필터한다.
    factory_id : optional
        DiagnoseStep1Body.factory_id 로 전달.
    """
    facts: Dict[str, Any] = dict(source_facts or {})

    # ── 승인된 alias 만 canonical key 로 승격 (신규 alias 0) ──
    #   consumer key(has_chemical_substance / has_high_work) 값이 있고 canonical key 미존재 시만.
    #   BUILDING has_chemical 승격은 스킵 — BUILDING patch-A(has_chemical_substance exact-key) 경로 유지
    #   (STEP-2B _build_unified_step1_body 와 동일한 파리티 규약).
    for _canon, _consumer in _LEG_CODE_TO_CONSUMER.items():
        if sector == "BUILDING" and _canon == "has_chemical":
            continue
        if _canon not in facts:
            _v = facts.get(_consumer)
            if _v is not None and not (isinstance(_v, str) and not _v.strip()):
                facts[_canon] = _v

    step1 = build_unified_leg_input(
        sector=sector, source_facts=facts, factory_id=factory_id,
    )

    if sector == "BUILDING":
        # ── BUILDING has_chemical_substance exact-key ──
        #   build_facility patch-A 는 sector==BUILDING 일 때 inp.get("has_chemical_substance") 를
        #   조회한다. SafeBuildingConsumerInput.extra=forbid 로 이미 검증된 명시적 SaaS 입력이므로
        #   body.input 에 exact-key 로 실어 patch-A 에 도달시킨다(unified filter 는 103 vocabulary
        #   밖이라 배제하기 때문). STEP-2B(marketing) 와 달리 SaaS 는 명시 override 라 parity 유지.
        _hcs = facts.get("has_chemical_substance")
        if _hcs is not None and not (isinstance(_hcs, str) and not _hcs.strip()):
            if step1.input is None:
                step1.input = {}
            step1.input["has_chemical_substance"] = _hcs
        # ── BUILDING elevator_count derived (103 vocab 밖) ──
        #   build_facility 가 elevator_count>0 을 has_building_elevator 로 파생. body.elevator_count
        #   또는 body.input.elevator_count 중 하나에 있으면 됨. build_facility 는 top-level 우선 조회.
        _elev = facts.get("elevator_count")
        if _elev is not None:
            try:
                step1.elevator_count = _elev
            except (AttributeError, ValueError):
                step1 = step1.model_copy(update={"elevator_count": _elev})

    return step1
