"""
routers/overdue_checker.py — v1.1.0

v1.1.0 (2026-04-17):
  [ADD] 현장별 notification_time 필터 — factories.notification_time 설정 시간 도달한 현장만 처리
  [ADD] cron 30분 간격 실행 (06:00~09:30) → 현장별 설정 시간에 맞춰 알림 발송
  기존 overdue_level 체크로 중복 발송 방지

v1.0.0: 초기 구현 (D-1/D+1/D+2/D+7 에스컬레이션)
"""
from __future__ import annotations
import logging
import os
from datetime import date, datetime, timezone, timedelta, time as dt_time
from typing import Optional, Any
from zoneinfo import ZoneInfo

import requests as _req
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/overdue", tags=["업무지연에스켈레이션"])

VERSION = "1.1.0"
KST = ZoneInfo("Asia/Seoul")

_SMS_EDGE = "https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/send-sms"
_FCM_EDGE = os.getenv(
    "FCM_EDGE_URL",
    "https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/send-push"
)

_LEVELS = [
    (-1, 1, "REMIND",           "[TAI Safe] 내일 {task} 마감입니다. 오늘 안에 완료해 주세요."),
    ( 1, 2, "WARN_WORKER",      "[TAI Safe] {task} 작업이 {days}일 지연되었습니다. 지금 즉시 완료해 주세요."),
    ( 2, 3, "NOTIFY_MANAGER",   "[TAI Safe] ⚠ {task} 2일 이상 미완료 확인 요청. 담당: {worker}"),
    ( 7, 4, "MARK_OVERDUE",     "[TAI Safe] {task}가 7일 이상 미완료되어 OVERDUE 전환되었습니다."),
]


def _today() -> date:
    return datetime.now(KST).date()


def _now_kst_time() -> dt_time:
    return datetime.now(KST).time()


def _effective_due(wa: dict) -> Optional[date]:
    d = wa.get("due_date") or wa.get("scheduled_date")
    if not d:
        return None
    if isinstance(d, date):
        return d
    try:
        return date.fromisoformat(str(d)[:10])
    except ValueError:
        return None


def _parse_time(t) -> dt_time:
    """DB의 TIME 값을 파이썬 time으로 변환. 실패 시 기본 07:00."""
    if isinstance(t, dt_time):
        return t
    if not t:
        return dt_time(7, 0)
    try:
        parts = str(t).split(":")
        return dt_time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    except (ValueError, IndexError):
        return dt_time(7, 0)


def _load_factory_notification_times(sb) -> dict:
    """전체 factories의 notification_time을 {factory_id: time} dict로 로드."""
    try:
        res = sb.table("factories").select("id, notification_time").execute()
        return {
            r["id"]: _parse_time(r.get("notification_time"))
            for r in (res.data or [])
        }
    except Exception as e:
        log.warning("[OVERDUE] factory notification_time 로드 실패: %s", e)
        return {}


def _send_sms(phone: str, message: str) -> bool:
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


