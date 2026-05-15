"""Synthetic Login Scenario — 로그인 업무 heartbeat.

실제 API를 호출하여 로그인이 끝까지 성공하는지 확인.
"""

import logging
import os
import requests

from watch_engine import create_trace, emit_event
from watch_engine.trace import clear_trace

logger = logging.getLogger("watch_engine.synthetic.login")

# Credentials from env (never hardcode)
SYNTHETIC_EMAIL = os.environ.get("SYNTHETIC_TEST_EMAIL", "")
SYNTHETIC_PASSWORD = os.environ.get("SYNTHETIC_TEST_PASSWORD", "")


def run_login_scenario(run_id: str, base_url: str) -> dict:
    """Execute login synthetic scenario.

    Steps:
        0. submit_credentials — POST /auth/login
        1. validate_auth — check response status
        2. session_issued — verify token exists

    Returns:
        {"scenario": "login", "status": "passed"|"failed"|"error",
         "steps_completed": int, "detail": {...}}
    """
    result = {
        "scenario": "login",
        "status": "error",
        "steps_completed": 0,
        "detail": {},
    }

    # Pre-check: credentials available?
    if not SYNTHETIC_EMAIL or not SYNTHETIC_PASSWORD:
        result["status"] = "error"
        result["detail"] = {"reason": "SYNTHETIC_TEST_EMAIL/PASSWORD not configured"}
        logger.warning("Login synthetic skipped: no credentials")
        return result

    trace = create_trace(
        flow_key="login",
        tenant_id="tai",
        actor_type="synthetic_user",
        scenario_run_id=run_id,
    )

    try:
        # Step 0: submit_credentials
        emit_event(
            step_key="submit_credentials", step_order=0,
            event_type="submit", result="success",
            connector_type="api",
            payload_summary={"synthetic": True, "has_identifier": True, "has_password": True},
        )

        resp = requests.post(
            f"{base_url}/auth/login",
            json={"identifier": SYNTHETIC_EMAIL, "password": SYNTHETIC_PASSWORD},
            timeout=15,
        )
        result["steps_completed"] = 1

        # Step 1: validate_auth
        if resp.status_code >= 400:
            emit_event(
                step_key="validate_auth", step_order=1,
                event_type="validate", result="failure",
                connector_type="api",
                payload_summary={"synthetic": True, "status_code": resp.status_code},
            )
            result["status"] = "failed"
            result["detail"] = {"step": "validate_auth", "status_code": resp.status_code}
            clear_trace()
            return result

        emit_event(
            step_key="validate_auth", step_order=1,
            event_type="validate", result="success",
            connector_type="api",
            payload_summary={"synthetic": True, "status_code": resp.status_code},
        )
        result["steps_completed"] = 2

        # Step 2: session_issued
        body = {}
        try:
            body = resp.json()
        except Exception:
            pass

        has_token = bool(
            body.get("access_token")
            or body.get("token")
            or (body.get("data") or {}).get("access_token")
        )

        emit_event(
            step_key="session_issued", step_order=2,
            event_type="read", result="success" if has_token else "failure",
            connector_type="api",
            payload_summary={"synthetic": True, "has_token": has_token},
        )
        result["steps_completed"] = 3

        if has_token:
            result["status"] = "passed"
            result["detail"] = {"steps": 3, "has_token": True}
        else:
            result["status"] = "failed"
            result["detail"] = {"step": "session_issued", "has_token": False}

    except requests.Timeout:
        emit_event(
            step_key="submit_credentials", step_order=0,
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
