"""운영 자동화 서비스 (WO-12 AutomationEngine).

Goal: G-ms4je4z3-33eada (구축 이어받기 G-ms5pdquz-9e76e5)
- 엔진 자산과 분리된 운영 전용 자동화. event→condition→action.
- 입력: gmail_inbox_svc 수신 콜백(mail.inbound), 수동 fire, 결제 성공/실패 발화(P2-4),
        만료임박 스캔(scan_expiring_subscriptions → subscription.expiring).
- 출력: notify_svc.send(SEND_MAIL/SEND_SMS), CREATE_TASK/CALL_WEBHOOK/LLM_DRAFT.
- require_approval 게이트: 승인 필요 규칙은 APPROVAL_PENDING 적재 후 사람 승인 시 실행.
- 감사(audit_svc). automation_rule/run_log(RLS off).

CREATE_TASK (2026-07-30, G-ms5pdquz-9e76e5): 스텁 → 실구현.
  운영 태스크를 admin_ops_task(taieng 어드민 전용 테이블)에 적재한다.
  45CM 자산(runtime_task/task_master 등)은 쓰지 않는다 — 도메인 분리.
  같은 규칙·같은 트리거의 열린 태스크가 중복 생성되지 않도록 멱등 처리한다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from services import audit_svc

log = logging.getLogger(__name__)

EVENT_TYPES = ("mail.inbound", "payment.failed", "payment.success",
               "subscription.expiring", "manual")
ACTION_TYPES = ("SEND_MAIL", "SEND_SMS", "CREATE_TASK", "CALL_WEBHOOK", "LLM_DRAFT")

_PRIORITY = {"LOW", "NORMAL", "HIGH", "URGENT"}


class AutomationError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _rules_for(event_type: str) -> List[Dict[str, Any]]:
    res = (
        get_supabase().table("automation_rule")
        .select("*").eq("event_type", event_type).eq("enabled", True).execute()
    )
    return res.data or []


def _matches(condition: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    """조건 매칭(단순 동등/포함). condition 비면 항상 매칭.

    지원: {"field": "subject", "contains": "환불"} / {"field":"status","equals":"FAILED"}
    """
    if not condition:
        return True
    field = condition.get("field")
    if not field:
        return True
    value = str(payload.get(field, ""))
    if "equals" in condition:
        return value == str(condition["equals"])
    if "contains" in condition:
        return str(condition["contains"]) in value
    return True


def _log_run(rule_id: Optional[str], event_type: str, trigger_ref: Optional[str],
             matched: bool, status: str, action_type: Optional[str] = None,
             result: Optional[Dict[str, Any]] = None, error: Optional[str] = None,
             approved_by: Optional[str] = None) -> str:
    row = {
        "rule_id": rule_id, "event_type": event_type, "trigger_ref": trigger_ref,
        "matched": matched, "status": status, "action_type": action_type,
        "result_json": result, "error": error, "approved_by": approved_by,
    }
    res = get_supabase().table("automation_run_log").insert(row).execute()
    return res.data[0]["id"] if res.data else ""


def _create_ops_task(config: Dict[str, Any], payload: Dict[str, Any],
                     rule_id: Optional[str] = None, event_type: Optional[str] = None,
                     trigger_ref: Optional[str] = None) -> Dict[str, Any]:
    """운영 태스크를 admin_ops_task 에 적재. 멱등(같은 규칙·트리거의 열린 태스크 1건).

    config: {title?, description?, priority?, due_date?, assignee?}
    payload 의 값으로 제목 템플릿 치환({field})을 지원한다.
    """
    sb = get_supabase()

    def _fmt(s: Optional[str]) -> Optional[str]:
        if not s:
            return s
        try:
            return s.format(**{k: ("" if v is None else v) for k, v in (payload or {}).items()})
        except Exception:
            return s

    title = _fmt(config.get("title")) or _fmt(config.get("note")) or f"[자동화] {event_type or '태스크'}"
    priority = str(config.get("priority", "NORMAL")).upper()
    if priority not in _PRIORITY:
        priority = "NORMAL"

    # 멱등: 같은 규칙·트리거의 열린 태스크가 이미 있으면 재사용.
    if rule_id and trigger_ref:
        try:
            dup = (sb.table("admin_ops_task").select("id")
                   .eq("source", "AUTOMATION").eq("source_rule_id", rule_id)
                   .eq("trigger_ref", trigger_ref).eq("status", "OPEN")
                   .limit(1).execute().data)
            if dup:
                return {"task": "deduped", "task_id": dup[0]["id"], "title": title}
        except Exception:
            pass  # 테이블 미적용 등 — 아래 insert 에서 처리

    row = {
        "company_id": payload.get("company_id"),
        "title": title[:500],
        "description": _fmt(config.get("description")),
        "priority": priority,
        "status": "OPEN",
        "source": "AUTOMATION",
        "source_rule_id": rule_id,
        "source_event": event_type,
        "trigger_ref": trigger_ref,
        "due_date": config.get("due_date"),
        "assignee": config.get("assignee"),
        "created_by": "automation",
    }
    try:
        res = sb.table("admin_ops_task").insert(row).execute()
    except Exception as e:  # noqa: BLE001
        msg = str(e).lower()
        if any(h in msg for h in ("does not exist", "relation", "42p01", "schema cache")):
            raise AutomationError(409, "admin_ops_task 스키마가 아직 적용되지 않았습니다. 마이그레이션 적용 후 다시 시도하세요.")
        # 멱등 유니크 충돌 → 이미 열린 태스크 존재
        if "duplicate" in msg or "unique" in msg:
            return {"task": "deduped", "title": title}
        raise AutomationError(500, f"태스크 생성 실패: {e}")
    if not res.data:
        raise AutomationError(500, "태스크 생성에 실패했습니다.")
    return {"task": "created", "task_id": res.data[0]["id"], "title": title}


def _execute_action(action_type: str, config: Dict[str, Any],
                    payload: Dict[str, Any], rule_id: Optional[str] = None,
                    event_type: Optional[str] = None,
                    trigger_ref: Optional[str] = None) -> Dict[str, Any]:
    """액션 실행. notify_svc 등 위임."""
    if action_type == "SEND_MAIL":
        from services.notify_svc import send as notify_send
        to = config.get("to") or payload.get("from_email")
        if not to:
            raise AutomationError(400, "SEND_MAIL: 수신자 없음")
        return notify_send("MAIL", target=to, subject=config.get("subject", "(자동응답)"),
                           html=config.get("html"), message=config.get("text"))
    if action_type == "SEND_SMS":
        from services.notify_svc import send as notify_send
        to = config.get("to") or payload.get("phone")
        if not to:
            raise AutomationError(400, "SEND_SMS: 수신번호 없음")
        return notify_send("SMS", target=to, message=config.get("message", ""))
    if action_type == "CALL_WEBHOOK":
        return _call_webhook(config.get("url", ""), payload)
    if action_type == "CREATE_TASK":
        return _create_ops_task(config, payload, rule_id=rule_id,
                                event_type=event_type, trigger_ref=trigger_ref)
    if action_type == "LLM_DRAFT":
        # 엔진 LLM 미결합 — 인터페이스만. 초안 요청 흔적만 반환.
        return {"llm_draft": "queued", "prompt_key": config.get("prompt_key")}
    raise AutomationError(400, f"지원하지 않는 액션: {action_type}")


def _call_webhook(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not url:
        raise AutomationError(400, "CALL_WEBHOOK: url 없음")
    import requests as _requests
    try:
        resp = _requests.post(url, json=payload, timeout=10)
        return {"webhook_status": resp.status_code}
    except Exception as e:  # noqa: BLE001
        raise AutomationError(502, f"웹훅 호출 실패: {e}") from e


def fire(event_type: str, payload: Dict[str, Any],
         trigger_ref: Optional[str] = None) -> Dict[str, Any]:
    """이벤트 발화 → 규칙 매칭 → 실행/승인대기 적재."""
    if event_type not in EVENT_TYPES:
        raise AutomationError(400, f"지원하지 않는 이벤트: {event_type}")

    rules = _rules_for(event_type)
    outcomes = []
    for rule in rules:
        matched = _matches(rule.get("condition_json") or {}, payload)
        if not matched:
            _log_run(rule["id"], event_type, trigger_ref, False, "SKIPPED", rule.get("action_type"))
            outcomes.append({"rule_code": rule["rule_code"], "status": "SKIPPED"})
            continue

        if rule.get("require_approval"):
            run_id = _log_run(rule["id"], event_type, trigger_ref, True, "APPROVAL_PENDING",
                              rule.get("action_type"), result={"payload": payload, "config": rule.get("action_config_json")})
            outcomes.append({"rule_code": rule["rule_code"], "status": "APPROVAL_PENDING", "run_id": run_id})
            continue

        # 즉시 실행
        try:
            result = _execute_action(rule["action_type"], rule.get("action_config_json") or {}, payload,
                                     rule_id=rule["id"], event_type=event_type, trigger_ref=trigger_ref)
            _log_run(rule["id"], event_type, trigger_ref, True, "RUN", rule["action_type"], result=result)
            outcomes.append({"rule_code": rule["rule_code"], "status": "RUN", "result": result})
        except Exception as e:  # noqa: BLE001
            _log_run(rule["id"], event_type, trigger_ref, True, "FAILED", rule["action_type"], error=str(e))
            outcomes.append({"rule_code": rule["rule_code"], "status": "FAILED", "error": str(e)})

    audit_svc.record("AUTOMATION_FIRE", "automation", entity_id=trigger_ref, actor_id="system",
                     after={"event_type": event_type, "matched_rules": len(outcomes)})
    return {"event_type": event_type, "outcomes": outcomes}


def approve_run(run_id: str, actor: Optional[str] = None) -> Dict[str, Any]:
    """승인 대기 건 실행."""
    supabase = get_supabase()
    run = supabase.table("automation_run_log").select("*").eq("id", run_id).limit(1).execute()
    if not run.data:
        raise AutomationError(404, "실행 건을 찾을 수 없습니다.")
    r = run.data[0]
    if r["status"] != "APPROVAL_PENDING":
        raise AutomationError(409, "승인 대기 상태가 아닙니다.")

    rule = supabase.table("automation_rule").select("*").eq("id", r["rule_id"]).limit(1).execute()
    if not rule.data:
        raise AutomationError(404, "규칙을 찾을 수 없습니다.")
    rule = rule.data[0]

    stored = r.get("result_json") or {}
    payload = stored.get("payload", {})
    config = stored.get("config") or rule.get("action_config_json") or {}
    try:
        result = _execute_action(rule["action_type"], config, payload,
                                 rule_id=rule["id"], event_type=r.get("event_type"),
                                 trigger_ref=r.get("trigger_ref"))
        supabase.table("automation_run_log").update(
            {"status": "APPROVED_RUN", "result_json": result, "approved_by": actor}
        ).eq("id", run_id).execute()
        audit_svc.record("AUTOMATION_APPROVE", "automation", entity_id=run_id, actor_id=actor,
                         after={"action": rule["action_type"], "result": result})
        return {"status": "APPROVED_RUN", "result": result}
    except Exception as e:  # noqa: BLE001
        supabase.table("automation_run_log").update(
            {"status": "FAILED", "error": str(e), "approved_by": actor}
        ).eq("id", run_id).execute()
        raise AutomationError(502, f"실행 실패: {e}") from e


# ── 운영 태스크 조회/완료 (admin_ops_task) ───────────────────────────
def list_ops_tasks(status: Optional[str] = None, company_id: Optional[str] = None,
                   limit: int = 100) -> List[Dict[str, Any]]:
    try:
        q = get_supabase().table("admin_ops_task").select("*")
        if status:
            q = q.eq("status", status)
        if company_id:
            q = q.eq("company_id", company_id)
        return (q.order("created_at", desc=True).limit(limit).execute().data) or []
    except Exception:
        return []


def close_ops_task(task_id: str, status: str = "DONE", actor: Optional[str] = None) -> Dict[str, Any]:
    if status not in ("DONE", "CANCELED"):
        raise AutomationError(400, "status 는 DONE 또는 CANCELED 여야 합니다.")
    now = datetime.now(timezone.utc).isoformat()
    res = (get_supabase().table("admin_ops_task")
           .update({"status": status, "done_at": now, "updated_at": now})
           .eq("id", task_id).execute())
    if not res.data:
        raise AutomationError(404, "태스크를 찾을 수 없습니다.")
    audit_svc.record("OPS_TASK_CLOSE", "admin_ops_task", entity_id=task_id, actor_id=actor,
                     after={"status": status})
    return res.data[0]


# ── 만료임박 구독 스캔 → subscription.expiring 발화 (WO-12 / P2-4) ─────
def scan_expiring_subscriptions(days: int = 7) -> Dict[str, Any]:
    """만료 임박(SUCCESS 결제의 expired_at ∈ [now, now+days]) 건을 스캔해
    각 건에 subscription.expiring 이벤트를 발화한다.

    자동 발화 소스(수동 fire 외)를 넓히기 위한 진입점. 운영자/크론에서 주기 호출.
    개별 발화 실패는 삼켜서 스캔 전체를 막지 않는다.
    """
    now = datetime.now(timezone.utc)
    deadline = (now + timedelta(days=days)).isoformat()
    rows = (
        get_supabase().table("v_payments_list")
        .select("id, company_id, user_id, plan_code, product_type, total_amount, expired_at")
        .eq("status_code", "SUCCESS")
        .lte("expired_at", deadline).gte("expired_at", now.isoformat())
        .execute()
    ).data or []

    fired = 0
    for r in rows:
        try:
            fire("subscription.expiring", {
                "payment_id": r.get("id"),
                "company_id": r.get("company_id"),
                "user_id": r.get("user_id"),
                "plan_code": r.get("plan_code"),
                "product_type": r.get("product_type"),
                "total_amount": r.get("total_amount"),
                "expired_at": r.get("expired_at"),
            }, trigger_ref=r.get("id"))
            fired += 1
        except Exception as e:  # noqa: BLE001
            log.warning("[AUTOMATION] subscription.expiring 발화 실패: %s", e)

    return {"scanned": len(rows), "fired": fired, "days": days}


# ── 수신 콜백 결합 (WO-8B → WO-12) ───────────────────────────────────
def _on_mail_inbound(mail_log_id: str, parsed: Dict[str, Any]) -> None:
    """gmail_inbox_svc 수신 콜백 → mail.inbound 이벤트 발화."""
    try:
        fire("mail.inbound", {
            "from_email": parsed.get("from_email"),
            "subject": parsed.get("subject"),
            "snippet": parsed.get("snippet"),
        }, trigger_ref=mail_log_id)
    except Exception as e:  # noqa: BLE001
        log.warning("[AUTOMATION] mail.inbound 처리 실패: %s", e)


def register() -> None:
    """부팅 시 1회: 수신 콜백 등록."""
    try:
        from services.gmail_inbox_svc import register_inbound_handler
        register_inbound_handler(_on_mail_inbound)
        log.info("[AUTOMATION] mail.inbound 콜백 등록 완료")
    except Exception as e:  # noqa: BLE001
        log.warning("[AUTOMATION] 콜백 등록 실패: %s", e)
