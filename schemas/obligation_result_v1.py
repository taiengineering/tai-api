"""Obligation Result Contract v1 (typed 계약, 정의만 — runtime 미연결).

WO-OBLIGATION-RESULT-CONTRACT-001 / STEP 1.

SoT = DEFINITION_consumer-pipeline_v1.
계약 기본 단위 = full_result.obligations_raw[] element (정의서 §8-A Official 조립기 leg_diagnosis_svc 산출).

원칙:
- 이 모델은 "계약 정의"일 뿐이며 run_diagnosis runtime validation 에 강제 연결하지 않는다.
  (CONTRACT DEFINITION 추가 · RUNTIME BEHAVIOR 불변 · API response shape 불변)
- where / how / recipient / when 등은 원천값이 있을 때만 존재 → Optional. 없으면 None.
  "" / "미확인" / 임의 문자열 생성 금지. absent 의 현행 의미(None/미존재) 보존.
- 신규 법적 필드/판단/LLM 파생 = 0.
"""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


class ObligationDetailV1(BaseModel):
    """obligations_raw[].obligation_detail — 6하원칙 detail (thin)."""
    what: Optional[str] = None
    who: Optional[str] = None
    when: Optional[str] = None
    where: Optional[str] = None       # OPTIONAL — 원천 있을 때만
    how: Optional[str] = None         # OPTIONAL — 원천 있을 때만
    condition: Optional[str] = None
    recipient: Optional[str] = None   # OPTIONAL — 원천 있을 때만


class ObligationEnrichmentV1(BaseModel):
    """obligations_raw[].enrichment."""
    obligation_type: Optional[str] = None          # ACTION | INSPECT | PROHIBIT
    content_type: Optional[str] = None             # OBLIGATION | PROHIBITION
    inspection_cycle: Optional[str] = None
    consumer_status: Optional[str] = None          # applicable | review_required
    usable_for_evaluation: Optional[bool] = None
    completeness: Optional[Any] = None
    needs_numeric_condition: Optional[bool] = None
    missing_fields: Optional[List[Any]] = None


class ObligationResultV1(BaseModel):
    """full_result.obligations_raw[] element 의 canonical 계약."""
    # IDENTITY
    atom_id: Optional[str] = None
    source_atom_ids: Optional[List[Any]] = None
    # LEGAL
    law_name: Optional[str] = None
    law_article: Optional[str] = None
    # OBLIGATION DETAIL
    obligation_detail: Optional[ObligationDetailV1] = None
    # ENRICHMENT
    enrichment: Optional[ObligationEnrichmentV1] = None
    # RESULT / EVIDENCE
    evidence: Optional[Any] = None
    triggered_by: Optional[List[Any]] = None
    check_result: Optional[str] = None             # VERIFIED | NOT_APPLICABLE
    applicability: Optional[str] = None            # APPLICABLE

    @classmethod
    def from_raw(cls, ob: Any) -> "ObligationResultV1":
        """obligations_raw[] dict → 계약 모델(느슨 파싱, 없는 값은 None 보존). 입력 mutation 없음."""
        d = ob if isinstance(ob, dict) else {}
        detail = d.get("obligation_detail")
        enr = d.get("enrichment")
        return cls(
            atom_id=d.get("atom_id"),
            source_atom_ids=d.get("source_atom_ids"),
            law_name=d.get("law_name"),
            law_article=d.get("law_article"),
            obligation_detail=ObligationDetailV1(**detail) if isinstance(detail, dict) else None,
            enrichment=ObligationEnrichmentV1(**enr) if isinstance(enr, dict) else None,
            evidence=d.get("evidence"),
            triggered_by=d.get("triggered_by"),
            check_result=d.get("check_result"),
            applicability=d.get("applicability"),
        )
