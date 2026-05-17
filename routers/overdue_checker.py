"""
routers/overdue_checker.py — v1.0.0

BE-10: 업무 지연 에스켈레이션 라우터

에스켈레이션 단계:
  D-1  (overdue_level=1): 리마인더  → 작업자 SMS
  D+1  (overdue_level=2): 작업자 경고 → 작업자 SMS + FCM
  D+2  (overdue_level=3): 관리자 알림 → 판리자/안전관리자 SMS + FCM
  D+7  (overdue_level=4): OVERDUE 전환 → status_code='OVERDUE' + notifications

원칙:
  - work_assignments.due_date 우선, 없으면 scheduled_date 사용
  - 이미 해당 level로 발송된 건 재발송 안함 (overdue_level 비교)
  - SMS: messaging.py _call_edge() 패턴 재사용 (Edge Function 경유)
  - FCM: users.push_token 직접
  - 모든 발송 이력 overdue_history 저장
  - DONE/SKIP 스킵 트리거는 status_code='OVERDUE'로 업데이트

API:
  POST /overdue/check               추제 실행 (cron-job.org 또는 수동)
  GET  /overdue/summary             사업장/판리자로 지연 현황 요약
  GET  /overdue/history             에스켈레이션 이력 조회
  POST /overdue/resolve/{history_id} 지연 해소 해주기
"""
from __future__ import annotations
import asyncio
import logging
import os
import threading
from datetime import date, datetime, timezone, timedelta
from typing import Optional, Any

import requests as _req
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/overdue", tags=["\uc5c5\ubb34\uc9c0\uc5f0\uc5d0\uc2a4\ucf08\ub808\uc774\uc158"])

VERSION = "1.0.0"

# Edge Function URL (messaging.py와 동일)
_SMS_EDGE = "https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/send-sms"

# FCM Edge Function URL
_FCM_EDGE = os.getenv(
    "FCM_EDGE_URL",
    "https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/send-push"
)

# 에스켈레이션 단계 정의
# (days_delta, overdue_level, action_type, 상와 문자열)
_LEVELS = [
    (-1, 1, "REMIND",           "[TAI Safe] 내일 {task} 마감입니다. 오늘 안에 완료해 주세요."),
    ( 1, 2, "WARN_WORKER",      "[TAI Safe] {task} 작업이 {days}일 지연되었습니다. 지금 증 완료해 주세요."),
    ( 2, 3, "NOTIFY_MANAGER",   "[TAI Safe] \u26a0 {task} 2일 이상 미완료 확인 요청. 담당: {worker}"),
    ( 7, 4, "MARK_OVERDUE",     "[TAI Safe] {task}가 7일 이상 미완료되어 OVERDUE 전환되었습니다."),
]


# ─────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────────────

def _today() -> date:
    return datetime.now(timezone.utc).date()


def _schedule_wire_and_emit(event_type: str, payload: dict) -> None:
    """033: sync cron path → fire-and-forget async wire_and_emit."""

    async def _run() -> None:
        try:
            from services.notification_engine.event_wiring import wire_and_emit
            await wire_and_emit(event_type=event_type, payload=payload)
        except Exception as e:
            log.warning("[NOTIF] %s wire failed: %s", event_type, e)

    def _thread_main() -> None:
        try:
            asyncio.run(_run())
        except Exception as e:
            log.warning("[NOTIF] %s wire thread failed: %s", event_type, e)

    threading.Thread(target=_thread_main, daemon=True).start()


def _effective_due(wa: dict) -> Optional[date]:
    """due_date 우선, 없으면 scheduled_date. 둘 다 없으면 None."""
    d = wa.get("due_date") or wa.get("scheduled_date")
    if not d:
        return None
    if isinstance(d, date):
        return d
    try:
        return date.fromisoformat(str(d)[:10])
    except ValueError:
        return None


