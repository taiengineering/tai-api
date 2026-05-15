"""Browser Synthetic — Process Registration Flow v1.1.

data-testid selector 기반.
SelectBar mismatch UI 탐지.
"""

import logging
import os

from watch_engine import create_trace, emit_event
from watch_engine.trace import clear_trace
from watch_engine.browser_synthetic.base import (
    browser_context, safe_click, safe_fill, safe_select,
    safe_retry_click, wait_for_url, get_text, tid,
    PLAYWRIGHT_BASE_URL, TIMEOUT_PAGE_LOAD, TIMEOUT_SUBMIT_RESULT,
)

logger = logging.getLogger("watch_engine.browser_synthetic.process_registration_browser")

SYNTHETIC_EMAIL = os.environ.get("SYNTHETIC_TEST_EMAIL", "")
SYNTHETIC_PASSWORD = os.environ.get("SYNTHETIC_TEST_PASSWORD", "")
SYNTHETIC_FACTORY_ID = os.environ.get("SYNTHETIC_FACTORY_ID", "")

SYNTHETIC_PROCESS_TYPE = "MANUAL"

# Selectors: data-testid 우선
SEL_TYPE = f"{tid('process-type-select')}, select[name='source'], #process-type"
SEL_NAME = f"{tid('process-name-input')}, input[name='process_name'], #process-name"
SEL_SUBMIT = f"{tid('process-submit-btn')}, button[type='submit'], #save-btn"
SEL_SUCCESS = f"{tid('process-success-modal')}, .success-modal, .toast-success, [data-result='success']"
SEL_RESULT_TYPE = f"{tid('process-type-display')}, .process-type-display, [data-field='source']"


async def run_process_registration_browser(run_id: str) -> dict:
    result = {"scenario": "process_registration_browser", "status": "error", "steps_completed": 0, "detail": {}}

    if not SYNTHETIC_EMAIL or not SYNTHETIC_PASSWORD or not SYNTHETIC_FACTORY_ID:
        result["detail"] = {"reason": "SYNTHETIC env vars not configured"}
        return result

    trace = create_trace(flow_key="process_registration_browser", tenant_id="tai",
                         actor_type="synthetic_user", scenario_run_id=run_id)

    try:
        async with browser_context() as ctx:
            page = await ctx.new_page()

            # Login first
            await page.goto(f"{PLAYWRIGHT_BASE_URL}/login", wait_until="domcontentloaded", timeout=TIMEOUT_PAGE_LOAD)
            await safe_fill(page, f"{tid('login-email-input')}, input[type='email']", SYNTHETIC_EMAIL)
            await safe_fill(page, f"{tid('login-password-input')}, input[type='password']", SYNTHETIC_PASSWORD)
            await safe_click(page, f"{tid('login-submit-btn')}, button[type='submit']")
            try:
                await page.wait_for_url("**/dashboard**", timeout=TIMEOUT_SUBMIT_RESULT)
            except Exception:
                result["status"] = "failed"; result["detail"] = {"step": "login", "error": "login failed"}
                emit_event(step_key="error", step_order=99, event_type="error", result="failure",
                           connector_type="browser", payload_summary={"synthetic": True, "error": "login_failed"})
                clear_trace(); return result

            # 0: open
            await page.goto(f"{PLAYWRIGHT_BASE_URL}/factory/{SYNTHETIC_FACTORY_ID}/process/new",
                           wait_until="domcontentloaded", timeout=TIMEOUT_PAGE_LOAD)
            emit_event(step_key="open_process_page", step_order=0, event_type="submit",
                       result="success", connector_type="browser",
                       payload_summary={"synthetic": True, "page": "/process/new"})
            result["steps_completed"] = 1

            # 1: select type
            r = await safe_select(page, SEL_TYPE, SYNTHETIC_PROCESS_TYPE)
            emit_event(step_key="select_process_type", step_order=1, event_type="submit",
                       result="success" if r["ok"] else "failure", connector_type="browser",
                       payload_summary={"synthetic": True, "process_type_key": SYNTHETIC_PROCESS_TYPE, "ok": r["ok"], "error": r.get("error")})
            if not r["ok"]:
                result["status"] = "failed"; result["detail"] = {"step": "select_process_type", **r}; clear_trace(); return result
            result["steps_completed"] = 2

            # 2: fill fields
            await safe_fill(page, SEL_NAME, "SYNTHETIC_HEARTBEAT")
            emit_event(step_key="input_required_fields", step_order=2, event_type="submit",
                       result="success", connector_type="browser",
                       payload_summary={"synthetic": True, "fields_filled": True})
            result["steps_completed"] = 3

            # 3: submit (retry)
            r = await safe_retry_click(page, SEL_SUBMIT, retries=2)
            emit_event(step_key="click_submit", step_order=3, event_type="submit",
                       result="success" if r["ok"] else "failure", connector_type="browser",
                       payload_summary={"synthetic": True, "ok": r["ok"], "error": r.get("error"), "selector": SEL_SUBMIT[:50]})
            if not r["ok"]:
                result["status"] = "failed"; result["detail"] = {"step": "click_submit", **r}; clear_trace(); return result
            result["steps_completed"] = 4

            # 4: wait success
            try:
                await page.wait_for_selector(SEL_SUCCESS, timeout=TIMEOUT_SUBMIT_RESULT)
                emit_event(step_key="wait_success_modal", step_order=4, event_type="validate",
                           result="success", connector_type="browser",
                           payload_summary={"synthetic": True, "modal_appeared": True})
            except Exception:
                emit_event(step_key="wait_success_modal", step_order=4, event_type="validate",
                           result="failure", connector_type="browser",
                           payload_summary={"synthetic": True, "error": "page_timeout"})
                result["status"] = "failed"; result["detail"] = {"step": "wait_success_modal", "error": "page_timeout"}
                clear_trace(); return result
            result["steps_completed"] = 5

            # 5: verify mismatch
            displayed = await get_text(page, SEL_RESULT_TYPE)
            submitted = SYNTHETIC_PROCESS_TYPE
            stored = (displayed or "").strip()
            match = submitted.upper() == stored.upper() if stored else None

            emit_event(step_key="verify_saved_result", step_order=5, event_type="read",
                       result="success" if match is not False else "failure",
                       connector_type="browser",
                       payload_summary={"synthetic": True, "process_type_key": stored or "unknown",
                                        "submitted": submitted, "ui_match": match})
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
        result["status"] = "error"; result["detail"] = {"error": str(e)[:200]}
    finally:
        clear_trace()

    return result
