"""Browser Synthetic — Login Flow v1.1.

data-testid selector 기반.
Fallback: CSS selector.
"""

import logging
import os

from watch_engine import create_trace, emit_event
from watch_engine.trace import clear_trace
from watch_engine.browser_synthetic.base import (
    browser_context, safe_click, safe_fill, safe_retry_click,
    wait_for_url, tid, PLAYWRIGHT_BASE_URL,
    TIMEOUT_PAGE_LOAD, TIMEOUT_SUBMIT_RESULT,
)

logger = logging.getLogger("watch_engine.browser_synthetic.login_browser")

SYNTHETIC_EMAIL = os.environ.get("SYNTHETIC_TEST_EMAIL", "")
SYNTHETIC_PASSWORD = os.environ.get("SYNTHETIC_TEST_PASSWORD", "")

# Selector 규약: data-testid 우선, CSS fallback
SEL_EMAIL = f"{tid('login-email-input')}, input[type='email'], input[name='email']"
SEL_PASSWORD = f"{tid('login-password-input')}, input[type='password']"
SEL_SUBMIT = f"{tid('login-submit-btn')}, button[type='submit']"


async def run_login_browser(run_id: str) -> dict:
    result = {"scenario": "login_browser", "status": "error", "steps_completed": 0, "detail": {}}

    if not SYNTHETIC_EMAIL or not SYNTHETIC_PASSWORD:
        result["detail"] = {"reason": "SYNTHETIC_TEST_EMAIL/PASSWORD not configured"}
        return result

    trace = create_trace(flow_key="login_browser", tenant_id="tai",
                         actor_type="synthetic_user", scenario_run_id=run_id)

    try:
        async with browser_context() as ctx:
            page = await ctx.new_page()

            # 0: open
            await page.goto(f"{PLAYWRIGHT_BASE_URL}/login", wait_until="domcontentloaded", timeout=TIMEOUT_PAGE_LOAD)
            emit_event(step_key="open_login_page", step_order=0, event_type="submit",
                       result="success", connector_type="browser",
                       payload_summary={"synthetic": True, "page": "/login"})
            result["steps_completed"] = 1

            # 1: email
            r = await safe_fill(page, SEL_EMAIL, SYNTHETIC_EMAIL)
            emit_event(step_key="input_email", step_order=1, event_type="submit",
                       result="success" if r["ok"] else "failure", connector_type="browser",
                       payload_summary={"synthetic": True, "ok": r["ok"], "error": r.get("error")})
            if not r["ok"]:
                result["status"] = "failed"; result["detail"] = {"step": "input_email", **r}; clear_trace(); return result
            result["steps_completed"] = 2

            # 2: password
            r = await safe_fill(page, SEL_PASSWORD, SYNTHETIC_PASSWORD)
            emit_event(step_key="input_password", step_order=2, event_type="submit",
                       result="success" if r["ok"] else "failure", connector_type="browser",
                       payload_summary={"synthetic": True, "ok": r["ok"], "error": r.get("error")})
            if not r["ok"]:
                result["status"] = "failed"; result["detail"] = {"step": "input_password", **r}; clear_trace(); return result
            result["steps_completed"] = 3

            # 3: click (with retry)
            r = await safe_retry_click(page, SEL_SUBMIT, retries=2)
            emit_event(step_key="click_login_button", step_order=3, event_type="submit",
                       result="success" if r["ok"] else "failure", connector_type="browser",
                       payload_summary={"synthetic": True, "ok": r["ok"], "error": r.get("error"), "selector": SEL_SUBMIT[:50]})
            if not r["ok"]:
                result["status"] = "failed"; result["detail"] = {"step": "click_login_button", **r}; clear_trace(); return result
            result["steps_completed"] = 4

            # 4: wait dashboard
            r = await wait_for_url(page, "/dashboard", timeout=TIMEOUT_SUBMIT_RESULT)
            emit_event(step_key="wait_dashboard", step_order=4, event_type="validate",
                       result="success" if r["ok"] else "failure", connector_type="browser",
                       payload_summary={"synthetic": True, "ok": r["ok"], "error": r.get("error")})
            if not r["ok"]:
                result["status"] = "failed"; result["detail"] = {"step": "wait_dashboard", **r}; clear_trace(); return result
            result["steps_completed"] = 5

            # 5: verify
            emit_event(step_key="verify_login_success", step_order=5, event_type="read",
                       result="success", connector_type="browser",
                       payload_summary={"synthetic": True, "login_verified": True})
            result["steps_completed"] = 6
            result["status"] = "passed"
            result["detail"] = {"steps": 6, "login_verified": True}

    except Exception as e:
        emit_event(step_key="error", step_order=99, event_type="error",
                   result="failure", connector_type="browser",
                   payload_summary={"synthetic": True, "error": str(e)[:100]})
        result["status"] = "error"; result["detail"] = {"error": str(e)[:200]}
    finally:
        clear_trace()

    return result
