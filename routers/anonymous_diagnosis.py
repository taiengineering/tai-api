"""
익명 무료 법령진단 — DB 저장 + public_token + claim
POST /anonymous-diagnosis          생성 (법령엔진 step1 재사용)
GET  /anonymous-diagnosis/{token}  조회
  - 기본(Nexas 등): 비로그인 partial만; 로그인+귀속 시 full
  - 구버전 taieng.co.kr: ?tai_legacy_public=1 로 full (로그인 불필요)
POST /anonymous-diagnosis/{token}/claim  로그인 사용자 귀속
GET  /anonymous-diagnosis/{token}/recommend-plan  BE-09 플랜 추천
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from routers.legal_engine import DiagnoseStep1Body, diagnose_step1
from routers.legal_engine import ENGINE_VERSION as LEGAL_ENGINE_VERSION

# BE-09: BE-08 추천 함수 재사용 (코드 중복 금지)
from routers.diagnosis_plan_recommend import (
    _recommend_industry,
    _recommend_building,
    _recommend_construction,
    _build_alternatives,
    _build_comparison,
    _effective_obligation_count,
    VERSION as PLAN_RECOMMEND_VERSION,
)

router = APIRouter(prefix="/anonymous-diagnosis", tags=["익명 무료진단"])

RULE_VERSION = "master_building_legal_rules:v1"
SOURCE_TYPE_DEFAULT = "site_free"
TTL_DAYS = 7

# BE-09: 익명 진단 sector → 추천 엔진 sector 정규화 매핑
# MANUFACTURING(법령엔진 내부 코드) → INDUSTRY(추천 엔진)
# SPECIAL_FACILITY(기타시설)        → BUILDING(추천 엔진)
_SECTOR_NORMALIZE: Dict[str, str] = {
    "MANUFACTURING":   "INDUSTRY",
    "SPECIAL_FACILITY": "BUILDING",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _partial_from_full(full: Dict[str, Any]) -> Dict[str, Any]:
    rules = full.get("rules") or []
    return {
        "risk_level": full.get("risk_level"),
        "summary": full.get("summary"),
        "applicable_count": full.get("applicable_count"),
        "sector": full.get("sector"),
        "evaluated_at": full.get("evaluated_at"),
        "key_obligations": (full.get("key_obligations") or [])[:6],
        "rules_preview": rules[:12],
        "law_badges": (full.get("law_badges") or [])[:18],
        "construction_summary": full.get("construction_summary"),
        "message": "일부 결과만 표시됩니다. 전체 법령·의무 목록은 로그인 후 확인할 수 있습니다.",
    }


# site_kind: construction | manufacturing | building | other
# scale: small | medium | large — 면적·공사규모 가이드용
SCALE_PRESETS: Dict[str, Dict[str, Any]] = {
    "small": {
        "floor_area": 400.0,
        "total_floor_area": 400.0,
        "contract_amount_eok": 1.0,
        "employee_hint": 12,
    },
    "medium": {
        "floor_area": 2800.0,
        "total_floor_area": 2800.0,
        "contract_amount_eok": 6.0,
        "employee_hint": 45,
    },
    "large": {
        "floor_area": 12000.0,
        "total_floor_area": 12000.0,
        "contract_amount_eok": 18.0,
        "employee_hint": 150,
    },
}

SECTOR_BY_KIND = {
    "construction": "CONSTRUCTION",
    "manufacturing": "MANUFACTURING",
    "building": "BUILDING",
    "other": "SPECIAL_FACILITY",
}


class AnonymousDiagnosisCreate(BaseModel):
    site_kind: str = Field(..., description="construction | manufacturing | building | other")
    scale: str = Field(..., description="small | medium | large")
    workers: int = Field(..., ge=1, le=50000, description="상시 인원·근로자 수")
    region: str = Field("", description="지역(시/도 등)")


def _build_step1_body(body: AnonymousDiagnosisCreate) -> DiagnoseStep1Body:
    sk = body.site_kind.strip().lower()
    if sk not in SECTOR_BY_KIND:
        raise HTTPException(status_code=422, detail="site_kind가 올바르지 않습니다.")
    sc = body.scale.strip().lower()
    if sc not in SCALE_PRESETS:
        raise HTTPException(status_code=422, detail="scale이 올바르지 않습니다.")
    sector = SECTOR_BY_KIND[sk]
    preset = SCALE_PRESETS[sc]
    workers = int(body.workers)
    region = (body.region or "").strip()

    inp: Dict[str, Any] = {
        "region": region,
        "site_kind": sk,
        "scale": sc,
        "anonymous_flow": True,
    }

    if sector == "CONSTRUCTION":
        return DiagnoseStep1Body(
            factory_id=None,
            sector=sector,
            input=inp,
            construction_type="건축",
            contract_amount_eok=float(preset["contract_amount_eok"]),
            direct_workers=workers,
            subcon_workers=0,
        )
    if sector == "MANUFACTURING":
        return DiagnoseStep1Body(
            factory_id=None,
            sector=sector,
            input=inp,
            worker_count=workers,
            employee_count=workers,
            floor_area=float(preset["floor_area"]),
            total_floor_area=float(preset["total_floor_area"]),
            ksic_major="",
        )
    if sector == "BUILDING":
        return DiagnoseStep1Body(
            factory_id=None,
            sector=sector,
            input=inp,
            building_use_type="사무실",
            floor_area=float(preset["floor_area"]),
            total_floor_area=float(preset["total_floor_area"]),
            worker_count=workers,
            employee_count=workers,
            floor_count=5,
        )
    # SPECIAL_FACILITY
    return DiagnoseStep1Body(
        factory_id=None,
        sector=sector,
        input=inp,
        facility_type="기타시설",
        floor_area=float(preset["floor_area"]),
        total_floor_area=float(preset["total_floor_area"]),
        worker_count=workers,
        employee_count=workers,
    )


@router.post("")
async def create_anonymous_diagnosis(body: AnonymousDiagnosisCreate):
    step1_body = _build_step1_body(body)
    eng = await diagnose_step1(step1_body)
    if eng.get("status") != "success":
        raise HTTPException(status_code=500, detail="진단 실행 실패")
    full_result = eng["data"]
    partial = _partial_from_full(full_result)

    token = str(uuid.uuid4())
    expires = (_now() + timedelta(days=TTL_DAYS)).isoformat()
    created = _now().isoformat()

    input_snapshot: Dict[str, Any] = {
        "site_kind": body.site_kind,
        "scale": body.scale,
        "workers": body.workers,
        "region": body.region,
        "sector": full_result.get("sector"),
    }

    row = {
        "public_token": token,
        "input_data": input_snapshot,
        "partial_result": partial,
        "full_result": full_result,
        "created_at": created,
        "expires_at": expires,
        "claimed_user_id": None,
        "status": "ACTIVE",
        "source_type": SOURCE_TYPE_DEFAULT,
        "engine_version": LEGAL_ENGINE_VERSION,
        "rule_version": RULE_VERSION,
    }

    supabase = get_supabase()
    try:
        res = supabase.table("anonymous_diagnosis_results").insert(row).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="DB 저장 실패")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {e!s}")

    return {
        "status": "success",
        "publicToken": token,
        "partialResult": partial,
        "hasFullResult": True,
        "expiresAt": expires,
    }


ADMIN_ALLOWED_STATUS = frozenset({"ACTIVE", "CLAIMED", "EXPIRED"})


class AdminAnonDiagPatch(BaseModel):
    status: Optional[str] = Field(None, description="ACTIVE | CLAIMED | EXPIRED")


# ── 관리자: 전체 목록 조회 (/{token} 보다 먼저 등록) ─────────────────
@router.get("/admin/list")
def list_anonymous_diagnoses(
    page: int = 1,
    size: int = 20,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다.")
    supabase = get_supabase()
    q = supabase.table("anonymous_diagnosis_results").select(
        "id,public_token,input_data,created_at,expires_at,claimed_user_id,status,source_type",
        count="exact",
    )
    if status:
        q = q.eq("status", status)
    kw = (keyword or "").strip()
    if kw:
        q = q.ilike("public_token", f"%{kw}%")
    offset = (page - 1) * size
    res = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    return {
        "status": "success",
        "data": {
            "items": res.data,
            "total": res.count,
            "page": page,
            "size": size,
            "total_pages": -(-res.count // size) if res.count else 0,
        },
    }


@router.get("/admin/detail/{record_id}")
def admin_get_anonymous_diagnosis_detail(
    record_id: str,
    current_user: dict = Depends(get_current_user),
):
    """관리자: 단건 전체 필드 (partial/full JSON 포함)."""
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다.")
    supabase = get_supabase()
    res = (
        supabase.table("anonymous_diagnosis_results")
        .select("*")
        .eq("id", record_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="레코드를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/admin/{record_id}")
def admin_patch_anonymous_diagnosis(
    record_id: str,
    body: AdminAnonDiagPatch,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다.")
    if body.status is None:
        raise HTTPException(status_code=422, detail="변경할 status가 필요합니다.")
    if body.status not in ADMIN_ALLOWED_STATUS:
        raise HTTPException(status_code=422, detail="허용되지 않는 status입니다.")
    supabase = get_supabase()
    res = (
        supabase.table("anonymous_diagnosis_results")
        .update({"status": body.status})
        .eq("id", record_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="레코드를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


# ── 만료 레코드 일괄 처리 (스케줄러 호출용) ─────────────────────────
@router.post("/admin/expire-stale")
def expire_stale_records():
    """expires_at이 지난 ACTIVE 레코드를 EXPIRED로 변경한다."""
    supabase = get_supabase()
    now_iso = _now().isoformat()
    res = (
        supabase.table("anonymous_diagnosis_results")
        .update({"status": "EXPIRED"})
        .eq("status", "ACTIVE")
        .lt("expires_at", now_iso)
        .execute()
    )
    count = len(res.data) if res.data else 0
    return {"status": "success", "expired_count": count}


# ── 관리자: 삭제 ────────────────────────────────────────────────────
@router.delete("/admin/{record_id}")
def delete_anonymous_diagnosis(
    record_id: str,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다.")
    supabase = get_supabase()
    res = (
        supabase.table("anonymous_diagnosis_results")
        .delete()
        .eq("id", record_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="레코드를 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제되었습니다."}


# ── 토큰 조회 (path param — 반드시 /admin/* 라우트 아래에 위치) ──────
def _fetch_row(token: str) -> Dict[str, Any]:
    supabase = get_supabase()
    res = (
        supabase.table("anonymous_diagnosis_results")
        .select("*")
        .eq("public_token", token)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="진단 결과를 찾을 수 없습니다.")
    row = res.data[0]
    exp = row.get("expires_at")
    if exp:
        try:
            exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if _now() > exp_dt:
                raise HTTPException(status_code=410, detail="만료된 진단 결과입니다.")
        except HTTPException:
            raise
        except Exception:
            pass
    return row


# ── BE-09: 토큰 기반 플랜 추천 (/{token} 보다 먼저 등록) ─────────────
@router.get("/{token}/recommend-plan")
def recommend_plan_by_token(token: str):
    """
    BE-09: 익명 진단 토큰 기반 SaaS 플랜 추천.

    BE-08(_recommend_* 함수)을 그대로 재사용하며 추가 코드 중복 없음.

    sector 보정:
      MANUFACTURING   → INDUSTRY  (법령엔진 내부 코드 → 추천 엔진 코드)
      SPECIAL_FACILITY → BUILDING (기타시설 → 건물 플랜)

    입력 데이터 소스:
      full_result.headline.severity (없으면 risk_level)
      full_result.key_obligations[] 길이 (없으면 applicable_count)
      input_data.workers
      full_result.roi.annual_penalty_risk_krw
    """
    row = _fetch_row(token)

    full: Dict[str, Any] = row.get("full_result") or {}
    input_data: Dict[str, Any] = row.get("input_data") or {}

    # ── sector 추출 & 보정 ──────────────────────────────────────────
    raw_sector = str(
        input_data.get("sector")
        or full.get("sector")
        or ""
    ).upper()
    sector = _SECTOR_NORMALIZE.get(raw_sector, raw_sector)

    if sector not in ("INDUSTRY", "BUILDING", "CONSTRUCTION"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"추천을 지원하지 않는 섹터입니다: '{raw_sector}'. "
                "무료 진단 후 결과를 확인해 주세요."
            ),
        )

    # ── 입력 변수 추출 ──────────────────────────────────────────────
    # severity: headline.severity 우선, 없으면 risk_level
    headline: Dict[str, Any] = full.get("headline") or {}
    severity: str = str(
        headline.get("severity")
        or full.get("risk_level")
        or "LOW"
    ).upper()

    # obl_cnt: key_obligations 배열 길이 우선, 없으면 applicable_count
    key_obl = full.get("key_obligations") or []
    obl_cnt: int = (
        len(key_obl)
        if key_obl
        else int(full.get("applicable_count") or 0)
    )

    workers: int = int(input_data.get("workers") or 0)

    penalty_risk_krw: int = int(
        (full.get("roi") or {}).get("annual_penalty_risk_krw") or 0
    )

    # ── BE-08 추천 함수 재사용 ──────────────────────────────────────
    if sector == "INDUSTRY":
        plan_code, reasons = _recommend_industry(severity, obl_cnt, workers)
    elif sector == "BUILDING":
        plan_code, reasons = _recommend_building(severity, obl_cnt, workers)
    else:  # CONSTRUCTION
        plan_code, reasons = _recommend_construction(severity, obl_cnt, workers)

    from routers.diagnosis_plan_recommend import _PLANS  # 지역 import (순환 방지)
    plan_info = _PLANS[plan_code]

    return {
        "status": "success",
        "version": PLAN_RECOMMEND_VERSION,
        "source": "anonymous_token",
        "token": token,
        "sector": sector,
        "sector_raw": raw_sector,
        "input_summary": {
            "severity":  severity,
            "obl_count": obl_cnt,
            "workers":   workers,
        },
        "recommended": {
            "plan_code":  plan_code,
            "plan_name":  plan_info["name"],
            "monthly_krw": plan_info["monthly"] if not plan_info["is_custom"] else None,
            "is_custom":  plan_info["is_custom"],
            "pricing_note": "맞춤 견적 문의" if plan_info["is_custom"] else f"월 {plan_info['monthly']:,}원 (부가세 별도)",
        },
        "reasons":      reasons,
        "alternatives": _build_alternatives(sector, plan_code),
        "comparison":   _build_comparison(plan_code, penalty_risk_krw),
        "cta": {
            "primary":   {"label": "지금 시작하기",       "action": "go_pricing", "plan_code": plan_code},
            "secondary": {"label": "전체 요금제 비교하기", "action": "go_pricing_all"},
            "signup":    {"label": "회원가입 후 상세 진단", "action": "go_register"},
        },
    }


@router.get("/{token}")
def get_anonymous_diagnosis(
    token: str,
    tai_legacy_public: Optional[str] = Query(
        None,
        description="구버전 taieng.co.kr 전용: 1 이면 로그인 없이 full_result 반환",
    ),
    authorization: Optional[str] = Header(None),
):
    row = _fetch_row(token)
    partial = row.get("partial_result") or {}
    full = row.get("full_result") or {}
    claimed = row.get("claimed_user_id")

    # 구버전 루트 도메인(taieng.co.kr) 정적 사이트만 이 쿼리를 붙여 호출하도록 둔다. Nexas는 붙이지 않음.
    legacy_public_full = tai_legacy_public == "1"

    can_full = False
    if legacy_public_full:
        can_full = True
    elif authorization and authorization.startswith("Bearer "):
        try:
            user = get_current_user(authorization)
            uid = user.get("id")
            if claimed and str(claimed) == str(uid):
                can_full = True
        except HTTPException:
            can_full = False

    if can_full:
        return {
            "status": "success",
            "data": {
                "publicToken": token,
                "partialResult": partial,
                "fullResult": full,
                "canViewFull": True,
                "claimed": bool(claimed),
                "expiresAt": row.get("expires_at"),
            },
        }

    return {
        "status": "success",
        "data": {
            "publicToken": token,
            "partialResult": partial,
            "fullResult": None,
            "canViewFull": False,
            "claimed": bool(claimed),
            "expiresAt": row.get("expires_at"),
        },
    }


@router.post("/{token}/claim")
def claim_anonymous_diagnosis(
    token: str,
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    user = get_current_user(authorization)
    uid = user.get("id")
    row = _fetch_row(token)
    claimed = row.get("claimed_user_id")

    if claimed and str(claimed) != str(uid):
        raise HTTPException(status_code=403, detail="이미 다른 계정에 연결된 진단입니다.")

    if not claimed:
        supabase = get_supabase()
        supabase.table("anonymous_diagnosis_results").update(
            {"claimed_user_id": str(uid), "status": "CLAIMED"}
        ).eq("public_token", token).execute()

    return {"status": "success", "message": "진단 결과가 내 계정에 연결되었습니다.", "publicToken": token}
