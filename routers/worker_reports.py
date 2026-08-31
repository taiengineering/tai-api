"""
작업자 안전신고 / 긴급신고 API — v1.3.0

작업자 PWA(/app/report.html, /app/emergency.html, /app/corrective.html)가 호출하지만
서버에 부재해 404 로 실패하던 경로를 신설한다. 테이블은 이미 존재하므로 DDL 변경은 없다.

API:
  POST /safety-reports              이상 신고 접수 (report.html) — 개방(산안법 제52조)
  GET  /safety-reports/{id}         신고 상세 (corrective.html) — 인증+회사 스코프
  POST /safety-reports/{id}/confirm 시정조치 확인 (corrective.html) — 인증+회사 스코프
  POST /emergency/report            긴급 신고 접수 (emergency.html) — 개방(즉시보고)

접수(POST)는 산안법 제52조(근로자의 즉시 보고)를 막지 않도록 개방(optional-auth)한다.
현장 작업자가 토큰 만료 상태에서도 신고할 수 있어야 하기 때문이다.

v1.3.0 (2026-08-20): [SEC] 회사 판정에 reporter_id/worker_id 폴백 추가.
  factory_id/site_id 가 비어 있는 신고(실측: 기존 2건 모두 null)는 factory/site 만으로는
  회사 판정이 불가해 자사 관리자조차 열람 불가(ALL 전용)가 된다. 신고는 reporter_id·worker_id
  를 담으므로, factory→site→reporter→worker 순으로 회사를 판정한다(각 id 는 users→
  worker_registry 에서 company_id 조회). 이로써 factory/site 미기재 신고도 자사 열람이 성립.

v1.2.0 (2026-08-20): [SEC] 열람·확인 경로 인증 강제 + 회사 스코프 (Wave3, 직접MCP, 운영자 승인)
  - GET /safety-reports/{id}·POST /{id}/confirm 은 로그인 필수(get_current_user).
  - safety_reports 에 직접 company_id 가 없어 factory_id→factories / site_id→construction_sites
    경유로 회사를 판정, 비-ALL 은 자사 신고만 열람·확인(타사 404).
  - 접수(POST /safety-reports, /emergency/report)는 개방 유지(산안법 제52조 즉시보고).

v1.1.0 (2026-08-20): [FIX] GET/POST /safety-reports/{id} 의 report_id 를 UUID 검증.
  프론트가 /safety-reports/summary 를 폴링하면 report_id="summary" 로 매칭돼
  postgrest 22P02(invalid uuid) 로 500 이 나던 것을 404 로 정정한다(경로 부재 신호).
"""
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_own_company
from services.time import now_kst, serialize_external_utc

log = logging.getLogger(__name__)
router = APIRouter(tags=["WorkerReport"])


def _is_uuid(value) -> bool:
    """report_id 가 UUID 형식인지. 아니면 라우트 부재로 보고 404 처리(500 방지)."""
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _entity_company_id(sb, entity_id) -> Optional[str]:
    """reporter_id/worker_id 는 users.id 또는 worker_registry.id 둘 다 가능(모호) →
    users 우선, 없으면 worker_registry 에서 company_id 조회."""
    if not entity_id:
        return None
    u = sb.table("users").select("company_id").eq("id", entity_id).limit(1).execute()
    if u.data and u.data[0].get("company_id"):
        return u.data[0].get("company_id")
    w = sb.table("worker_registry").select("company_id").eq("id", entity_id).limit(1).execute()
    if w.data and w.data[0].get("company_id"):
        return w.data[0].get("company_id")
    return None


def _report_company_id(sb, row) -> Optional[str]:
    """safety_reports 행의 회사 판정. factory_id→site_id→reporter_id→worker_id 순.
    factory_id→factories.company_id, site_id→construction_sites.company_id,
    reporter_id/worker_id→users|worker_registry.company_id. 전부 실패 시 None."""
    fid = row.get("factory_id")
    if fid:
        f = sb.table("factories").select("company_id").eq("id", fid).limit(1).execute()
        if f.data and f.data[0].get("company_id"):
            return f.data[0].get("company_id")
    sid = row.get("site_id")
    if sid:
        s = sb.table("construction_sites").select("company_id").eq("id", sid).limit(1).execute()
        if s.data and s.data[0].get("company_id"):
            return s.data[0].get("company_id")
    # 폴백: factory/site 미기재 신고 → 신고자/작업자 id 경유로 회사 판정
    for eid in (row.get("reporter_id"), row.get("worker_id")):
        cid = _entity_company_id(sb, eid)
        if cid:
            return cid
    return None