def _send_sms(phone: str, message: str) -> bool:
    """Edge Function 경유 SMS 발송. 성공 시 True."""
    if not phone:
        return False
    try:
        resp = _req.post(
            _SMS_EDGE,
            json={"receiver": phone, "message": message, "type": "sms"},
            timeout=20,
        )
        result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        ok = bool(result.get("success")) or resp.status_code < 300
        log.info("[OVERDUE] SMS %s → %s", phone[-4:], "OK" if ok else "FAIL")
        return ok
    except Exception as e:
        log.warning("[OVERDUE] SMS 실패: %s", e)
        return False


def _send_fcm(push_token: str, title: str, body: str) -> bool:
    """FCM 푸시 발송 (Edge Function 경유). 성공 시 True."""
    if not push_token:
        return False
    try:
        resp = _req.post(
            _FCM_EDGE,
            json={"token": push_token, "title": title, "body": body},
            timeout=20,
        )
        ok = resp.status_code < 300
        log.info("[OVERDUE] FCM → %s", "OK" if ok else "FAIL")
        return ok
    except Exception as e:
        log.warning("[OVERDUE] FCM 실패: %s", e)
        return False


def _write_notification(sb, user_id: str, company_id: Optional[str], title: str, body: str) -> None:
    """안전신 notifications 테이블 INSERT."""
    try:
        sb.table("notifications").insert({
            "user_id":      user_id,
            "company_id":   company_id,
            "trigger_code": "OVERDUE_ESCALATION",
            "trigger_group": "OVERDUE",
            "title":        title,
            "body":         body,
            "priority":     "HIGH",
            "is_read":      False,
            "channel":      "push",
            "send_status":  "SENT",
            "sent_at":      datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.warning("[OVERDUE] notifications INSERT 실패: %s", e)


def _write_history(
    sb,
    assignment_id: str,
    factory_id: Optional[str],
    assigned_user_id: Optional[str],
    overdue_level: int,
    action_type: str,
    message_body: str,
    sms_sent: bool,
    fcm_sent: bool,
    notif_sent: bool,
) -> Optional[str]:
    """에스켈레이션 이력 overdue_history 저장. 생성된 id 반환."""
    try:
        res = sb.table("overdue_history").insert({
            "assignment_id":    assignment_id,
            "factory_id":       factory_id,
            "assigned_user_id": assigned_user_id,
            "overdue_level":    overdue_level,
            "action_type":      action_type,
            "message_body":     message_body,
            "sms_sent":         sms_sent,
            "fcm_sent":         fcm_sent,
            "notif_sent":       notif_sent,
        }).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        log.error("[OVERDUE] history INSERT 실패: %s", e)
        return None


def _process_one(sb, wa: dict, today: date) -> dict:
    """단일 work_assignment 에스켈레이션 실행. 결과 dict 반환."""
    wa_id    = wa["id"]
    cur_lvl  = wa.get("overdue_level") or 0
    due      = _effective_due(wa)

    if not due:
        return {"id": wa_id, "skipped": "due_date_none"}

    delta = (today - due).days   # 0=당일, 1=1일 차과, -1=1일 전

    # 단계 결정: delta 다 타겜하지 않은 것 중 가장 높은 level
    target_level = 0
    for days_delta, lvl, _, _ in _LEVELS:
        if delta >= days_delta:
            target_level = lvl

    if target_level <= cur_lvl:
        return {"id": wa_id, "skipped": f"already_level_{cur_lvl}"}

    # 해당 level config 가져오기
    cfg = next((x for x in _LEVELS if x[1] == target_level), None)
    if not cfg:
        return {"id": wa_id, "skipped": "no_cfg"}

    days_delta, lvl, action_type, msg_tpl = cfg

    # 작업자/관리자 정보 조회
    user_id    = wa.get("assigned_user_id")
    factory_id = wa.get("factory_id")
    task_name  = wa.get("task_name") or wa.get("inspection_set_id") or "\uc810\uac80 \uc791\uc5c5"

    worker_info: dict[str, Any] = {}
    if user_id:
        try:
            ur = sb.table("users").select(
                "id, name, phone, push_token, allow_sms, allow_push, company_id"
            ).eq("id", user_id).limit(1).execute()
            worker_info = ur.data[0] if ur.data else {}
        except Exception:
            pass

    # 관리자 조회 (factory 안전관리자 또는 관리자 역할)
    manager_info: dict[str, Any] = {}
    if factory_id and action_type in ("NOTIFY_MANAGER", "MARK_OVERDUE"):
        try:
            mr = sb.table("users").select(
                "id, name, phone, push_token, allow_sms, allow_push"
            ).eq("factory_id", factory_id).in_(
                "role_code", ["001", "002"]  # admin, safety_manager
            ).eq("is_active", True).limit(1).execute()
            manager_info = mr.data[0] if mr.data else {}
        except Exception:
            pass

    company_id = worker_info.get("company_id")

    factory_name = ""
    if factory_id:
        try:
            fr = sb.table("factories").select("factory_name").eq("id", factory_id).limit(1).execute()
            if fr.data:
                factory_name = fr.data[0].get("factory_name") or ""
        except Exception:
            pass

    inspection_id = wa.get("inspection_set_id") or wa.get("inspection_id")

    # 메시지 생성
    worker_name = worker_info.get("name") or "\uc791\uc5c5\uc790"
    msg = (msg_tpl
           .replace("{task}",   str(task_name))
           .replace("{days}",   str(abs(delta)))
           .replace("{worker}", worker_name))

    sms_ok = fcm_ok = notif_ok = False
    target_user_id = None

    if action_type in ("REMIND", "WARN_WORKER"):
        # 작업자 대상
        target_user_id = user_id
        if worker_info.get("allow_sms") and worker_info.get("phone"):
            sms_ok = _send_sms(worker_info["phone"], msg)
        if action_type == "WARN_WORKER":
            if worker_info.get("allow_push") and worker_info.get("push_token"):
                fcm_ok = _send_fcm(worker_info["push_token"], "[TAI Safe] \uc791\uc5c5 \uc9c0\uc5f0", msg)
        if target_user_id:
            _write_notification(sb, target_user_id, company_id, "[TAI Safe] \uc791\uc5c5 \uc9c0\uc5f0", msg)
            notif_ok = True

    elif action_type == "NOTIFY_MANAGER":
        # 관리자 대상
        target_user_id = manager_info.get("id") or user_id
        if manager_info.get("allow_sms") and manager_info.get("phone"):
            sms_ok = _send_sms(manager_info["phone"], msg)
        if manager_info.get("allow_push") and manager_info.get("push_token"):
            fcm_ok = _send_fcm(manager_info["push_token"], "[TAI Safe] \uc9c0\uc5f0 \ud310\ub9ac", msg)
        if target_user_id:
            _write_notification(sb, target_user_id, company_id, "[TAI Safe] \uc9c0\uc5f0 \ud310\ub9ac", msg)
            notif_ok = True

    elif action_type == "MARK_OVERDUE":
        # OVERDUE 전환 + 판리자/작업자 동시 알림
        target_user_id = manager_info.get("id") or user_id
        if manager_info.get("allow_sms") and manager_info.get("phone"):
            sms_ok = _send_sms(manager_info["phone"], msg)
        if manager_info.get("allow_push") and manager_info.get("push_token"):
            fcm_ok = _send_fcm(manager_info["push_token"], "[TAI Safe] OVERDUE", msg)
        if target_user_id:
            _write_notification(sb, target_user_id, company_id, "[TAI Safe] OVERDUE \uc804\ud658", msg)
            notif_ok = True
        # status_code OVERDUE 전환
        try:
            sb.table("work_assignments").update({"status_code": "OVERDUE"}).eq("id", wa_id).execute()
        except Exception as e:
            log.error("[OVERDUE] status OVERDUE 업데이트 실패: %s", e)

    # ── Notification Runtime 연결 (033) ──
    _schedule_wire_and_emit(
        "schedule_overdue",
        {
            "title": f"점검 미이행: {task_name}",
            "body": f"{factory_name or ''} 점검이 예정일을 초과했습니다.".strip(),
            "factory_id": str(factory_id) if factory_id else None,
            "company_id": str(company_id) if company_id else None,
            "inspection_id": str(inspection_id) if inspection_id else None,
            "assignment_id": str(wa_id),
            "overdue_level": lvl,
        },
    )

    # overdue_level + last_reminded_at 업데이트
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        sb.table("work_assignments").update({
            "overdue_level":    lvl,
            "last_reminded_at": now_iso,
        }).eq("id", wa_id).execute()
    except Exception as e:
        log.error("[OVERDUE] level 업데이트 실패: %s", e)

    hist_id = _write_history(
        sb, wa_id, factory_id, user_id,
        lvl, action_type, msg,
        sms_ok, fcm_ok, notif_ok,
    )

    return {
        "id":          wa_id,
        "action":      action_type,
        "level":       lvl,
        "delta_days":  delta,
        "sms":         sms_ok,
        "fcm":         fcm_ok,
        "notif":       notif_ok,
        "history_id":  hist_id,
    }


# ─────────────────────────────────────────────────────────────────────────
# API 엔드포인트
# ─────────────────────────────────────────────────────────────────────────

@router.post("/check")
def run_overdue_check(
    factory_id:  Optional[str] = Query(None, description="특정 시설만 체크 (None = 전체)"),
    dry_run:     bool          = Query(False, description="True이면 DB 미수정, 시뮬레이션만"),
    limit:       int           = Query(200, ge=1, le=1000, description="실행 최대 건수"),
):
    """
    에스켈레이션 실행. cron-job.org에서 매일 09:00 KST 자동 호출.
    dry_run=True이면 실제 SMS/FCM/DB 수정 없이 시뮬레이션 결과만 반환.
    """
    supabase = get_supabase()
    today    = _today()

    # 체크 대상: DONE/SKIP 제외, due_date 또는 scheduled_date 존재
    q = (
        supabase.table("work_assignments")
        .select("id, factory_id, assigned_user_id, scheduled_date, due_date,"
                " overdue_level, last_reminded_at, status_code, inspection_set_id")
        .not_.in_("status_code", ["DONE", "SKIP", "OVERDUE"])
        .limit(limit)
    )
    if factory_id:
        q = q.eq("factory_id", factory_id)

    res = q.execute()
    assignments = res.data or []

    results     = []
    acted       = 0
    skipped_cnt = 0

    for wa in assignments:
        if dry_run:
            # dry_run: level 계산만, 실제 발송/DB 수정 없음
            due = _effective_due(wa)
            if not due:
                skipped_cnt += 1; continue
            delta = (today - due).days
            target_level = 0
            for dd, lvl, act, _ in _LEVELS:
                if delta >= dd: target_level = lvl
            results.append({"id": wa["id"], "delta": delta,
                            "current_level": wa.get("overdue_level",0),
                            "target_level": target_level,
                            "would_act": target_level > (wa.get("overdue_level") or 0)})
        else:
            r = _process_one(supabase, wa, today)
            results.append(r)
            if r.get("action"):
                acted += 1
            else:
                skipped_cnt += 1

    return {
        "status":   "dry_run" if dry_run else "success",
        "date":     today.isoformat(),
        "checked":  len(assignments),
        "acted":    acted,
        "skipped":  skipped_cnt,
        "version":  VERSION,
        "results":  results,
    }


@router.get("/summary")
def get_overdue_summary(
    factory_id: Optional[str] = Query(None, description="시설 ID 필터"),
):
    """
    지연 현황 요약.
    overdue_level 총 4단계 + OVERDUE status 긜별 집계.
    """
    supabase = get_supabase()
    today    = _today()

    q = supabase.table("work_assignments").select(
        "id, factory_id, scheduled_date, due_date, overdue_level, status_code"
    ).not_.in_("status_code", ["DONE", "SKIP"])
    if factory_id:
        q = q.eq("factory_id", factory_id)

    res = q.execute()
    rows = res.data or []

    summary: dict[str, int] = {
        "total":          len(rows),
        "normal":         0,
        "remind_d1":      0,   # level 1
        "warn_d1":        0,   # level 2
        "manager_d2":     0,   # level 3
        "overdue_d7":     0,   # level 4 or status=OVERDUE
        "no_due_date":    0,
    }

    for wa in rows:
        if wa["status_code"] == "OVERDUE" or (wa.get("overdue_level") or 0) >= 4:
            summary["overdue_d7"] += 1
        elif (wa.get("overdue_level") or 0) == 3:
            summary["manager_d2"] += 1
        elif (wa.get("overdue_level") or 0) == 2:
            summary["warn_d1"] += 1
        elif (wa.get("overdue_level") or 0) == 1:
            summary["remind_d1"] += 1
        elif not _effective_due(wa):
            summary["no_due_date"] += 1
        else:
            summary["normal"] += 1

    return {
        "status": "success",
        "date":   today.isoformat(),
        "factory_id": factory_id or "all",
        "summary": summary,
    }


@router.get("/history")
def get_overdue_history(
    factory_id:    Optional[str] = Query(None),
    assignment_id: Optional[str] = Query(None),
    action_type:   Optional[str] = Query(None, description="REMIND|WARN_WORKER|NOTIFY_MANAGER|MARK_OVERDUE|RESOLVE"),
    resolved:      Optional[bool] = Query(None),
    page:          int           = Query(1, ge=1),
    size:          int           = Query(20, ge=1, le=100),
):
    """\uc5d0\uc2a4\ucf08\ub808\uc774\uc158 \uc774\ub825 \uc870\ud68c."""
    supabase = get_supabase()
    offset = (page - 1) * size

    q = supabase.table("overdue_history").select(
        "id, assignment_id, factory_id, assigned_user_id,"
        " overdue_level, action_type, message_body,"
        " sms_sent, fcm_sent, notif_sent,"
        " resolved, resolved_at, resolve_note, created_at",
        count="exact",
    ).order("created_at", desc=True)

    if factory_id:    q = q.eq("factory_id", factory_id)
    if assignment_id: q = q.eq("assignment_id", assignment_id)
    if action_type:   q = q.eq("action_type", action_type)
    if resolved is not None: q = q.eq("resolved", resolved)

    res = q.range(offset, offset + size - 1).execute()

    return {
        "status": "success",
        "total":  res.count or 0,
        "page":   page,
        "size":   size,
        "items":  res.data or [],
    }


class ResolveBody(BaseModel):
    resolved_by: Optional[str] = None
    resolve_note: Optional[str] = None


@router.post("/resolve/{history_id}")
def resolve_overdue(history_id: str, body: ResolveBody):
    """
    \uc9c0\uc5f0 \ud574\uc18c \ud574\uc8fc\uae30.
    overdue_history 크 해소 표시 + 대상 work_assignment의 resolved_at 기록.
    """
    supabase = get_supabase()
    now_iso  = datetime.now(timezone.utc).isoformat()

    # 1. overdue_history 조회
    hist_res = supabase.table("overdue_history").select(
        "id, assignment_id, resolved"
    ).eq("id", history_id).limit(1).execute()

    if not hist_res.data:
        raise HTTPException(status_code=404, detail="이력을 찾을 수 없습니다.")

    hist = hist_res.data[0]
    if hist.get("resolved"):
        raise HTTPException(status_code=409, detail="이미 해소 처리된 이력입니다.")

    # 2. history 해소
    upd: dict[str, Any] = {
        "resolved":    True,
        "resolved_at": now_iso,
    }
    if body.resolved_by:  upd["resolved_by"]  = body.resolved_by
    if body.resolve_note: upd["resolve_note"] = body.resolve_note

    supabase.table("overdue_history").update(upd).eq("id", history_id).execute()

    # 3. work_assignment resolved_at + overdue_level 0 리셋
    wa_id = hist["assignment_id"]
    try:
        supabase.table("work_assignments").update({
            "resolved_at":  now_iso,
            "overdue_level": 0,
            "status_code":  "DONE",
        }).eq("id", wa_id).execute()
    except Exception as e:
        log.warning("[OVERDUE] resolve wa 업데이트 실패: %s", e)

    # 4. 해소 이력 기록
    _write_history(
        supabase, wa_id, None, body.resolved_by,
        0, "RESOLVE", body.resolve_note or "\uc9c0\uc5f0 \ud574\uc18c",
        False, False, False,
    )

    return {
        "status":      "success",
        "history_id":  history_id,
        "assignment_id": wa_id,
        "resolved_at": now_iso,
    }