def _write_history(sb, assignment_id, factory_id, assigned_user_id,
                   overdue_level, action_type, message_body,
                   sms_sent, fcm_sent, notif_sent) -> Optional[str]:
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
    wa_id    = wa["id"]
    cur_lvl  = wa.get("overdue_level") or 0
    due      = _effective_due(wa)

    if not due:
        return {"id": wa_id, "skipped": "due_date_none"}

    delta = (today - due).days

    target_level = 0
    for days_delta, lvl, _, _ in _LEVELS:
        if delta >= days_delta:
            target_level = lvl

    if target_level <= cur_lvl:
        return {"id": wa_id, "skipped": f"already_level_{cur_lvl}"}

    cfg = next((x for x in _LEVELS if x[1] == target_level), None)
    if not cfg:
        return {"id": wa_id, "skipped": "no_cfg"}

    days_delta, lvl, action_type, msg_tpl = cfg

    user_id    = wa.get("assigned_user_id")
    factory_id = wa.get("factory_id")
    task_name  = wa.get("task_name") or wa.get("inspection_set_id") or "점검 작업"

    worker_info: dict[str, Any] = {}
    if user_id:
        try:
            ur = sb.table("users").select(
                "id, name, phone, push_token, allow_sms, allow_push, company_id"
            ).eq("id", user_id).limit(1).execute()
            worker_info = ur.data[0] if ur.data else {}
        except Exception:
            pass

    manager_info: dict[str, Any] = {}
    if factory_id and action_type in ("NOTIFY_MANAGER", "MARK_OVERDUE"):
        try:
            mr = sb.table("users").select(
                "id, name, phone, push_token, allow_sms, allow_push"
            ).eq("factory_id", factory_id).in_(
                "role_code", ["001", "002"]
            ).eq("is_active", True).limit(1).execute()
            manager_info = mr.data[0] if mr.data else {}
        except Exception:
            pass

    company_id = worker_info.get("company_id")
    worker_name = worker_info.get("name") or "작업자"
    msg = (msg_tpl
           .replace("{task}",   str(task_name))
           .replace("{days}",   str(abs(delta)))
           .replace("{worker}", worker_name))

    sms_ok = fcm_ok = notif_ok = False
    target_user_id = None

    if action_type in ("REMIND", "WARN_WORKER"):
        target_user_id = user_id
        if worker_info.get("allow_sms") and worker_info.get("phone"):
            sms_ok = _send_sms(worker_info["phone"], msg)
        if action_type == "WARN_WORKER":
            if worker_info.get("allow_push") and worker_info.get("push_token"):
                fcm_ok = _send_fcm(worker_info["push_token"], "[TAI Safe] 작업 지연", msg)
        if target_user_id:
            _write_notification(sb, target_user_id, company_id, "[TAI Safe] 작업 지연", msg)
            notif_ok = True

    elif action_type == "NOTIFY_MANAGER":
        target_user_id = manager_info.get("id") or user_id
        if manager_info.get("allow_sms") and manager_info.get("phone"):
            sms_ok = _send_sms(manager_info["phone"], msg)
        if manager_info.get("allow_push") and manager_info.get("push_token"):
            fcm_ok = _send_fcm(manager_info["push_token"], "[TAI Safe] 지연 관리", msg)
        if target_user_id:
            _write_notification(sb, target_user_id, company_id, "[TAI Safe] 지연 관리", msg)
            notif_ok = True

    elif action_type == "MARK_OVERDUE":
        target_user_id = manager_info.get("id") or user_id
        if manager_info.get("allow_sms") and manager_info.get("phone"):
            sms_ok = _send_sms(manager_info["phone"], msg)
        if manager_info.get("allow_push") and manager_info.get("push_token"):
            fcm_ok = _send_fcm(manager_info["push_token"], "[TAI Safe] OVERDUE", msg)
        if target_user_id:
            _write_notification(sb, target_user_id, company_id, "[TAI Safe] OVERDUE 전환", msg)
            notif_ok = True
        try:
            sb.table("work_assignments").update({"status_code": "OVERDUE"}).eq("id", wa_id).execute()
        except Exception as e:
            log.error("[OVERDUE] status OVERDUE 업데이트 실패: %s", e)

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
        lvl, action_type, msg, sms_ok, fcm_ok, notif_ok,
    )

    return {
        "id": wa_id, "action": action_type, "level": lvl,
        "delta_days": delta, "sms": sms_ok, "fcm": fcm_ok,
        "notif": notif_ok, "history_id": hist_id,
    }


