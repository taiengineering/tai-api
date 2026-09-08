"""Obligation Result Contract v1 (typed 계약, 정의만 — runtime 미연결).

WO-OBLIGATION-RESULT-CONTRACT-001 / STEP 1 + PATCH-1.

SoT = DEFINITION_consumer-pipeline_v1. 단위 = full_result.obligations_raw[] element.

원칙:
- 계약 "정의"일 뿐 run_diagnosis runtime validation 에 강제 연결하지 않는다(API/DB/runtime 불변).
- ABSENT ≠ NULL 보존(PATCH-1 P1): from_raw 는 source dict 에 **실제 존재하는 key 만** 모델에 전달한다.
  → model_dump(exclude_unset=True) 시 source 에 없던 field 는 key 자체가 없고,
    source 에 명시된 None 은 key + None 으로 유지된다.
- where/how/recipient/when = 원천 있을 때만 → Optional. 임의 default/문자열 생성 0.
- 신규 법적필드/판단/LLM 파생 0. mapped_field 는 official result 에 이미 존재하는 필드의 계약 반영(신규 아님).
"""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel

_DETAIL_KEYS = ("what", "who", "when", "where", "how", "condition", "recipient")
_ENRICH_KEYS = (
    "obligation_type", "content_type", "inspection_cycle", "consumer_status",
    "usable_for_evaluation", "completeness", "needs_numeric_condition", "missing_fields",
)
_ROOT_KEYS = (
    "atom_id", "source_atom_ids", "law_name", "law_article",
    "evidence", "triggered_by", "check_result", "applicability", "mapped_field",
)


class ObligationDetailV1(BaseModel):
    """obligations_raw[].obligation_detail — 6하원칙 detail (thin)."""
    what: Optional[str] = None
    who: Optional[str] = None
    when: Optional[str] = None
    where: Optional[str] = None       # OPTIONAL — 원천 있을 때만
    how: Optional[str] = None         # OPTIONAL — 원천 있을 때만
    condition: Optional[str] = None
    recipient: Optional[str] = None   # OPTIONAL — 원천 있을 때만

    @classmethod
    def from_raw(cls, d: Any) -> "ObligationDetailV1":
        src = d if isinstance(d, dict) else {}
        return cls(**{k: src[k] for k in _DETAIL_KEYS if k in src})


class ObligationEnrichmentV1(BaseModel):
    """obligations_raw[].enrichment."""
    obligation_type: Optional[str] = None          # APPOINT|INSPECT|REPORT|NOTIFY|TRAINING|PROHIBIT|ACTION
    content_type: Optional[str] = None             # OBLIGATION|PROHIBITION
    inspection_cycle: Optional[str] = None
    consumer_status: Optional[str] = None          # applicable|review_required
    usable_for_evaluation: Optional[bool] = None
    completeness: Optional[str] = None             # COMPLETE|PARTIAL|CATALOG_ONLY
    needs_numeric_condition: Optional[bool] = None
    missing_fields: Optional[List[str]] = None     # 문자열 field명 목록

    @classmethod
    def from_raw(cls, e: Any) -> "ObligationEnrichmentV1":
        src = e if isinstance(e, dict) else {}
        return cls(**{k: src[k] for k in _ENRICH_KEYS if k in src})


class ObligationResultV1(BaseModel):
    """full_result.obligations_raw[] element 의 canonical 계약."""
    # IDENTITY
    atom_id: Optional[str] = None
    source_atom_ids: Optional[List[str]] = None
    # LEGAL
    law_name: Optional[str] = None
    law_article: Optional[str] = None
    # OBLIGATION DETAIL
    obligation_detail: Optional[ObligationDetailV1] = None
    # ENRICHMENT
    enrichment: Optional[ObligationEnrichmentV1] = None
    # RESULT / EVIDENCE
    evidence: Optional[Any] = None                 # 타입 이번 증거로 미확정 — 좁히지 않음
    triggered_by: Optional[List[str]] = None
    check_result: Optional[str] = None             # VERIFIED|NOT_APPLICABLE
    applicability: Optional[str] = None            # APPLICABLE
    # 기존 official result 필드 (신규 아님, PATCH-1 P3)
    mapped_field: Optional[str] = None

    @classmethod
    def from_raw(cls, ob: Any) -> "ObligationResultV1":
        """obligations_raw[] dict → 계약 모델. source 에 실제 존재하는 key 만 set(ABSENT≠NULL 보존). 입력 mutation 없음."""
        src = ob if isinstance(ob, dict) else {}
        payload: dict = {k: src[k] for k in _ROOT_KEYS if k in src}
        if "obligation_detail" in src:
            det = src["obligation_detail"]
            payload["obligation_detail"] = ObligationDetailV1.from_raw(det) if isinstance(det, dict) else det
        if "enrichment" in src:
            enr = src["enrichment"]
            payload["enrichment"] = ObligationEnrichmentV1.from_raw(enr) if isinstance(enr, dict) else enr
        return cls(**payload)