def _optional_auth(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Authorization이 있으면 검증, 없으면 None 반환. (worker_check.py 와 동일 관례)"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    try:
        ur = supabase.auth.get_user(token)
        if not ur or not ur.user:
            raise HTTPException(status_code=401, detail={"error": "AUTH_EXPIRED"})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "AUTH_EXPIRED"})
    res = supabase.table("users").select("*").eq("auth_id", str(ur.user.id)).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return res.data[0]


def _clean_phone(phone: str) -> str:
    return (phone or "").replace("-", "").replace(" ", "")


def _resolve_worker(phone: str):
    """전화번호로 users → worker_registry 순서로 조회. (worker_check.py 와 동일 관례)

    users.phone 은 하이픈 유무가 섞여 있어 양쪽 형식으로 조회한다.
    """
    supabase = get_supabase()
    clean = _clean_phone(phone)
    if not clean:
        return None, ""

    u = supabase.table("users").select("id, name").eq("phone", clean).limit(1).execute()
    if not u.data and len(clean) == 11:
        fmt = f"{clean[:3]}-{clean[3:7]}-{clean[7:]}"
        u = supabase.table("users").select("id, name").eq("phone", fmt).limit(1).execute()
    if u.data:
        return u.data[0]["id"], u.data[0].get("name", "")

    w = supabase.table("worker_registry").select("id, name").eq("phone", clean).limit(1).execute()
    if w.data:
        return w.data[0]["id"], w.data[0].get("name", "")

    return None, ""


def _gen_report_number(prefix: str) -> str:
    """report_number 채번. 두 테이블 모두 NOT NULL 이며 서버가 생성한다.

    형식: <PREFIX>-YYYYMMDD-<6자리>
    프론트는 응답의 report_number 를 화면에 표시하므로 반드시 반환해야 한다.
    """
    today = now_kst().strftime("%Y%m%d")
    return f"{prefix}-{today}-{random.randint(100000, 999999)}"


# ══════════════════════════════════════════
# 안전(이상) 신고 — safety_reports
# ══════════════════════════════════════════

class SafetyReportBody(BaseModel):
    phone: str
    worker_id: Optional[str] = None
    factory_id: Optional[str] = None
    site_id: Optional[str] = None
    report_type: str
    description: str
    urgency: Optional[str] = "normal"
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    location_text: Optional[str] = None
    photo_urls: Optional[List[str]] = None


@router.post("/safety-reports")
def create_safety_report(
    body: SafetyReportBody,
    current_user: Optional[dict] = Depends(_optional_auth),
):
    """이상 신고 접수 (산안법 제52조) — 개방(즉시보고 보장)."""
    supabase = get_supabase()
    clean = _clean_phone(body.phone)

    worker_id = body.worker_id
    reporter_id = current_user["id"] if current_user else None
    if not worker_id or not reporter_id:
        resolved_id, _ = _resolve_worker(clean)
        worker_id = worker_id or resolved_id
        reporter_id = reporter_id or resolved_id

    report_number = _gen_report_number("SR")

    row = {
        "report_number": report_number,
        "phone": clean,
        "worker_id": worker_id,
        "factory_id": body.factory_id,
        "site_id": body.site_id,
        "report_type": body.report_type,
        "description": body.description,
        "urgency": body.urgency or "normal",
        "location_lat": body.location_lat,
        "location_lng": body.location_lng,
        "location_text": body.location_text,
        "photo_urls": body.photo_urls or [],
        "reporter_id": reporter_id,
        "status": "RECEIVED",
    }

    res = supabase.table("safety_reports").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="신고 저장에 실패했습니다")

    saved = res.data[0]
    log.info(f"[SafetyReport] 접수 {report_number} phone={clean} type={body.report_type}")

    return {
        "status": "success",
        "message": "신고가 접수됐습니다.",
        "report_number": report_number,
        "data": {
            "id": saved["id"],
            "report_number": report_number,
            "status": saved.get("status", "RECEIVED"),
        },
    }


