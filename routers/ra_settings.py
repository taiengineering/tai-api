"""위험성평가 설정 API — 운영 파라미터 및 척도 (v1.0.0).

Goal: G-ms5zwv4v-b88c4a
설계: docs/ops/tai-risk-assessment/PLAN_risk-assessment-design_v2.md
스키마: docs/ops/tai-risk-assessment/WORKORDER_schema-legal-period-scale_v2.md

■ 이 라우터가 존재하는 이유
  산업안전보건법 제36조제4항이 위험성평가의 "방법, 절차 및 시기"를 전부 고용노동부장관
  고시에 위임한다. 고시(제2024-76호) 제28조는 3년마다 타당성을 재검토하도록 정해
  주기적 개정이 예정되어 있다. 또한 고시는 위험성 척도 수치를 규정하지 않고,
  제9조제2항이 "위험성의 수준과 그 판단 기준" 및 "허용 가능한 위험성 수준"을
  사업주가 사전에 확정하도록 위임한다.
  => 주기·기한·척도를 코드 상수로 두면 법 개정 시 전면 재작업이 발생한다.
     실제로 risk_assessments 라우터가 최초평가 기한을 "1년"으로 안내하고 있었고
     (현행 고시 제15조제1항은 "1개월이 되는 날까지 착수"), v1.2.0 에서 정정했다.

■ 법령 데이터 취급 원칙 (중요)
  법령 조문 원문은 법령엔진이 API 로만 관리한다. 이 모듈은 조문 텍스트를 저장하지 않으며
  law_article_ref 포인터만 보유한다. 원문이 필요하면 런타임에 법령 API 로 조회하고
  그 결과를 저장하지 않는다.

■ 스키마 미적용 상태 대응
  ra_policy_param / ra_scale 은 보호 경로(supabase/migrations) 정책상 오퍼레이터가 적용한다.
  적용 전에는 테이블이 없으므로, 조회 API 는 500 대신 fallback(내장 기본값)을 반환하고
  응답에 source="fallback" 을 표시한다. 쓰기 API 는 409 로 명확히 거절한다.

■ 인증·스코프 (2026-08-20)
  policy-params 는 전사 공통 법정 상수(참조데이터)이며 get_policy_param 이 내부 함수로
  호출하므로 공개 유지한다. 척도(scales)는 회사 데이터이므로 로그인 + 회사 스코프를 건다.

API:
  GET   /ra/policy-params            운영 파라미터 목록(현행) — 공개(참조)
  GET   /ra/policy-params/{code}     단건 — 공개(참조)
  GET   /ra/scales                   척도 목록(프리셋 + 회사 설정) — 자사 스코프
  POST  /ra/scales                   척도 생성(프리셋 복제 포함) — 토큰 회사 강제
  PUT   /ra/scales/{id}              척도 수정 — 자사 소유 확인
  GET   /ra/settings/health          스키마 적용 여부 점검 — 로그인
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import require_company_id, scoped_list_company, _ensure_own_company
from services.time import business_today

log = logging.getLogger(__name__)

router = APIRouter(prefix="/ra", tags=["위험성평가 설정"])

VERSION = "1.0.0"

# 스키마 미적용 시 사용할 내장 기본값.
# 값(value_num/value_unit)만 보유하며 조문 원문은 담지 않는다(법령 데이터 취급 원칙).
_FALLBACK_PARAMS: List[Dict[str, Any]] = [
    {"param_code": "INITIAL_DUE", "label": "최초평가 착수기한", "value_num": 1, "value_unit": "MONTH",
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 15, "clause": "1"},
     "note": "건설업은 실착공일 기산. 1개월 미만 작업·공사는 개시 후 지체 없이."},
    {"param_code": "PERIODIC_CYCLE", "label": "정기평가 주기", "value_num": 1, "value_unit": "YEAR",
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 15, "clause": "3"},
     "note": "전면 재실시가 아니라 적정성 재검토."},
    {"param_code": "CONTINUOUS_MONTHLY", "label": "상시평가 월간 요건", "value_num": 1, "value_unit": "MONTH",
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 15, "clause": "4-1"},
     "note": "발굴 + 위험성결정 + 감소대책 수립·실행까지 이루어져야 충족."},
    {"param_code": "CONTINUOUS_WEEKLY", "label": "상시평가 주간 요건", "value_num": 1, "value_unit": "WEEK",
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 15, "clause": "4-2"},
     "note": "참석자 직위 요건 있음. 도급 시 수급사 관리자 포함."},
    {"param_code": "CONTINUOUS_DAILY", "label": "상시평가 일간 요건", "value_num": None, "value_unit": "WORKDAY",
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 15, "clause": "4-3"},
     "note": "TBM 기록으로 충족."},
    {"param_code": "RETENTION", "label": "기록 보존기간", "value_num": 3, "value_unit": "YEAR",
     "law_article_ref": {"law_key": "007364_271485", "article_no": 37, "clause": "2"},
     "note": "기산점은 실시 시기별 평가 완료일."},
    {"param_code": "PREP_EXEMPT_HEADCOUNT", "label": "사전준비 생략 기준(상시근로자)", "value_num": 5, "value_unit": "PERSON",
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 8, "clause": "but"},
     "note": "미만 기준. 5인 이상은 사전준비 필수."},
    {"param_code": "PREP_EXEMPT_AMOUNT", "label": "사전준비 생략 기준(건설공사 금액)", "value_num": 100000000,
     "value_unit": "KRW", "applies_to": "CONSTRUCTION",
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 8, "clause": "but"},
     "note": "1억원 미만."},
    {"param_code": "MCA_HALFYEAR_CHECK", "label": "중처법 반기 점검 주기", "value_num": 1, "value_unit": "HALF_YEAR",
     "law_article_ref": {"law_key": "014159_277417", "article_no": 4, "clause": "3"},
     "note": "위험성평가 실시 + 결과 보고 시 갈음 가능."},
]

_MISSING_TABLE_HINTS = ("does not exist", "relation", "42p01", "schema cache", "not find the table")


def _is_missing_table(err: Exception) -> bool:
    s = str(err).lower()
    return any(h in s for h in _MISSING_TABLE_HINTS)


class ScaleBody(BaseModel):
    company_id: Optional[str] = None
    factory_id: Optional[str] = None
    method: str                                  # THREE_STEP | CHECKLIST | OPS | FREQ_SEV
    name: str
    levels_json: List[Dict[str, Any]] = []
    matrix_json: Optional[Dict[str, Any]] = None
    acceptable_max: Optional[str] = None
    acceptable_reason: Optional[str] = None
    law_article_ref: Optional[Dict[str, Any]] = None
    created_by: Optional[str] = None


class ScaleUpdateBody(BaseModel):
    name: Optional[str] = None
    levels_json: Optional[List[Dict[str, Any]]] = None
    matrix_json: Optional[Dict[str, Any]] = None
    acceptable_max: Optional[str] = None
    acceptable_reason: Optional[str] = None
    is_active: Optional[bool] = None


_ALLOWED_METHODS = ("THREE_STEP", "CHECKLIST", "OPS", "FREQ_SEV")


# ── 운영 파라미터 (공개 참조데이터) ──────────────────────────────────
@router.get("/policy-params")
def list_policy_params(
    on_date: Optional[str] = Query(None, description="기준일 YYYY-MM-DD. 기본값 오늘"),
    applies_to: Optional[str] = Query(None),
):
    """위험성평가 운영 파라미터(현행) 조회.

    effective_from <= 기준일 < effective_to 인 행을 반환한다.
    법 개정 시 종전 행이 닫히고 신규 행이 추가되므로, 과거 시점 판정도 재현 가능하다.
    전사 공통 법정 상수라 공개 유지(get_policy_param 이 내부 함수로 호출).
    """
    ref = on_date or business_today().isoformat()
    try:
        q = get_supabase().table("ra_policy_param").select("*").eq("is_active", True)
        q = q.lte("effective_from", ref)
        res = q.order("param_code").execute()
        rows = [r for r in (res.data or [])
                if not r.get("effective_to") or str(r["effective_to"]) > ref]
        if applies_to:
            rows = [r for r in rows if not r.get("applies_to") or r["applies_to"] == applies_to]
        return {"status": "success", "data": {"items": rows, "source": "db", "as_of": ref}}
    except Exception as e:  # noqa: BLE001
        if _is_missing_table(e):
            log.warning("[RA] ra_policy_param 미적용 — fallback 반환")
            rows = _FALLBACK_PARAMS
            if applies_to:
                rows = [r for r in rows if not r.get("applies_to") or r.get("applies_to") == applies_to]
            return {"status": "success",
                    "data": {"items": rows, "source": "fallback", "as_of": ref,
                             "notice": "ra_policy_param 스키마가 아직 적용되지 않아 내장 기본값을 반환합니다."}}
        raise HTTPException(status_code=500, detail=f"조회 실패: {e}")


@router.get("/policy-params/{param_code}")
def get_policy_param(param_code: str, on_date: Optional[str] = Query(None)):
    """단건 조회. 다른 모듈이 상수 대신 이 값을 쓰도록 한다."""
    payload = list_policy_params(on_date=on_date)  # type: ignore[arg-type]
    for r in payload["data"]["items"]:
        if r.get("param_code") == param_code:
            return {"status": "success", "data": {**r, "source": payload["data"]["source"]}}
    raise HTTPException(status_code=404, detail=f"파라미터를 찾을 수 없습니다: {param_code}")


# ── 척도 (회사 데이터 — 스코프) ─────────────────────────────────────
@router.get("/scales")
def list_scales(
    company_id: Optional[str] = Query(None),
    factory_id: Optional[str] = Query(None),
    include_presets: bool = Query(True),
    method: Optional[str] = Query(None),
    current: dict = Depends(get_current_user),
):
    """척도 목록. 회사 설정 + (옵션) 시스템 프리셋. 비-ALL 은 자사 척도만 + 프리셋."""
    sb = get_supabase()
    scoped_cid, deny_all = scoped_list_company(current, sb, company_id)
    company_id = scoped_cid              # 비-ALL=토큰회사, ALL=클라값(None=전체)
    only_presets = deny_all              # 무회사 비-ALL → 회사 척도 숨김(프리셋만)
    try:
        q = sb.table("ra_scale").select("*").eq("is_active", True)
        if method:
            q = q.eq("method", method)
        res = q.order("is_preset", desc=True).order("created_at").execute()
        rows = res.data or []

        out = []
        for r in rows:
            if r.get("is_preset"):
                if include_presets:
                    out.append(r)
                continue
            if only_presets:
                continue
            if company_id and r.get("company_id") != company_id:
                continue
            if factory_id and r.get("factory_id") not in (None, factory_id):
                continue
            out.append(r)
        return {"status": "success", "data": {"items": out, "source": "db"}}
    except Exception as e:  # noqa: BLE001
        if _is_missing_table(e):
            return {"status": "success",
                    "data": {"items": [], "source": "fallback",
                             "notice": "ra_scale 스키마가 아직 적용되지 않았습니다."}}
        raise HTTPException(status_code=500, detail=f"조회 실패: {e}")


@router.post("/scales")
def create_scale(body: ScaleBody, current: dict = Depends(get_current_user)):
    """척도 생성. 프리셋을 복제해 사업장 기준을 만드는 것이 표준 흐름이다.

    고시 제9조제2항 — 사업주는 위험성평가 실시 전에 위험성 수준과 판단기준,
    허용 가능한 위험성 수준을 확정해야 한다. 허용수준은 법에서 정한 기준 이상이어야 한다.
    """
    _forced = require_company_id(current, get_supabase())   # 비-ALL 토큰강제·무회사 403; ALL 은 토큰 company
    if _forced:
        body.company_id = _forced

    if body.method not in _ALLOWED_METHODS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 평가방법: {body.method}")
    if not body.company_id:
        raise HTTPException(status_code=400, detail="company_id 는 필수입니다(프리셋은 시스템만 생성).")
    if not body.levels_json:
        raise HTTPException(status_code=400, detail="levels_json(위험성 수준 정의)은 필수입니다.")
    if not body.acceptable_max:
        raise HTTPException(status_code=400, detail="acceptable_max(허용 가능한 위험성 수준)는 필수입니다.")

    codes = {str(l.get("code")) for l in body.levels_json if isinstance(l, dict)}
    if body.acceptable_max not in codes:
        raise HTTPException(status_code=400,
                            detail="acceptable_max 는 levels_json 의 code 중 하나여야 합니다.")

    row = {
        "company_id": body.company_id,
        "factory_id": body.factory_id,
        "method": body.method,
        "name": body.name,
        "levels_json": body.levels_json,
        "matrix_json": body.matrix_json,
        "acceptable_max": body.acceptable_max,
        "acceptable_reason": body.acceptable_reason,
        "law_article_ref": body.law_article_ref,
        "is_preset": False,
        "is_active": True,
        "version": 1,
        "created_by": body.created_by,
    }
    try:
        res = get_supabase().table("ra_scale").insert(row).execute()
    except Exception as e:  # noqa: BLE001
        if _is_missing_table(e):
            raise HTTPException(status_code=409,
                                detail="ra_scale 스키마가 아직 적용되지 않았습니다. 마이그레이션 적용 후 다시 시도하세요.")
        raise HTTPException(status_code=500, detail=f"생성 실패: {e}")
    if not res.data:
        raise HTTPException(status_code=500, detail="척도 생성에 실패했습니다.")
    return {"status": "success", "message": "척도가 생성되었습니다.", "data": res.data[0]}


@router.put("/scales/{scale_id}")
def update_scale(scale_id: str, body: ScaleUpdateBody, current: dict = Depends(get_current_user)):
    """척도 수정. 프리셋은 수정할 수 없다.

    판정 기준이 바뀌면 version 을 올린다. 완료된 평가는 당시 version 을 스냅샷 참조하므로
    과거 판정이 소급 변경되지 않는다.
    """
    payload = {k: v for k, v in body.dict().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")

    try:
        cur = get_supabase().table("ra_scale").select(
            "id, is_preset, version, levels_json, acceptable_max, company_id"
        ).eq("id", scale_id).limit(1).execute()
        if not cur.data:
            raise HTTPException(status_code=404, detail="척도를 찾을 수 없습니다.")
        row = cur.data[0]
        if row.get("is_preset"):
            raise HTTPException(status_code=403, detail="시스템 프리셋은 수정할 수 없습니다. 복제해 사용하세요.")
        _ensure_own_company(row.get("company_id"), current, get_supabase(), "척도를 찾을 수 없습니다.")

        levels = payload.get("levels_json", row.get("levels_json")) or []
        acc = payload.get("acceptable_max", row.get("acceptable_max"))
        codes = {str(l.get("code")) for l in levels if isinstance(l, dict)}
        if acc and codes and acc not in codes:
            raise HTTPException(status_code=400,
                                detail="acceptable_max 는 levels_json 의 code 중 하나여야 합니다.")

        # 판정에 영향을 주는 변경이면 version 증가
        if "levels_json" in payload or "acceptable_max" in payload or "matrix_json" in payload:
            payload["version"] = int(row.get("version") or 1) + 1

        res = get_supabase().table("ra_scale").update(payload).eq("id", scale_id).execute()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        if _is_missing_table(e):
            raise HTTPException(status_code=409, detail="ra_scale 스키마가 아직 적용되지 않았습니다.")
        raise HTTPException(status_code=500, detail=f"수정 실패: {e}")

    if not res.data:
        raise HTTPException(status_code=404, detail="척도를 찾을 수 없습니다.")
    return {"status": "success", "message": "수정되었습니다.", "data": res.data[0]}


# ── 상태 점검 ────────────────────────────────────────────────────────
@router.get("/settings/health")
def settings_health(current: dict = Depends(get_current_user)):
    """스키마 적용 여부 점검. 운영자가 마이그레이션 적용 결과를 확인하는 용도."""
    out: Dict[str, Any] = {}
    for t in ("ra_policy_param", "ra_scale"):
        try:
            r = get_supabase().table(t).select("id", count="exact").limit(1).execute()
            out[t] = {"applied": True, "rows": r.count or 0}
        except Exception as e:  # noqa: BLE001
            out[t] = {"applied": False, "reason": "table_missing" if _is_missing_table(e) else str(e)[:120]}
    ready = all(v.get("applied") for v in out.values())
    return {"status": "success",
            "data": {"ready": ready, "tables": out,
                     "next": None if ready else
                     "docs/ops/tai-risk-assessment/WORKORDER_schema-legal-period-scale_v2.md 의 SQL 적용 필요"}}
