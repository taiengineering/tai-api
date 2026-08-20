"""
이창 보고서 조치사항(Corrective Actions) 관리 라우터 — v1.2.0

v1.2.0 (2026-08-20):
  [SEC] 인증·회사 스코프 (Wave3, 직접MCP)
    - GET 목록: factory_id 주면 시설 소유확인, 아니면 회사 스코프(company_id).
      비-ALL·무회사는 빈 결과. ALL 은 company_id 선택 필터.
    - POST: require_company_id 로 비-ALL 은 토큰 company_id 강제(클라 값 무시, P13).
      factory_id 주면 시설 소유확인.
    - PATCH: 대상 행 company_id 소유확인(_ensure_own_company) 후 수정.

v1.1.0 (2026-04-07):
  [FIX] 기존 테이블 구조 대응
    - status_code (기존) ↔ status (프론트 기대) 양방향 정규화
    - assigned_user_id (기존) ↔ assignee_id (프론트 기대) 정규화
    - 신규 컬럼(severity, location, asset_name 등) ALTER로 추가 완료
  [FIX] GET 응답에 status 필드 보장 (status_code 있으면 status로 매핑)

corrective_actions 테이블 컬럼:
  id, defect_id, assigned_user_id, status_code, description,
  factory_id, company_id, location, asset_name, severity,
  due_date, action_plan, action_result, completed_at,
  created_by, created_at, updated_at, status

API:
  GET    /corrective-actions   목록 조회 (factory_id/status/severity 필터)
  POST   /corrective-actions   등록
  PATCH  /corrective-actions/{id}  수정
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import (
    require_company_id,
    _ensure_own_company,
    _ensure_factory_own,
    _scope,
    _is_admin,
)

router = APIRouter(prefix="/corrective-actions", tags=["이창보고서"])

VERSION = "1.2.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    DB 응답 정규화:
    - status_code → status (프론트 기대 필드명)
    - assigned_user_id → assignee_id (프론트 기대 필드명)
    두 컬럼 모두 응답에 포함 (하위호환)
    """
    if row is None:
        return row
    # status 정규화
    if "status" not in row or row.get("status") is None:
        row["status"] = row.get("status_code", "OPEN")
    # status_code 동기화
    if "status_code" not in row or row.get("status_code") is None:
        row["status_code"] = row.get("status", "OPEN")
    # assignee_id 정규화
    if "assignee_id" not in row or row.get("assignee_id") is None:
        row["assignee_id"] = row.get("assigned_user_id")
    return row


# ── Pydantic 모델 ─────────────────────────────────────────────

class CorrectiveActionCreate(BaseModel):
    factory_id:   Optional[str] = None
    company_id:   Optional[str] = None
    description:  str
    location:     Optional[str] = None
    asset_name:   Optional[str] = None
    severity:     Optional[str] = "MEDIUM"   # HIGH / MEDIUM / LOW
    assignee_id:  Optional[str] = None       # → assigned_user_id
    due_date:     Optional[str] = None       # YYYY-MM-DD
    action_plan:  Optional[str] = None
    status:       Optional[str] = "OPEN"     # OPEN / IN_PROGRESS / COMPLETED / CANCELLED
    created_by:   Optional[str] = None
    defect_id:    Optional[str] = None       # 기존 defect 연결


class CorrectiveActionUpdate(BaseModel):
    status:         Optional[str] = None
    action_result:  Optional[str] = None
    action_plan:    Optional[str] = None
    assignee_id:    Optional[str] = None
    due_date:       Optional[str] = None
    severity:       Optional[str] = None
    location:       Optional[str] = None
    asset_name:     Optional[str] = None
    completed_at:   Optional[str] = None


# ── GET /corrective-actions ──────────────────────────────────

