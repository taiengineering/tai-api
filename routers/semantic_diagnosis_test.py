"""
semantic_diagnosis_test — D단계 의미절 직접 진단 테스트 라우터 (임시).

기존 진단 경로(anonymous_factory_service)는 무수정. 이 라우터는 의미절 직접 경로
(semantic_diagnosis_service)를 별도로 호출해 before/after 비교용 결과를 반환한다.
검증 후 정식 통합 시 제거.

보호: X-Internal-Secret 헤더.
실행: POST /admin/semantic-diagnosis  body=DiagnoseStep1Body
"""
from __future__ import annotations

import os
from fastapi import APIRouter, Header, HTTPException

from schemas.legal_engine import DiagnoseStep1Body
from db.supabase_client import get_supabase
from services.semantic_diagnosis_service import run_semantic_diagnosis

router = APIRouter()

_ALLOWED_SECTORS = frozenset({"BUILDING", "MANUFACTURING", "CONSTRUCTION", "SPECIAL_FACILITY", "INDUSTRIAL"})


@router.post("/admin/semantic-diagnosis")
def semantic_diagnosis(
    body: DiagnoseStep1Body,
    x_internal_secret: str = Header(None, alias="X-Internal-Secret"),
):
    if x_internal_secret != os.environ.get("INTERNAL_API_SECRET"):
        raise HTTPException(status_code=403, detail="forbidden")
    sb = get_supabase()
    try:
        result = run_semantic_diagnosis(sb, body, _ALLOWED_SECTORS)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"semantic diagnosis failed: {exc}")
    # 비교용 요약 + 상위 의무 표본만 반환(전체는 큼)
    return {
        "engine": result.get("engine_version"),
        "summary": result.get("summary"),
        "risk_level": result.get("risk_level"),
        "law_count": len(result.get("law_badges") or []),
        "semantic_direct": result.get("semantic_direct"),
        "sample_rules": (result.get("rules_table") or [])[:30],
    }
