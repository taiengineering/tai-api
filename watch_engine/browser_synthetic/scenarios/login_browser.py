"""Browser Synthetic — Login Flow.

실제 브라우저로 로그인 페이지 열고 → 입력 → 클릭 → 대시보드 확인.
API는 정상인데 UI가 망가진 상태 탐지.
"""

import logging
import os

from watch_engine import create_trace, emit_event
from watch_engine.trace import clear_trace
from watch_engine.browser_synthetic.base import (
    browser_context, safe_click, safe_fill, wait_for_url,
    PLAYWRIGHT_BASE_URL,
)

logger = logging.getLogger("watch_engine.browser_synthetic.login_browser")

SYNTHETIC_EMAIL = os.environ.get("SYNTHETIC_TEST_EMAIL", "")
SYNTHETIC_PASSWORD = os.environ.get("SYNTHETIC_TEST_PASSWORD", "")


async def run_login_browser(run_id: str) -> dict:
    result = {"scenario": "login_browser", "status": "error", "steps_completed": 0, "detail": {}}

    if not SYNTHETIC_EMAIL or not SYNTHETIC_PASSWORD:
        result["detail"] = {"reason": "SYNTHETIC_TEST_EMAIL/PASSWORD not configured"}
        return result

    trace = create_trace(
        flow_key="login_browser",
        tenant_id="tai",
        actor_type="synthetic_user",
        scenario_run_id=run_id,
    )

    try:
        async with browser_context() as ctx:
            page = await ctx.new_page()

            # Step 0: open_login_page
            await page.goto(f"{PLAYWRIGHT_BASE_URL}/login")
            emit_event(step_key="open_login_page", step_order=0, event_type="submit",
                       result="success", connector_type="browser",
                       payload_summary={"synthetic": True, "page": "/login"})
            result["steps_completed"] = 1

            # Step 1: input_email
            r = await safe_fill(page, "input[type='email'], input[name='email'], #email, input[type='text']", SYNTHETIC_EMAIL)
            if not r["ok"]:
                emit_event(step_key="input_email", step_order=1, event_type="submit",
                           result="failure", connector_type="browser",
                           payload_summary={"synthetic": True, "error": r["error"], "selector": r.get("selector")})
                result["status"] = "failed"
                result["detail"] = {"step": "input_email", **r}
                clear_trace()
                return result
            emit_event(step_key="input_email", step_order=1, event_type="submit",
                       result="success", connector_type="browser",
                       payload_summary={"synthetic": True, "has_value": True})
            result["steps_completed"] = 2

            # Step 2: input_password
            r = await safe_fill(page, "input[type='password'], #password", SYNTHETIC_PASSWORD)
            if not r["ok"]:
                emit_event(step_key="input_password", step_order=2, event_type="submit",
                           result="failure", connector_type="browser",
                           payload_summary={"synthetic": True, "error": r["error"]})
                result["status"] = "failed"
                result["detail"] = {"step": "input_password", **r}
                clear_trace()
                return result
            emit_event(step_key="input_password", step_order=2, event_type="submit",
                       result="success", connector_type="browser",
                       payload_summary={"synthetic": True, "has_value": True})
            result["steps_completed"] = 3

            # Step 3: click_login_button
            r = await safe_click(page, "button[type='submit'], #login-btn, .login-btn")
            if not r["ok"]:
                emit_event(step_key="click_login_button", step_order=3, event_type="submit",
                           result="failure", connector_type="browser",
                           payload_summary={"synthetic": True, "error": r["error"], "selector": r.get("selector")})
                result["status"] = "failed"
                result["detail"] = {"step": "click_login_button", **r}
                clear_trace()
                return result
            emit_event(step_key="click_login_button", step_order=3, event_type="submit",
                       result="success", connector_type="browser",
                       payload_summary={"synthetic": True, "selector": "button[type=submit]"})
            result["steps_completed"] = 4

            # Step 4: wait_dashboard
            r = await wait_for_url(page, "/dashboard", timeout=10000)
            if not r["ok"]:
                emit_event(step_key="wait_dashboard", step_order=4, event_type="validate",
                           result="failure", connector_type="browser",
                           payload_summary={"synthetic": True, "error": r["error"], "actual_url": r.get("actual", "")[:100]})
                result["status"] = "failed"
                result["detail"] = {"step": "wait_dashboard", **r}
                clear_trace()
                return result
            emit_event(step_key="wait_dashboard", step_order=4, event_type="validate",
                       result="success", connector_type="browser",
                       payload_summary={"synthetic": True, "url_contains": "/dashboard"})
            result["steps_completed"] = 5

            # Step 5: verify_login_success
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
        result["status"] = "error"
        result["detail"] = {"error": str(e)[:200]}
    finally:
        clear_trace()

    return result
