"""
routers/overdue_checker.py — v1.2.0

v1.2.0 (2026-04-17):
  [BREAKING] 큐 기반 알림 구조 전환
  - POST /overdue/prepare  (04:00 KST) → 전체 스캔, notification_queue에 예약 생성
  - POST /overdue/dispatch  (매 10분 05:00~10:50) → 시간 도달 건 발송
  - 현장별 factories.notification_time 기반 발송 시각 결정
  - 기존 /check는 호환용 유지 (prepare+dispatch 통합 실행)

v1.1.0: 현장별 notification_time 필터 (30분 간격)
v1.0.0: 초기 구현
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

VERSION = "1.2.0"
KST = ZoneInfo("Asia/Seoul")

_SMS_EDGE = "https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/send-sms"
_FCM_EDGE = os.getenv(
    "FCM_EDGE_URL",
    "https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/send-push"
)

_LEVELS = [
    (-1, 1, "REMIND",         "[TAI Safe] 내일 점검 예정",
     "[TAI Safe] 내일 {task} 마감입니다. 오늘 안에 완료해 주세요."),
    ( 1, 2, "WARN_WORKER",    "[TAI Safe] 점검 지연 경고",
     "[TAI Safe] {task} 작업이 {days}일 지연되었습니다. 즉시 완료해 주세요."),
    ( 2, 3, "NOTIFY_MANAGER", "[TAI Safe] 미이행 에스컬레이션",
     "[TAI Safe] ⚠ {task} 2일 이상 미완료. 담당: {worker}"),
    ( 7, 4, "MARK_OVERDUE",   "[TAI Safe] OVERDUE 전환",
     "[TAI Safe] {task}가 7일 이상 미완료되어 OVERDUE 전환되었습니다."),
]


def _today_kst() -> date:
    return datetime.now(KST).date()

def _now_kst() -> datetime:
    return datetime.now(KST)

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
    if isinstance(t, dt_time):
        return t
    if not t:
        return dt_time(7, 0)
    try:
        parts = str(t).split(":")
        return dt_time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    except (ValueError, IndexError):
        return dt_time(7, 0)


# ── 발송 헬퍼 ─────────────────────────────────────────────────────────

def _send_sms(phone: str, message: str) -> bool:
    if not phone: return False
    try:
        resp = _req.post(_SMS_EDGE,
            json={"receiver": phone, "message": message, "type": "sms"}, timeout=20)
        result = resp.json() if "json" in resp.headers.get("content-type", "") else {}
        ok = bool(result.get("success")) or resp.status_code < 300
        log.info("[OVERDUE] SMS %s → %s", phone[-4:], "OK" if ok else "FAIL")
        return ok
    except Exception as e:
        log.warning("[OVERDUE] SMS 실패: %s", e)
        return False

def _send_fcm(push_token: str, title: str, body: str) -> bool:
    if not push_token: return False
    try:
        resp = _req.post(_FCM_EDGE,
            json={"token": push_token, "title": title, "body": body}, timeout=20)
        return resp.status_code < 300
    except Exception as e:
        log.warning("[OVERDUE] FCM 실패: %s", e)
        return False

def _write_notification(sb, user_id, company_id, title, body):
    try:
        sb.table("notifications").insert({
            "user_id": user_id, "company_id": company_id,
            "trigger_code": "OVERDUE_ESCALATION", "trigger_group": "OVERDUE",
            "title": title, "body": body, "priority": "HIGH",
            "is_read": False, "channel": "push", "send_status": "SENT",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.warning("[OVERDUE] notification INSERT 실패: %s", e)

def _write_history(sb, assignment_id, factory_id, user_id,
                   level, action, msg, sms, fcm, notif):
    try:
        res = sb.table("overdue_history").insert({
            "assignment_id": assignment_id, "factory_id": factory_id,
            "assigned_user_id": user_id, "overdue_level": level,
            "action_type": action, "message_body": msg,
            "sms_sent": sms, "fcm_sent": fcm, "notif_sent": notif,
        }).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        log.error("[OVERDUE] history INSERT 실패: %s", e)
        return None


# ── POST /overdue/prepare ─────────────────────────────────────────────

@router.post("/prepare")
def prepare_overdue_queue(
    factory_id: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
):
    """
    04:00 KST cron 실행.
    전체 work_assignments 스캔 → notification_queue에 발송 예약 INSERT.
    각 건의 scheduled_send_at = 해당 현장의 notification_time (오늘 날짜 기준).
    이미 해당 level로 발송/큐잉된 건은 스킵.
    """
    sb    = get_supabase()
    today = _today_kst()

    # 현장별 notification_time 로드
    try:
        fac_res = sb.table("factories").select("id, notification_time").execute()
        fac_times = {r["id"]: _parse_time(r.get("notification_time")) for r in (fac_res.data or [])}
    except Exception:
        fac_times = {}

    # 미완료 assignments
    q = sb.table("work_assignments") \
        .select("id, factory_id, assigned_user_id, scheduled_date, due_date,"
                " overdue_level, status_code, inspection_set_id") \
        .not_.in_("status_code", ["DONE", "SKIP", "OVERDUE"]) \
        .limit(limit)
    if factory_id:
        q = q.eq("factory_id", factory_id)

    assignments = (q.execute()).data or []
    queued = 0
    skipped = 0

    for wa in assignments:
        due = _effective_due(wa)
        if not due:
            skipped += 1
            continue

        delta = (today - due).days
        cur_lvl = wa.get("overdue_level") or 0

        # 대상 level 결정
        target_level = 0
        for dd, lvl, _, _, _ in _LEVELS:
            if delta >= dd:
                target_level = lvl

        if target_level <= cur_lvl:
            skipped += 1
            continue

        cfg = next((x for x in _LEVELS if x[1] == target_level), None)
        if not cfg:
            skipped += 1
            continue

        _, lvl, action_type, title_tpl, body_tpl = cfg
        fid = wa.get("factory_id")
        notif_time = fac_times.get(fid, dt_time(7, 0))

        # scheduled_send_at = 오늘 + 현장 notification_time (KST → UTC)
        send_kst = datetime.combine(today, notif_time, tzinfo=KST)
        send_utc = send_kst.astimezone(timezone.utc)

        task_name = wa.get("task_name") or wa.get("inspection_set_id") or "점검 작업"
        title = title_tpl
        body = body_tpl.replace("{task}", str(task_name)).replace("{days}", str(abs(delta))).replace("{worker}", "")

        # 대상: WORKER(level 1,2) or MANAGER(level 3,4)
        target_role = "MANAGER" if action_type in ("NOTIFY_MANAGER", "MARK_OVERDUE") else "WORKER"
        target_uid = wa.get("assigned_user_id")

        # 중복 큐 체크 (오늘 같은 assignment + level)
        try:
            dup = sb.table("notification_queue") \
                .select("id") \
                .eq("assignment_id", wa["id"]) \
                .eq("overdue_level", lvl) \
                .gte("created_at", today.isoformat()) \
                .limit(1).execute()
            if dup.data:
                skipped += 1
                continue
        except Exception:
            pass

        try:
            sb.table("notification_queue").insert({
                "assignment_id": wa["id"],
                "factory_id": fid,
                "target_user_id": target_uid,
                "target_role": target_role,
                "action_type": action_type,
                "overdue_level": lvl,
                "message_title": title,
                "message_body": body,
                "scheduled_send_at": send_utc.isoformat(),
                "sent": False,
            }).execute()
            queued += 1
        except Exception as e:
            log.error("[OVERDUE] queue INSERT 실패: %s", e)

    return {
        "status": "success", "version": VERSION,
        "date": today.isoformat(),
        "scanned": len(assignments), "queued": queued, "skipped": skipped,
    }


# ── POST /overdue/dispatch ────────────────────────────────────────────

@router.post("/dispatch")
def dispatch_overdue_queue(
    limit: int = Query(100, ge=1, le=500),
):
    """
    매 10분 cron 실행 (05:00~10:50 KST).
    notification_queue에서 scheduled_send_at <= now() AND sent=false 건만 발송.
    """
    sb  = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    # 발송 대상 조회
    q_res = sb.table("notification_queue") \
        .select("*") \
        .eq("sent", False) \
        .lte("scheduled_send_at", now) \
        .order("scheduled_send_at") \
        .limit(limit) \
        .execute()

    items = q_res.data or []
    sent_count = 0
    errors = 0

    for item in items:
        qid = item["id"]
        uid = item.get("target_user_id")
        role = item.get("target_role", "WORKER")
        action = item.get("action_type")
        fid = item.get("factory_id")
        aid = item.get("assignment_id")
        title = item.get("message_title", "")
        body = item.get("message_body", "")
        level = item.get("overdue_level", 0)

        # 발송 대상 정보 조회
        user_info = {}
        if role == "MANAGER" and fid:
            try:
                mr = sb.table("users").select(
                    "id, name, phone, push_token, allow_sms, allow_push, company_id"
                ).eq("factory_id", fid).in_(
                    "role_code", ["001", "002"]
                ).eq("is_active", True).limit(1).execute()
                user_info = mr.data[0] if mr.data else {}
            except Exception:
                pass
        if not user_info and uid:
            try:
                ur = sb.table("users").select(
                    "id, name, phone, push_token, allow_sms, allow_push, company_id"
                ).eq("id", uid).limit(1).execute()
                user_info = ur.data[0] if ur.data else {}
            except Exception:
                pass

        if not user_info:
            # 유저 없으면 sent 표시하고 스킵
            sb.table("notification_queue").update({
                "sent": True, "sent_at": now,
                "sms_result": False, "fcm_result": False,
            }).eq("id", qid).execute()
            continue

        # {worker} 치환
        worker_name = user_info.get("name") or "작업자"
        body = body.replace("{worker}", worker_name)

        # 발송
        sms_ok = False
        fcm_ok = False

        if user_info.get("allow_sms") and user_info.get("phone"):
            sms_ok = _send_sms(user_info["phone"], body)
        if user_info.get("allow_push") and user_info.get("push_token"):
            fcm_ok = _send_fcm(user_info["push_token"], title, body)

        # notifications 테이블
        actual_uid = user_info.get("id") or uid
        if actual_uid:
            _write_notification(sb, actual_uid, user_info.get("company_id"), title, body)

        # 큐 sent 업데이트
        sb.table("notification_queue").update({
            "sent": True, "sent_at": now,
            "sms_result": sms_ok, "fcm_result": fcm_ok,
        }).eq("id", qid).execute()

        # work_assignments overdue_level 업데이트
        if aid:
            upd = {"overdue_level": level, "last_reminded_at": now}
            if action == "MARK_OVERDUE":
                upd["status_code"] = "OVERDUE"
            try:
                sb.table("work_assignments").update(upd).eq("id", aid).execute()
            except Exception as e:
                log.error("[OVERDUE] assignment 업데이트 실패: %s", e)

        # history 기록
        _write_history(sb, aid, fid, uid, level, action, body, sms_ok, fcm_ok, True)
        sent_count += 1

    return {
        "status": "success", "version": VERSION,
        "dispatched": sent_count, "pending_checked": len(items),
        "errors": errors,
    }


# ── POST /overdue/check (호환용) ──────────────────────────────────────

@router.post("/check")
def run_overdue_check(
    factory_id: Optional[str] = Query(None),
    dry_run: bool = Query(False),
    limit: int = Query(500, ge=1, le=2000),
):
    """호환용: prepare + dispatch 통합 실행."""
    if dry_run:
        sb = get_supabase()
        today = _today_kst()
        q = sb.table("work_assignments") \
            .select("id, factory_id, scheduled_date, due_date, overdue_level, status_code") \
            .not_.in_("status_code", ["DONE", "SKIP", "OVERDUE"]).limit(limit)
        if factory_id:
            q = q.eq("factory_id", factory_id)
        rows = (q.execute()).data or []
        results = []
        for wa in rows:
            due = _effective_due(wa)
            if not due: continue
            delta = (today - due).days
            tgt = 0
            for dd, lv, _, _, _ in _LEVELS:
                if delta >= dd: tgt = lv
            results.append({
                "id": wa["id"], "delta": delta,
                "current_level": wa.get("overdue_level", 0),
                "target_level": tgt,
                "would_act": tgt > (wa.get("overdue_level") or 0),
            })
        return {"status": "dry_run", "checked": len(rows), "results": results}

    prep = prepare_overdue_queue(factory_id=factory_id, limit=limit)
    disp = dispatch_overdue_queue(limit=limit)
    return {
        "status": "success", "version": VERSION,
        "prepare": prep, "dispatch": disp,
    }


# ── GET /overdue/summary ──────────────────────────────────────────────

@router.get("/summary")
def get_overdue_summary(factory_id: Optional[str] = Query(None)):
    sb = get_supabase()
    today = _today_kst()
    q = sb.table("work_assignments").select(
        "id, factory_id, scheduled_date, due_date, overdue_level, status_code"
    ).not_.in_("status_code", ["DONE", "SKIP"])
    if factory_id:
        q = q.eq("factory_id", factory_id)
    rows = (q.execute()).data or []
    summary = {"total": len(rows), "normal": 0, "remind_d1": 0,
               "warn_d1": 0, "manager_d2": 0, "overdue_d7": 0, "no_due_date": 0}
    for wa in rows:
        if wa["status_code"] == "OVERDUE" or (wa.get("overdue_level") or 0) >= 4:
            summary["overdue_d7"] += 1
        elif (wa.get("overdue_level") or 0) == 3: summary["manager_d2"] += 1
        elif (wa.get("overdue_level") or 0) == 2: summary["warn_d1"] += 1
        elif (wa.get("overdue_level") or 0) == 1: summary["remind_d1"] += 1
        elif not _effective_due(wa): summary["no_due_date"] += 1
        else: summary["normal"] += 1
    return {"status": "success", "date": today.isoformat(),
            "factory_id": factory_id or "all", "summary": summary}


# ── GET /overdue/queue ────────────────────────────────────────────────

@router.get("/queue")
def get_queue_status(
    sent: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """오늘의 큐 현황 조회."""
    sb = get_supabase()
    today = _today_kst()
    offset = (page - 1) * size
    q = sb.table("notification_queue").select(
        "id, assignment_id, factory_id, target_role, action_type,"
        " overdue_level, message_title, scheduled_send_at,"
        " sent, sent_at, sms_result, fcm_result, created_at",
        count="exact"
    ).gte("created_at", today.isoformat()).order("scheduled_send_at")
    if sent is not None:
        q = q.eq("sent", sent)
    res = q.range(offset, offset + size - 1).execute()
    return {"status": "success", "date": today.isoformat(),
            "total": res.count or 0, "page": page, "items": res.data or []}


# ── GET /overdue/history ──────────────────────────────────────────────

@router.get("/history")
def get_overdue_history(
    factory_id: Optional[str] = Query(None),
    assignment_id: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    resolved: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    sb = get_supabase()
    offset = (page - 1) * size
    q = sb.table("overdue_history").select(
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
    sb = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    hist_res = sb.table("overdue_history").select(
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
    sb.table("overdue_history").update(upd).eq("id", history_id).execute()
    wa_id = hist["assignment_id"]
    try:
        sb.table("work_assignments").update({
            "resolved_at": now_iso, "overdue_level": 0, "status_code": "DONE",
        }).eq("id", wa_id).execute()
    except Exception as e:
        log.warning("[OVERDUE] resolve 실패: %s", e)
    _write_history(sb, wa_id, None, body.resolved_by,
                   0, "RESOLVE", body.resolve_note or "지연 해소",
                   False, False, False)
    return {"status": "success", "history_id": history_id,
            "assignment_id": wa_id, "resolved_at": now_iso}