@router.post("/check")
def run_overdue_check(
    factory_id:  Optional[str] = Query(None),
    dry_run:     bool          = Query(False),
    limit:       int           = Query(500, ge=1, le=2000),
):
    """
    에스켈레이션 실행.
    v1.1.0: 현장별 notification_time 체크 — 설정 시간 미도달 현장은 스킵.
    cron 30분 간격 (06:00~09:30) 실행, 각 현장의 알림 시각에 맞춰 발송.
    기존 overdue_level 체크로 이미 발송된 건은 재발송 안함.
    """
    supabase = get_supabase()
    today    = _today()
    now_time = _now_kst_time()

    # 현장별 notification_time 로드
    factory_times = _load_factory_notification_times(supabase)

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
    results = []
    acted = 0
    skipped_cnt = 0
    skipped_not_time = 0

    for wa in assignments:
        # v1.1.0: 현장별 notification_time 체크
        fid = wa.get("factory_id")
        notif_time = factory_times.get(fid, dt_time(7, 0))  # 기본 07:00
        if now_time < notif_time:
            skipped_not_time += 1
            continue

        if dry_run:
            due = _effective_due(wa)
            if not due:
                skipped_cnt += 1; continue
            delta = (today - due).days
            target_level = 0
            for dd, lvl, act, _ in _LEVELS:
                if delta >= dd: target_level = lvl
            results.append({"id": wa["id"], "delta": delta,
                            "current_level": wa.get("overdue_level", 0),
                            "target_level": target_level,
                            "would_act": target_level > (wa.get("overdue_level") or 0),
                            "factory_notif_time": str(notif_time)})
        else:
            r = _process_one(supabase, wa, today)
            results.append(r)
            if r.get("action"):
                acted += 1
            else:
                skipped_cnt += 1

    return {
        "status": "dry_run" if dry_run else "success",
        "version": VERSION,
        "date": today.isoformat(),
        "current_kst_time": str(now_time)[:5],
        "checked": len(assignments),
        "acted": acted,
        "skipped": skipped_cnt,
        "skipped_not_time": skipped_not_time,
        "results": results,
    }


@router.get("/summary")
def get_overdue_summary(factory_id: Optional[str] = Query(None)):
    supabase = get_supabase()
    today    = _today()

    q = supabase.table("work_assignments").select(
        "id, factory_id, scheduled_date, due_date, overdue_level, status_code"
    ).not_.in_("status_code", ["DONE", "SKIP"])
    if factory_id:
        q = q.eq("factory_id", factory_id)

    res = q.execute()
    rows = res.data or []

    summary = {
        "total": len(rows), "normal": 0, "remind_d1": 0,
        "warn_d1": 0, "manager_d2": 0, "overdue_d7": 0, "no_due_date": 0,
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

    return {"status": "success", "date": today.isoformat(),
            "factory_id": factory_id or "all", "summary": summary}


@router.get("/history")
def get_overdue_history(
    factory_id: Optional[str] = Query(None),
    assignment_id: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    resolved: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
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

    return {"status": "success", "total": res.count or 0,
            "page": page, "size": size, "items": res.data or []}


class ResolveBody(BaseModel):
    resolved_by: Optional[str] = None
    resolve_note: Optional[str] = None


@router.post("/resolve/{history_id}")
def resolve_overdue(history_id: str, body: ResolveBody):
    supabase = get_supabase()
    now_iso  = datetime.now(timezone.utc).isoformat()

    hist_res = supabase.table("overdue_history").select(
        "id, assignment_id, resolved"
    ).eq("id", history_id).limit(1).execute()

    if not hist_res.data:
        raise HTTPException(status_code=404, detail="이력을 찾을 수 없습니다.")

    hist = hist_res.data[0]
    if hist.get("resolved"):
        raise HTTPException(status_code=409, detail="이미 해소 처리된 이력입니다.")

    upd: dict[str, Any] = {"resolved": True, "resolved_at": now_iso}
    if body.resolved_by:  upd["resolved_by"]  = body.resolved_by
    if body.resolve_note: upd["resolve_note"] = body.resolve_note

    supabase.table("overdue_history").update(upd).eq("id", history_id).execute()

    wa_id = hist["assignment_id"]
    try:
        supabase.table("work_assignments").update({
            "resolved_at": now_iso, "overdue_level": 0, "status_code": "DONE",
        }).eq("id", wa_id).execute()
    except Exception as e:
        log.warning("[OVERDUE] resolve wa 업데이트 실패: %s", e)

    _write_history(
        supabase, wa_id, None, body.resolved_by,
        0, "RESOLVE", body.resolve_note or "지연 해소",
        False, False, False,
    )

    return {"status": "success", "history_id": history_id,
            "assignment_id": wa_id, "resolved_at": now_iso}
