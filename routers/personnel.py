"""
선임연결 관리 라우터 — v1.0.0

대상 테이블:
  - safety_personnel   : 개인기술자
  - safety_agencies    : 대행업체
  - verification_logs  : 검증 이력

엔드포인트 (prefix: /personnel)
  GET  /personnel/stats              전체 통계
  GET  /personnel/fee-calc           수수료 계산
  GET  /personnel/agencies           대행업체 목록
  POST /personnel/agencies           대행업체 등록
  PATCH /personnel/agencies/{id}     대행업체 수정
  GET  /personnel                    개인기술자 목록
  POST /personnel                    개인기술자 등록
  GET  /personnel/{id}               개인기술자 상세
  PATCH /personnel/{id}              개인기술자 수정
  POST /personnel/{id}/verify        검증 상태 변경
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone
from db.supabase_client import get_supabase

router = APIRouter(prefix="/personnel", tags=["선임연결"])

VERSION = "1.0.0"

# 개인기술자 수정 허용 필드
PATCH_PERSONNEL_ALLOWED = {
    "name", "phone", "tai_grade", "region_sido", "region_range_km",
    "monthly_fee_min", "monthly_fee_max", "max_slots",
    "verified_status", "is_active", "current_slots",
}

# 대행업체 수정 허용 필드
PATCH_AGENCY_ALLOWED = {
    "agency_name", "phone", "email", "region_sido",
    "max_clients", "current_clients", "specialties",
    "verified_status", "is_active",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────
# 1. GET /personnel/stats  전체 통계
# ※ /{id} 보다 먼저 선언
# ─────────────────────────────────────────────────────
@router.get("/stats")
async def get_personnel_stats():
    """개인기술자 + 대행업체 전체 통계"""
    supabase = get_supabase()
    try:
        # 개인기술자 집계
        p_res = supabase.table("safety_personnel").select(
            "id, employment_type, verified_status, is_active"
        ).execute()
        personnel = p_res.data or []

        # 대행업체 집계
        a_res = supabase.table("safety_agencies").select(
            "id, verified_status, is_active"
        ).execute()
        agencies = a_res.data or []

        personnel_total = len(personnel)
        agencies_total = len(agencies)
        approved_count = sum(
            1 for r in personnel + agencies if r.get("verified_status") == "APPROVED"
        )
        pending_count = sum(
            1 for r in personnel + agencies if r.get("verified_status") == "PENDING"
        )
        fulltime_count = sum(
            1 for r in personnel if r.get("employment_type") == "FULLTIME"
        )
        parttime_count = sum(
            1 for r in personnel if r.get("employment_type") == "PARTTIME"
        )
        active_personnel = sum(1 for r in personnel if r.get("is_active"))
        active_agencies = sum(1 for r in agencies if r.get("is_active"))

        return {
            "status": "success",
            "data": {
                "personnel_total": personnel_total,
                "agencies_total": agencies_total,
                "approved_count": approved_count,
                "pending_count": pending_count,
                "fulltime_count": fulltime_count,
                "parttime_count": parttime_count,
                "active_personnel": active_personnel,
                "active_agencies": active_agencies,
                "version": VERSION,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 2. GET /personnel/fee-calc  수수료 계산
# ※ /{id} 보다 먼저 선언
# ─────────────────────────────────────────────────────
@router.get("/fee-calc")
async def calc_fee(
    employment_type: str = Query(..., description="FULLTIME 또는 PARTTIME"),
    annual_salary: Optional[int] = Query(None, description="연봉 (원) — FULLTIME 시 필수"),
    monthly_fee: Optional[int] = Query(None, description="월 보수 (원) — PARTTIME 시 필수"),
):
    """수수료 계산 유틸"""
    try:
        if employment_type == "FULLTIME":
            if annual_salary is None:
                raise HTTPException(status_code=400, detail="FULLTIME은 annual_salary가 필요합니다.")
            fee = annual_salary * 0.15
        elif employment_type == "PARTTIME":
            if monthly_fee is None:
                raise HTTPException(status_code=400, detail="PARTTIME은 monthly_fee가 필요합니다.")
            fee = monthly_fee * 12 * 0.10
        else:
            raise HTTPException(status_code=400, detail="employment_type은 FULLTIME 또는 PARTTIME이어야 합니다.")

        fee_int = int(fee)
        fee_man = fee_int // 10000

        return {
            "status": "success",
            "data": {
                "employment_type": employment_type,
                "fee_amount": fee_int,
                "fee_label": f"{fee_man:,}만원",
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 3. GET /personnel/agencies  대행업체 목록
# ※ /{id} 보다 먼저 선언
# ─────────────────────────────────────────────────────
@router.get("/agencies")
async def list_agencies(
    region_sido: Optional[str] = Query(None, description="지역 시도 필터"),
    verified_status: Optional[str] = Query(None, description="검증 상태 필터"),
    search: Optional[str] = Query(None, description="업체명/이메일 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """대행업체 목록 조회"""
    supabase = get_supabase()
    try:
        query = supabase.table("safety_agencies").select(
            "*", count="exact"
        ).eq("is_active", True)

        if verified_status:
            query = query.eq("verified_status", verified_status)
        if search:
            query = query.or_(
                f"agency_name.ilike.%{search}%,email.ilike.%{search}%"
            )
        # region_sido는 ARRAY 타입이므로 contains 사용
        if region_sido:
            query = query.contains("region_sido", [region_sido])

        offset = (page - 1) * page_size
        query = query.order("created_at", desc=True).range(offset, offset + page_size - 1)
        res = query.execute()

        total = res.count or 0
        return {
            "status": "success",
            "data": {
                "items": res.data or [],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size if total else 0,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 4. POST /personnel/agencies  대행업체 등록
# ─────────────────────────────────────────────────────
@router.post("/agencies")
async def create_agency(body: dict):
    """대행업체 등록"""
    supabase = get_supabase()
    try:
        if not body.get("agency_name", "").strip():
            raise HTTPException(status_code=400, detail="agency_name은 필수입니다.")

        now = _now_iso()
        insert_data = {
            "agency_name":    body.get("agency_name"),
            "phone":          body.get("phone"),
            "email":          body.get("email"),
            "business_no":    body.get("business_no"),
            "license_no":     body.get("license_no"),
            "region_sido":    body.get("region_sido", []),
            "max_clients":    body.get("max_clients", 0),
            "current_clients": body.get("current_clients", 0),
            "specialties":    body.get("specialties", []),
            "verified_status": "PENDING",
            "match_count":    0,
            "review_score":   None,
            "is_active":      True,
            "created_at":     now,
            "updated_at":     now,
        }

        res = supabase.table("safety_agencies").insert(insert_data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="대행업체 등록에 실패했습니다.")

        return {
            "status": "success",
            "message": "대행업체가 등록됐습니다.",
            "data": res.data[0],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 5. PATCH /personnel/agencies/{agency_id}  대행업체 수정
# ─────────────────────────────────────────────────────
@router.patch("/agencies/{agency_id}")
async def update_agency(agency_id: str, body: dict):
    """대행업체 수정 (허용 필드만)"""
    supabase = get_supabase()
    try:
        update_data = {k: v for k, v in body.items() if k in PATCH_AGENCY_ALLOWED}
        if not update_data:
            raise HTTPException(status_code=400, detail="수정할 필드가 없습니다.")

        update_data["updated_at"] = _now_iso()

        res = supabase.table("safety_agencies").update(
            update_data
        ).eq("id", agency_id).execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="대행업체를 찾을 수 없습니다.")

        return {
            "status": "success",
            "message": "대행업체가 수정됐습니다.",
            "data": res.data[0],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 6. GET /personnel  개인기술자 목록
# ─────────────────────────────────────────────────────
@router.get("")
async def list_personnel(
    employment_type: Optional[str] = Query(None, description="FULLTIME / PARTTIME"),
    tai_grade: Optional[str] = Query(None, description="T1~T5"),
    region_sido: Optional[str] = Query(None, description="지역 시도"),
    verified_status: Optional[str] = Query(None, description="검증 상태"),
    qualification_type: Optional[str] = Query(None, description="자격 종류"),
    search: Optional[str] = Query(None, description="이름/이메일 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """개인기술자 목록 조회 (페이지네이션 + 필터)"""
    supabase = get_supabase()
    try:
        query = supabase.table("safety_personnel").select(
            "*", count="exact"
        ).eq("is_active", True)

        if employment_type:
            query = query.eq("employment_type", employment_type)
        if tai_grade:
            query = query.eq("tai_grade", tai_grade)
        if region_sido:
            query = query.eq("region_sido", region_sido)
        if verified_status:
            query = query.eq("verified_status", verified_status)
        if qualification_type:
            query = query.eq("qualification_type", qualification_type)
        if search:
            query = query.or_(
                f"name.ilike.%{search}%,email.ilike.%{search}%"
            )

        offset = (page - 1) * page_size
        query = query.order("created_at", desc=True).range(offset, offset + page_size - 1)
        res = query.execute()

        total = res.count or 0
        return {
            "status": "success",
            "data": {
                "items": res.data or [],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size if total else 0,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 7. POST /personnel  개인기술자 등록
# ─────────────────────────────────────────────────────
@router.post("")
async def create_personnel(body: dict):
    """개인기술자 등록"""
    supabase = get_supabase()
    try:
        if not body.get("name", "").strip():
            raise HTTPException(status_code=400, detail="name은 필수입니다.")
        if not body.get("employment_type") in ("FULLTIME", "PARTTIME"):
            raise HTTPException(status_code=400, detail="employment_type은 FULLTIME 또는 PARTTIME이어야 합니다.")

        now = _now_iso()
        insert_data = {
            "name":                  body.get("name"),
            "phone":                 body.get("phone"),
            "email":                 body.get("email"),
            "employment_type":       body.get("employment_type"),
            "qualification_type":    body.get("qualification_type"),
            "qualification_grade":   body.get("qualification_grade"),
            "qualification_no":      body.get("qualification_no"),
            "qualification_verified": False,
            "career_years":          body.get("career_years", 0),
            "tai_grade":             body.get("tai_grade"),
            "region_sido":           body.get("region_sido"),
            "region_range_km":       body.get("region_range_km", 50),
            "industry_specialties":  body.get("industry_specialties", []),
            "current_slots":         0,
            "max_slots":             body.get("max_slots", 1),
            "monthly_fee_min":       body.get("monthly_fee_min"),
            "monthly_fee_max":       body.get("monthly_fee_max"),
            "verified_status":       "PENDING",
            "match_count":           0,
            "review_score":          None,
            "is_active":             True,
            "created_at":            now,
            "updated_at":            now,
        }
        # None 값 제거
        insert_data = {k: v for k, v in insert_data.items() if v is not None}

        res = supabase.table("safety_personnel").insert(insert_data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="개인기술자 등록에 실패했습니다.")

        return {
            "status": "success",
            "message": "개인기술자가 등록됐습니다.",
            "data": res.data[0],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 8. GET /personnel/{personnel_id}  개인기술자 상세
# ─────────────────────────────────────────────────────
@router.get("/{personnel_id}")
async def get_personnel(personnel_id: str):
    """개인기술자 단건 상세"""
    supabase = get_supabase()
    try:
        res = supabase.table("safety_personnel").select("*").eq(
            "id", personnel_id
        ).limit(1).execute()

        rows = res.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="기술자를 찾을 수 없습니다.")

        return {"status": "success", "data": rows[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 9. PATCH /personnel/{personnel_id}  개인기술자 수정
# ─────────────────────────────────────────────────────
@router.patch("/{personnel_id}")
async def update_personnel(personnel_id: str, body: dict):
    """개인기술자 수정 (허용 필드만)"""
    supabase = get_supabase()
    try:
        update_data = {k: v for k, v in body.items() if k in PATCH_PERSONNEL_ALLOWED}
        if not update_data:
            raise HTTPException(status_code=400, detail="수정할 필드가 없습니다.")

        update_data["updated_at"] = _now_iso()

        res = supabase.table("safety_personnel").update(
            update_data
        ).eq("id", personnel_id).execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="기술자를 찾을 수 없습니다.")

        return {
            "status": "success",
            "message": "기술자 정보가 수정됐습니다.",
            "data": res.data[0],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 10. POST /personnel/{personnel_id}/verify  검증 상태 변경
# ─────────────────────────────────────────────────────
@router.post("/{personnel_id}/verify")
async def verify_personnel(personnel_id: str, body: dict):
    """
    검증 상태 변경 + verification_logs 이력 저장.
    body: { verified_status: 'APPROVED'|'REJECTED'|'PENDING', note: '...' }
    """
    supabase = get_supabase()
    try:
        verified_status = body.get("verified_status")
        if verified_status not in ("APPROVED", "REJECTED", "PENDING", "SUSPENDED"):
            raise HTTPException(status_code=400, detail="verified_status가 올바르지 않습니다.")

        now = _now_iso()

        # safety_personnel 상태 업데이트
        p_res = supabase.table("safety_personnel").update({
            "verified_status": verified_status,
            "updated_at": now,
        }).eq("id", personnel_id).execute()

        if not p_res.data:
            raise HTTPException(status_code=404, detail="기술자를 찾을 수 없습니다.")

        # verification_logs 이력 저장
        log_data = {
            "target_type":      "PERSONNEL",
            "target_id":        personnel_id,
            "verification_step": "STATUS_CHANGE",
            "status":           verified_status,
            "note":             body.get("note", ""),
            "created_at":       now,
        }
        supabase.table("verification_logs").insert(log_data).execute()

        return {
            "status": "success",
            "message": f"검증 상태가 {verified_status}로 변경됐습니다.",
            "data": {
                "personnel_id":    personnel_id,
                "verified_status": verified_status,
                "updated_at":      now,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