@router.get("")
def list_corrective_actions(
    factory_id:  Optional[str] = Query(None),
    company_id:  Optional[str] = Query(None),
    status:      Optional[str] = Query(None),
    severity:    Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(200, ge=1, le=500),
    current: dict = Depends(get_current_user),
):
    """
    이창 보고서 목록 조회.
    응답 정규화: status_code → status, assigned_user_id → assignee_id
    """
    supabase = get_supabase()
    q = supabase.table("corrective_actions").select("*", count="exact")

    # ── 인증·회사 스코프 (P13) ──
    # factory_id 지정 → 시설 소유확인 후 시설 스코프
    # 그 외 비-ALL → 토큰 company_id 스코프(무회사는 빈 결과)
    # ALL → company_id 선택 필터(미지정 시 전사)
    if factory_id:
        _ensure_factory_own(supabase, factory_id, current)
        q = q.eq("factory_id", factory_id)
    elif not _is_admin(_scope(supabase, current.get("role_code"))):
        cid = current.get("company_id")
        if not cid:
            return {
                "status": "success",
                "data": {
                    "items":       [],
                    "total":       0,
                    "page":        page,
                    "size":        size,
                    "total_pages": 0,
                },
            }
        q = q.eq("company_id", cid)
    elif company_id:
        q = q.eq("company_id", company_id)

    if severity:    q = q.eq("severity",     severity)

    # status 필터: status 또는 status_code 둘 다 체크
    if status:
        q = q.or_(f"status.eq.{status},status_code.eq.{status}")

    # assignee_id 필터: assignee_id 또는 assigned_user_id
    if assignee_id:
        q = q.or_(f"assignee_id.eq.{assignee_id},assigned_user_id.eq.{assignee_id}")

    offset = (page - 1) * size
    res    = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total  = res.count or 0

    items = [_normalize(row) for row in (res.data or [])]

    return {
        "status": "success",
        "data": {
            "items":       items,
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


# ── POST /corrective-actions ─────────────────────────────────

@router.post("")
def create_corrective_action(
    body: CorrectiveActionCreate,
    current: dict = Depends(get_current_user),
):
    """이창 발행 등록."""
    supabase = get_supabase()

    # ── 회사 스코프 강제 (P13): 비-ALL 은 토큰 company_id(클라 값 무시) ──
    _forced = require_company_id(current, supabase)
    if _forced:
        body.company_id = _forced
    if body.factory_id:
        _ensure_factory_own(supabase, body.factory_id, current)

    now = _now()

    row = {
        "factory_id":        body.factory_id,
        "company_id":        body.company_id,
        "description":       body.description,
        "location":          body.location,
        "asset_name":        body.asset_name,
        "severity":          body.severity or "MEDIUM",
        "assigned_user_id":  body.assignee_id,   # 기존 컬럼명
        "assignee_id":       body.assignee_id,   # 신규 컬럼
        "due_date":          body.due_date,
        "action_plan":       body.action_plan,
        "status":            body.status or "OPEN",
        "status_code":       body.status or "OPEN",   # 기존 컬럼 동기화
        "created_by":        body.created_by,
        "created_at":        now,
        "updated_at":        now,
    }
    if body.defect_id:
        row["defect_id"] = body.defect_id

    res = supabase.table("corrective_actions").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="이창 발행 등록 실패")

    return {
        "status":  "success",
        "message": "이창이 등록되었습니다.",
        "data":    _normalize(res.data[0]),
    }


# ── PATCH /corrective-actions/{id} ──────────────────────────

@router.patch("/{action_id}")
def update_corrective_action(
    action_id: str,
    body: CorrectiveActionUpdate,
    current: dict = Depends(get_current_user),
):
    """
    이창 수정.
    - status=COMPLETED 시 completed_at 자동 세팅
    - status / status_code 양쪽 동기화
    - assignee_id / assigned_user_id 양쪽 동기화
    """
    supabase = get_supabase()
    now = _now()

    chk = supabase.table("corrective_actions").select("id, company_id").eq("id", action_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="이창을 찾을 수 없습니다.")
    # ── 회사 소유확인 (P13): 비-ALL 이 타사 자원 수정 차단 ──
    _ensure_own_company(chk.data[0].get("company_id"), current, supabase, "이창을 찾을 수 없습니다.")

    payload: dict = {"updated_at": now}

    if body.status is not None:
        payload["status"]      = body.status
        payload["status_code"] = body.status   # 기존 컬럼 동기화
        if body.status == "COMPLETED" and body.completed_at is None:
            payload["completed_at"] = now

    if body.action_result is not None: payload["action_result"]    = body.action_result
    if body.action_plan   is not None: payload["action_plan"]      = body.action_plan
    if body.assignee_id   is not None:
        payload["assignee_id"]      = body.assignee_id
        payload["assigned_user_id"] = body.assignee_id   # 기존 컬럼 동기화
    if body.due_date      is not None: payload["due_date"]         = body.due_date
    if body.severity      is not None: payload["severity"]         = body.severity
    if body.location      is not None: payload["location"]         = body.location
    if body.asset_name    is not None: payload["asset_name"]       = body.asset_name
    if body.completed_at  is not None: payload["completed_at"]     = body.completed_at

    res = supabase.table("corrective_actions").update(payload).eq("id", action_id).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="수정 실패")

    return {
        "status":  "success",
        "message": "이창이 수정되었습니다.",
        "data":    _normalize(res.data[0]),
    }
