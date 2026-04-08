"""
equipment_checkins.py — v1.0.0

v1.0.0 (2026-04-08):
  QR/RFID 설비 체크인 API
  - POST /equipment-checkins         체크인 제출 (인증 불필요)
  - GET  /equipment-checkins         이력 조회  (인증 필요)
  - GET  /equipment-checkins/{id}    단건 조회  (인증 필요)

이상(NG/HOLD) 발생 시 자동 처리:
  1. notifications 테이블에 DB 알림 생성
  2. 해당 사업장 안전관리자(role_code=003)에게 FCM 푸시 발송
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from db.supabase_client import get_supabase

router = APIRouter(prefix="/equipment-checkins", tags=["equipment_checkins"])

VERSION = "1.0.0"


# ── Pydantic 모델 ─────────────────────────────────

class CheckinItem(BaseModel):
    item_key:   str
    item_label: str
    result:     str        # OK | NG | HOLD
    note:       Optional[str] = None


class EquipmentCheckinCreate(BaseModel):
    equipment_asset_id: str
    schedule_id:        Optional[str] = None
    checkin_items:      Optional[List[CheckinItem]] = None
    overall_result:     str                            # OK | NG | HOLD
    note:               Optional[str] = None
    worker_id:          Optional[str] = None           # 로그인 사용자
    worker_name:        Optional[str] = None           # 미로그인 직접 입력
    signature_data:     Optional[str] = None           # base64
    photo_urls:         Optional[List[str]] = None
    scan_method:        Optional[str] = "QR"           # QR | RFID | MANUAL
    latitude:           Optional[float] = None
    longitude:          Optional[float] = None


# ── POST /equipment-checkins (인증 불필요) ──────────────────

@router.post("")
async def submit_checkin(body: EquipmentCheckinCreate):
    """
    QR/RFID 스캔 후 점검 결과 제출.
    인증: 불필요 (현장 익명 접근 허용)
    이상(NG/HOLD) 시 관리자 FCM + DB 알림 자동 생성.
    """
    supabase = get_supabase()

    if body.overall_result not in ("OK", "NG", "HOLD"):
        raise HTTPException(status_code=422, detail="overall_result는 OK|NG|HOLD 중 하나여야 합니다")
    if not body.worker_id and not body.worker_name:
        raise HTTPException(status_code=422, detail="worker_id 또는 worker_name 중 하나는 필수입니다")

    # 설비 + 사업장 정보 조회
    asset_res = supabase.table("equipment_assets").select(
        "id, asset_name, factory_id"
    ).eq("id", body.equipment_asset_id).limit(1).execute()
    if not asset_res.data:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다")

    asset      = asset_res.data[0]
    factory_id = asset.get("factory_id")
    company_id = None
    if factory_id:
        fac = supabase.table("factories").select("company_id").eq(
            "id", factory_id
        ).limit(1).execute()
        company_id = (fac.data[0] if fac.data else {}).get("company_id")

    # 체크인 레코드 저장
    now_iso     = datetime.now(timezone.utc).isoformat()
    insert_data = {
        "equipment_asset_id": body.equipment_asset_id,
        "factory_id":         factory_id,
        "company_id":         company_id,
        "worker_id":          body.worker_id,
        "worker_name":        body.worker_name,
        "checkin_items":      [i.dict() for i in body.checkin_items] if body.checkin_items else None,
        "overall_result":     body.overall_result,
        "note":               body.note,
        "signature_data":     body.signature_data,
        "photo_urls":         body.photo_urls,
        "scan_method":        body.scan_method or "QR",
        "latitude":           body.latitude,
        "longitude":          body.longitude,
        "checkin_at":         now_iso,
    }
    if body.schedule_id:
        insert_data["schedule_id"] = body.schedule_id
    insert_data = {k: v for k, v in insert_data.items() if v is not None}

    res = supabase.table("equipment_checkins").insert(insert_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="체크인 저장 실패")

    new_checkin = res.data[0]

    # 일정 완료 처리
    if body.schedule_id and body.overall_result == "OK":
        try:
            supabase.table("work_schedules").update({
                "status_code": "DONE"
            }).eq("id", body.schedule_id).execute()
        except Exception as e:
            print(f"[CHECKIN] 일정 상태 업데이트 실패: {e}")

    # 이상·보류 시 관리자 알림
    if body.overall_result in ("NG", "HOLD") and factory_id:
        try:
            _notify_abnormal_checkin(
                supabase    = supabase,
                factory_id  = factory_id,
                company_id  = company_id,
                asset_name  = asset["asset_name"],
                worker_name = body.worker_name or body.worker_id or "작업자",
                overall_result = body.overall_result,
                note        = body.note,
                checkin_id  = new_checkin["id"],
            )
        except Exception as e:
            print(f"[CHECKIN] 이상 알림 실패 (non-critical): {e}")

    return {
        "status":  "success",
        "message": "체크인이 완료됐습니다",
        "data": {
            "checkin_id":     new_checkin["id"],
            "overall_result": body.overall_result,
            "checkin_at":     new_checkin["checkin_at"],
        }
    }


def _notify_abnormal_checkin(
    supabase,
    factory_id:     str,
    company_id:     Optional[str],
    asset_name:     str,
    worker_name:    str,
    overall_result: str,
    note:           Optional[str],
    checkin_id:     str,
):
    """
    이상(NG) / 보류(HOLD) 체크인 시:
    1. notifications 테이블 알림 INSERT
    2. 안전관리자(role_code=003) FCM 푸시 발송
    """
    label     = "이상" if overall_result == "NG" else "보류"
    title     = f"[TAI Safe] 설비 점검 {label} 발생"
    body_text = f"{asset_name} — {worker_name}님이 {label}로 보고했습니다."
    if note:
        body_text += f" ({note})"

    # DB 알림 생성
    notif: dict = {
        "factory_id":    factory_id,
        "title":         title,
        "body":          body_text,
        "type":          "EQUIPMENT_ABNORMAL",
        "reference_id":  checkin_id,
        "is_read":       False,
    }
    if company_id:
        notif["company_id"] = company_id
    try:
        supabase.table("notifications").insert(notif).execute()
    except Exception as e:
        print(f"[CHECKIN] 알림 DB 저장 실패: {e}")

    # FCM 발송 — 사업장 안전관리자 토큰 조회
    try:
        from utils.fcm_utils import send_push
        mgr_res = supabase.table("users").select("push_token").eq(
            "factory_id", factory_id
        ).eq("role_code", "003").execute()
        for u in (mgr_res.data or []):
            token = u.get("push_token")
            if token:
                try:
                    send_push(
                        fcm_token = token,
                        title     = title,
                        body      = body_text,
                        data      = {
                            "type":       "EQUIPMENT_ABNORMAL",
                            "checkin_id": checkin_id,
                        },
                    )
                except Exception as fe:
                    print(f"[CHECKIN] FCM 단건 실패 token={token[:15]}: {fe}")
    except Exception as e:
        print(f"[CHECKIN] FCM 전체 실패: {e}")


# ── GET /equipment-checkins (인증 필요) ─────────────────────

@router.get("")
def get_checkins(
    factory_id:         Optional[str] = Query(None),
    equipment_asset_id: Optional[str] = Query(None),
    overall_result:     Optional[str] = Query(None),   # OK | NG | HOLD
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    q = supabase.table("equipment_checkins").select(
        "id, equipment_asset_id, factory_id, worker_id, worker_name, "
        "overall_result, note, scan_method, checkin_at, "
        "checkin_items, photo_urls",
        count="exact"
    )
    if factory_id:
        q = q.eq("factory_id",         factory_id)
    if equipment_asset_id:
        q = q.eq("equipment_asset_id", equipment_asset_id)
    if overall_result:
        q = q.eq("overall_result",     overall_result)

    offset = (page - 1) * size
    res = q.order("checkin_at", desc=True).range(offset, offset + size - 1).execute()
    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": res.count or 0,
            "page":  page,
            "size":  size,
        }
    }


# ── GET /equipment-checkins/{id} (인증 필요) ────────────────

@router.get("/{checkin_id}")
def get_checkin(checkin_id: str):
    supabase = get_supabase()
    res = supabase.table("equipment_checkins").select("*").eq(
        "id", checkin_id
    ).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="체크인 기록을 찾을 수 없습니다")
    return {"status": "success", "data": res.data[0]}
