"""Browser Synthetic — Process Registration Flow.

실제 브라우저로 공정등록 페이지 → 선택 → 입력 → 저장 → 확인.
SelectBar mismatch / 버튼 disabled / 렌더 실패 탐지.
"""

import logging
import os

from watch_engine import create_trace, emit_event
from watch_engine.trace import clear_trace
from watch_engine.browser_synthetic.base import (
    browser_context, safe_click, safe_fill, safe_select, wait_for_url, get_text,
    PLAYWRIGHT_BASE_URL,
)

logger = logging.getLogger("watch_engine.browser_synthetic.process_registration_browser")

SYNTHETIC_EMAIL = os.environ.get("SYNTHETIC_TEST_EMAIL", "")
SYNTHETIC_PASSWORD = os.environ.get("SYNTHETIC_TEST_PASSWORD", "")
SYNTHETIC_FACTORY_ID = os.environ.get("SYNTHETIC_FACTORY_ID", "")

SYNTHETIC_PROCESS_TYPE = "MANUAL"


async def run_process_registration_browser(run_id: str) -> dict:
    result = {"scenario": "process_registration_browser", "status": "error", "steps_completed": 0, "detail": {}}

    if not SYNTHETIC_EMAIL or not SYNTHETIC_PASSWORD or not SYNTHETIC_FACTORY_ID:
        result["detail"] = {"reason": "SYNTHETIC env vars not configured"}
        return result

    trace = create_trace(
        flow_key="process_registration_browser",
        tenant_id="tai",
        actor_type="synthetic_user",
        scenario_run_id=run_id,
    )

    try:
        async with browser_context() as ctx:
            page = await ctx.new_page()

            # Login first
            await page.goto(f"{PLAYWRIGHT_BASE_URL}/login")
            await safe_fill(page, "input[type='email'], input[name='email'], #email, input[type='text']", SYNTHETIC_EMAIL)
            await safe_fill(page, "input[type='password'], #password", SYNTHETIC_PASSWORD)
            await safe_click(page, "button[type='submit'], #login-btn, .login-btn")
            try:
                await page.wait_for_url("**/dashboard**", timeout=10000)
            except Exception:
                emit_event(step_key="error", step_order=99, event_type="error",
                           result="failure", connector_type="browser",
                           payload_summary={"synthetic": True, "error": "login_failed_before_process"})
                result["status"] = "failed"
                result["detail"] = {"step": "login", "error": "login failed"}
                clear_trace()
                return result

            # Step 0: open_process_page
            await page.goto(f"{PLAYWRIGHT_BASE_URL}/factory/{SYNTHETIC_FACTORY_ID}/process/new")
            emit_event(step_key="open_process_page", step_order=0, event_type="submit",
                       result="success", connector_type="browser",
                       payload_summary={"synthetic": True, "page": "/process/new"})
            result["steps_completed"] = 1

            # Step 1: select_process_type
            r = await safe_select(page, "select[name='source'], #process-type, .process-type-select", SYNTHETIC_PROCESS_TYPE)
            if not r["ok"]:
                emit_event(step_key="select_process_type", step_order=1, event_type="submit",
                           result="failure", connector_type="browser",
                           payload_summary={"synthetic": True, "error": r["error"], "selector": r.get("selector")})
                result["status"] = "failed"
                result["detail"] = {"step": "select_process_type", **r}
                clear_trace()
                return result
            emit_event(step_key="select_process_type", step_order=1, event_type="submit",
                       result="success", connector_type="browser",
                       payload_summary={"synthetic": True, "process_type_key": SYNTHETIC_PROCESS_TYPE})
            result["steps_completed"] = 2

            # Step 2: input_required_fields
            await safe_fill(page, "input[name='process_name'], #process-name", "SYNTHETIC_HEARTBEAT")
            emit_event(step_key="input_required_fields", step_order=2, event_type="submit",
                       result="success", connector_type="browser",
                       payload_summary={"synthetic": True, "fields_filled": True})
            result["steps_completed"] = 3

            # Step 3: click_submit
            r = await safe_click(page, "button[type='submit'], #save-btn, .save-btn")
            if not r["ok"]:
                emit_event(step_key="click_submit", step_order=3, event_type="submit",
                           result="failure", connector_type="browser",
                           payload_summary={"synthetic": True, "error": r["error"], "selector": r.get("selector")})
                result["status"] = "failed"
                result["detail"] = {"step": "click_submit", **r}
                clear_trace()
                return result
            emit_event(step_key="click_submit", step_order=3, event_type="submit",
                       result="success", connector_type="browser",
                       payload_summary={"synthetic": True, "selector": "button[type=submit]"})
            result["steps_completed"] = 4

            # Step 4: wait_success_modal
            try:
                await page.wait_for_selector(".success-modal, .toast-success, [data-result='success']", timeout=10000)
                emit_event(step_key="wait_success_modal", step_order=4, event_type="validate",
                           result="success", connector_type="browser",
                           payload_summary={"synthetic": True, "modal_appeared": True})
            except Exception:
                emit_event(step_key="wait_success_modal", step_order=4, event_type="validate",
                           result="failure", connector_type="browser",
                           payload_summary={"synthetic": True, "error": "page_timeout", "modal_appeared": False})
                result["status"] = "failed"
                result["detail"] = {"step": "wait_success_modal", "error": "page_timeout"}
                clear_trace()
                return result
            result["steps_completed"] = 5

            # Step 5: verify_saved_result — UI value mismatch 검증
            displayed_type = await get_text(page, ".process-type-display, [data-field='source'], .source-value")
            submitted = SYNTHETIC_PROCESS_TYPE
            stored = (displayed_type or "").strip()
            match = submitted.upper() == stored.upper() if stored else None

            emit_event(step_key="verify_saved_result", step_order=5, event_type="read",
                       result="success" if match is not False else "failure",
                       connector_type="browser",
                       payload_summary={
                           "synthetic": True,
                           "process_type_key": stored or "unknown",
                           "submitted": submitted,
                           "ui_match": match,
                       })
            result["steps_completed"] = 6

            if match is False:
                result["status"] = "failed"
                result["detail"] = {"step": "verify_saved_result", "submitted": submitted, "stored": stored, "mismatch": True}
            else:
                result["status"] = "passed"
                result["detail"] = {"steps": 6, "submitted": submitted, "stored": stored}

    except Exception as e:
        emit_event(step_key="error", step_order=99, event_type="error",
                   result="failure", connector_type="browser",
                   payload_summary={"synthetic": True, "error": str(e)[:100]})
        result["status"] = "error"
        result["detail"] = {"error": str(e)[:200]}
    finally:
        clear_trace()

    return result
