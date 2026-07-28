"""운영 자동화 서비스 (WO-12 AutomationEngine).

Goal: G-ms4je4z3-33eada
- 엔진 자산과 분리된 운영 전용 자동화. event→condition→action.
- 입력: gmail_inbox_svc 수신 콜백(mail.inbound), 수동 fire.
- 출력: notify_svc.send(SEND_MAIL/SEND_SMS), CREATE_TASK/CALL_WEBHOOK/LLM_DRAFT.
- require_approval 게이트: 승인 필요 규칙은 APPROVAL_PENDING 적재 후 사람 승인 시 실행.
- 감사(audit_svc). automation_rule/run_log(RLS off).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from services import audit_svc

log = logging.getLogger(__name__)

EVENT_TYPES = ("mail.inbound", "payment.failed", "payment.success",
               "subscription.expiring", "manual")
ACTION_TYPES = ("SEND_MAIL", "SEND_SMS", "CREATE_TASK", "CALL_WEBHOOK", "LLM_DRAFT")


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


def _execute_action(action_type: str, config: Dict[str, Any],
                    payload: Dict[str, Any]) -> Dict[str, Any]:
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
        # 운영 태스크 적재(간단): automation_run_log가 곧 태스크 흔적. 별도 태스크 테이블은 후속.
        return {"task": "created", "note": config.get("note", "")}
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
            result = _execute_action(rule["action_type"], rule.get("action_config_json") or {}, payload)
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
        result = _execute_action(rule["action_type"], config, payload)
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