@router.get("/safety-reports/{report_id}")
def get_safety_report(report_id: str, current: dict = Depends(get_current_user)):
    """신고 상세 조회 (corrective.html). 인증 필수 + 회사 스코프."""
    # report_id 가 UUID 가 아니면(예: 프론트의 /summary 폴링) 라우트 부재로 보고 404.
    if not _is_uuid(report_id):
        raise HTTPException(status_code=404, detail="신고를 찾을 수 없습니다")
    supabase = get_supabase()
    res = supabase.table("safety_reports").select("*").eq("id", report_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="신고를 찾을 수 없습니다")
    row = res.data[0]
    # 회사 스코프(P13): factory_id→site_id→reporter_id→worker_id 경유 회사 판정 후 자사만 열람
    _ensure_own_company(_report_company_id(supabase, row), current, supabase, "신고를 찾을 수 없습니다")
    return {"status": "success", "data": row}


class ConfirmBody(BaseModel):
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[str] = None


@router.post("/safety-reports/{report_id}/confirm")
def confirm_safety_report(
    report_id: str,
    body: ConfirmBody,
    current: dict = Depends(get_current_user),
):
    """작업자의 시정조치 완료 확인 (산안법 제53조). 인증 필수 + 회사 스코프.

    safety_reports 에는 확인자/확인시각 전용 컬럼이 없다. 상태만 CONFIRMED 로 전이시키며,
    확인자 이력이 필요해지면 별도 컬럼 추가를 동반한 마이그레이션이 필요하다.
    """
    if not _is_uuid(report_id):
        raise HTTPException(status_code=404, detail="신고를 찾을 수 없습니다")
    supabase = get_supabase()

    exist = supabase.table("safety_reports").select("id, status, factory_id, site_id, reporter_id, worker_id").eq("id", report_id).limit(1).execute()
    if not exist.data:
        raise HTTPException(status_code=404, detail="신고를 찾을 수 없습니다")
    # 회사 스코프(P13): 자사 신고만 확인 가능
    _ensure_own_company(_report_company_id(supabase, exist.data[0]), current, supabase, "신고를 찾을 수 없습니다")

    res = supabase.table("safety_reports").update({
        "status": "CONFIRMED",
        "updated_at": serialize_external_utc(now_kst()),
    }).eq("id", report_id).execute()

    log.info(f"[SafetyReport] 조치확인 {report_id} by={body.confirmed_by}")

    return {
        "status": "success",
        "message": "조치 확인이 완료됐습니다.",
        "data": {"id": report_id, "status": "CONFIRMED"},
    }


# ══════════════════════════════════════════
# 긴급 신고 — emergency_reports
# ══════════════════════════════════════════

class EmergencyReportBody(BaseModel):
    phone: str
    worker_name: str
    accident_type: str          # 표시용 라벨
    accident_type_key: str      # fall|fire|pinch|electric|chem|other
    location: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    photo_urls: Optional[List[str]] = None


@router.post("/emergency/report")
def create_emergency_report(
    body: EmergencyReportBody,
    current_user: Optional[dict] = Depends(_optional_auth),
):
    """긴급 신고 접수. 사고 발생 시 즉시 보고 경로이므로 인증 실패로 막지 않는다."""
    supabase = get_supabase()
    clean = _clean_phone(body.phone)

    reporter_id = current_user["id"] if current_user else None
    if not reporter_id:
        reporter_id, _ = _resolve_worker(clean)

    report_number = _gen_report_number("EM")

    row = {
        "report_number": report_number,
        "phone": clean,
        "worker_name": body.worker_name,
        "accident_type": body.accident_type,
        "accident_type_key": body.accident_type_key,
        "location": body.location,
        "location_lat": body.location_lat,
        "location_lng": body.location_lng,
        "photo_urls": body.photo_urls or [],
        "reporter_id": reporter_id,
        "status": "RECEIVED",
    }

    res = supabase.table("emergency_reports").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="긴급 신고 저장에 실패했습니다")

    saved = res.data[0]
    log.warning(
        f"[EmergencyReport] 접수 {report_number} phone={clean} "
        f"type={body.accident_type_key} loc={body.location_lat},{body.location_lng}"
    )

    return {
        "status": "success",
        "message": "긴급 신고가 접수됐습니다.",
        "report_number": report_number,
        "data": {
            "id": saved["id"],
            "report_number": report_number,
            "status": saved.get("status", "RECEIVED"),
        },
    }
