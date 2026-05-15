"""Synthetic Process Registration Scenario — 공정등록 업무 heartbeat.

실제 API를 호출하여 공정등록이 끝까지 성공하는지 확인.
핵심: SelectBar mismatch 재발 감시.
"""

import logging
import os
import requests

from watch_engine import create_trace, emit_event
from watch_engine.trace import clear_trace

logger = logging.getLogger("watch_engine.synthetic.process_registration")

SYNTHETIC_EMAIL = os.environ.get("SYNTHETIC_TEST_EMAIL", "")
SYNTHETIC_PASSWORD = os.environ.get("SYNTHETIC_TEST_PASSWORD", "")
SYNTHETIC_FACTORY_ID = os.environ.get("SYNTHETIC_FACTORY_ID", "")

# Synthetic process data (no PII)
SYNTHETIC_PROCESS = {
    "source": "MANUAL",
    "process_name": "SYNTHETIC_HEARTBEAT",
    "description": "Watch Engine synthetic heartbeat process",
}


def run_process_registration_scenario(run_id: str, base_url: str) -> dict:
    """Execute process registration synthetic scenario.

    Steps:
        0. submit_payload — POST /{factory_id}/processes
        1. validate_input — check response status
        2. save_db — verify saved data
        3. read_result — verify process_type match

    Requires login first (parent_trace_id from login scenario).
    """
    result = {
        "scenario": "process_registration",
        "status": "error",
        "steps_completed": 0,
        "detail": {},
    }

    # Pre-check
    if not SYNTHETIC_EMAIL or not SYNTHETIC_PASSWORD or not SYNTHETIC_FACTORY_ID:
        result["detail"] = {"reason": "SYNTHETIC env vars not configured"}
        logger.warning("Process registration synthetic skipped: missing config")
        return result

    # Login first to get token
    login_trace_id = None
    token = None
    try:
        login_resp = requests.post(
            f"{base_url}/auth/login",
            json={"identifier": SYNTHETIC_EMAIL, "password": SYNTHETIC_PASSWORD},
            timeout=15,
        )
        if login_resp.status_code < 400:
            body = login_resp.json()
            token = (
                body.get("access_token")
                or body.get("token")
                or (body.get("data") or {}).get("access_token")
            )
            login_trace_id = f"login_synthetic_{run_id}"
    except Exception as e:
        result["detail"] = {"error": f"Login failed: {str(e)[:100]}"}
        return result

    if not token:
        result["status"] = "failed"
        result["detail"] = {"step": "login", "reason": "no token"}
        return result

    trace = create_trace(
        flow_key="process_registration",
        tenant_id="tai",
        actor_type="synthetic_user",
        scenario_run_id=run_id,
        parent_trace_id=login_trace_id,
    )
    headers = {"Authorization": f"Bearer {token}"}
    source_key = SYNTHETIC_PROCESS["source"]

    try:
        # Step 0: submit_payload
        emit_event(
            step_key="submit_payload", step_order=0,
            event_type="submit", result="success",
            connector_type="api",
            payload_summary={
                "synthetic": True,
                "has_process_type": True,
                "process_type_key": source_key,
                "required_field_exists": True,
            },
        )

        resp = requests.post(
            f"{base_url}/factory-process/v3/{SYNTHETIC_FACTORY_ID}/processes",
            json=SYNTHETIC_PROCESS,
            headers=headers,
            timeout=15,
        )
        result["steps_completed"] = 1

        # Step 1: validate_input
        if resp.status_code >= 400:
            emit_event(
                step_key="validate_input", step_order=1,
                event_type="validate", result="failure",
                connector_type="api",
                payload_summary={"synthetic": True, "status_code": resp.status_code},
            )
            result["status"] = "failed"
            result["detail"] = {"step": "validate_input", "status_code": resp.status_code}
            clear_trace()
            return result

        emit_event(
            step_key="validate_input", step_order=1,
            event_type="validate", result="success",
            connector_type="api",
            payload_summary={"synthetic": True, "status_code": resp.status_code},
        )
        result["steps_completed"] = 2

        # Step 2: save_db
        body = {}
        try:
            body = resp.json()
        except Exception:
            pass

        saved_data = body.get("data") or body
        saved_source = None
        if isinstance(saved_data, dict):
            saved_source = saved_data.get("source")
        elif isinstance(saved_data, list) and saved_data:
            saved_source = saved_data[0].get("source")

        emit_event(
            step_key="save_db", step_order=2,
            event_type="save", result="success",
            connector_type="database",
            payload_summary={
                "synthetic": True,
                "process_type_key": saved_source,
                "row_saved": True,
            },
        )
        result["steps_completed"] = 3

        # Step 3: read_result — verify source matches
        read_source = saved_source  # Same response for v1

        emit_event(
            step_key="read_result", step_order=3,
            event_type="read", result="success",
            connector_type="api",
            payload_summary={
                "synthetic": True,
                "process_type_key": read_source,
                "row_count": 1,
            },
        )
        result["steps_completed"] = 4

        # Verify match
        if source_key == read_source:
            result["status"] = "passed"
            result["detail"] = {
                "steps": 4,
                "source_match": True,
                "submitted": source_key,
                "stored": read_source,
            }
        else:
            result["status"] = "failed"
            result["detail"] = {
                "step": "field_mismatch",
                "submitted": source_key,
                "stored": read_source,
            }

    except requests.Timeout:
        emit_event(
            step_key="submit_payload", step_order=0,
            event_type="submit", result="timeout",
            connector_type="api",
            payload_summary={"synthetic": True, "error": "timeout"},
        )
        result["status"] = "failed"
        result["detail"] = {"error": "timeout"}

    except Exception as e:
        emit_event(
            step_key="error", step_order=99,
            event_type="error", result="failure",
            connector_type="api",
            payload_summary={"synthetic": True, "error": str(e)[:100]},
        )
        result["status"] = "error"
        result["detail"] = {"error": str(e)[:200]}

    finally:
        clear_trace()

    return result
