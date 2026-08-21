"""법령 판정 엔진 라우터."""
from fastapi import APIRouter, HTTPException, Query, Header
from typing import Optional

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_factory_own
from schemas.legal_engine import DiagnoseStep1Body, DiagnoseStep2Body, DiagnoseStep3Body
from services import legal_engine_svc
from services.legal_v510_svc import run_diagnose_step1_v510
from services.legal_context import _factory_to_context, _survey_data_to_context
from services.legal_format import CYCLE_CODE_MAP
from services.legal_helpers import (
    _now_iso,
    _parse_survey_data,
    get_construction_amount_threshold,
    get_effective_worker_count,
)

router = APIRouter(prefix="/legal-engine", tags=["법령엔진"])

# v5.8.0 (2026-04-23): 조문 본문 연결 (rule_article_mapping 활용)
#   - Phase A-1: fetch_article_contexts 헬퍼 + format_rule_result_db 확장
#   - Phase A-2: legal_runtime + legal_step1_builder 통합
# v5.7.0: BE-11 데이터 품질 개선
ENGINE_VERSION = "5.8.0"

# 입력표준(INDUSTRIAL)과 엔진/룰표준(MANUFACTURING)을 모두 허용한다.
# 산업 sector는 입력단에서 INDUSTRIAL, 룰조회/판정 경계에서 MANUFACTURING으로 변환된다.
STEP1_ALLOWED_SECTORS = ["BUILDING", "MANUFACTURING", "INDUSTRIAL", "CONSTRUCTION", "SPECIAL_FACILITY"]


@router.post("/apply/{factory_id}")
async def apply_legal_engine(factory_id: str, body: Optional[dict] = None, mode: str = Query("all")):
    supabase = get_supabase()
    if body and body.get("mode"):
        mode = body["mode"]
    try:
        return await legal_engine_svc.run_apply_engine(
            supabase,
            factory_id,
            mode,
            ENGINE_VERSION,
            _now_iso,
            _factory_to_context,
            get_effective_worker_count,
            get_construction_amount_threshold,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/apply-quote/{quote_id}")
async def apply_legal_engine_from_quote(quote_id: str):
    supabase = get_supabase()
    try:
        return legal_engine_svc.run_apply_quote(supabase, quote_id, ENGINE_VERSION, _parse_survey_data, _survey_data_to_context, _now_iso)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/diagnose/step1")
async def diagnose_step1(body: DiagnoseStep1Body, authorization: Optional[str] = Header(None)):
    # v510 Canonical Runtime: adapter + enrichment + obligation_contract
    supabase = get_supabase()
    # P13 (2026-08-21): factory_id 로 저장 시설 프로필을 끌어오는 경로는 소유 검증을 요구한다.
    #   factory_id 미지정(인라인 무료진단)은 공개로 유지 — 무료진단 퍼널 불변.
    #   존재만 확인하던 종전 방식은 타사 factory_id 로 진단 결과를 열람할 여지가 있었다.
    if body.factory_id:
        current = get_current_user(authorization)
        _ensure_factory_own(supabase, body.factory_id, current)
    try:
        return run_diagnose_step1_v510(supabase, body, STEP1_ALLOWED_SECTORS, "v5.10")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/quote-result/{quote_id}")
async def get_legal_result_from_quote(quote_id: str):
    supabase = get_supabase()
    try:
        return legal_engine_svc.run_get_legal_result_from_quote(supabase, quote_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/result/{factory_id}")
async def get_legal_result(factory_id: str, mode: str = Query("all")):
    supabase = get_supabase()
    try:
        return legal_engine_svc.run_get_legal_result(supabase, factory_id, mode)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/summary/{factory_id}")
async def get_legal_summary(factory_id: str):
    supabase = get_supabase()
    return legal_engine_svc.run_get_legal_summary(supabase, factory_id)


@router.post("/create-inspection-sets/{factory_id}")
async def create_inspection_sets_from_legal(factory_id: str):
    supabase = get_supabase()
    try:
        return legal_engine_svc.run_create_inspection_sets_from_legal(supabase, factory_id, CYCLE_CODE_MAP)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/debug/context/{quote_id}")
async def debug_quote_context(quote_id: str):
    supabase = get_supabase()
    try:
        return legal_engine_svc.run_debug_quote_context(supabase, quote_id, _parse_survey_data, _survey_data_to_context)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/diagnose/step2")
def diagnose_step2(body: DiagnoseStep2Body):
    # LEGACY - ISOLATED: 구형 엔진 경로. runtime 전환 완료 후 제거 대상.
    supabase = get_supabase()
    return legal_engine_svc.run_diagnose_step2(supabase, body, ENGINE_VERSION)


@router.post("/diagnose/step3")
def diagnose_step3(body: DiagnoseStep3Body):
    # LEGACY - ISOLATED: 구형 엔진 경로. runtime 전환 완료 후 제거 대상.
    supabase = get_supabase()
    if not body.factory_id:
        raise HTTPException(status_code=400, detail='factory_id 필수')
    return legal_engine_svc.run_diagnose_step3(supabase, body, ENGINE_VERSION)


@router.get("/diagnose/{factory_id}/latest")
def get_latest_diagnosis(factory_id: str):
    supabase = get_supabase()
    try:
        return legal_engine_svc.run_get_latest_diagnosis(supabase, factory_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnose/{factory_id}/history")
def get_diagnosis_history(factory_id: str, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50)):
    supabase = get_supabase()
    return legal_engine_svc.run_get_diagnosis_history(supabase, factory_id, page, page_size)
