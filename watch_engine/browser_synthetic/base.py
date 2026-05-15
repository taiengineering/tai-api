"""Browser Synthetic Base v1.1 — Playwright 공통 + 안정성 강화.

data-testid selector 기반.
retry/wait/timeout 표준화.
Fail-safe: Playwright 미설치 시 skip.
"""

import logging
import os
from typing import Optional
from contextlib import asynccontextmanager

logger = logging.getLogger("watch_engine.browser_synthetic.base")

PLAYWRIGHT_HEADLESS = os.environ.get("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
PLAYWRIGHT_BASE_URL = os.environ.get("PLAYWRIGHT_BASE_URL", "https://taieng.co.kr")

# Timeout 표준 (ms)
TIMEOUT_PAGE_LOAD = 15000
TIMEOUT_SELECTOR = 10000
TIMEOUT_SUBMIT_RESULT = 20000
DEFAULT_RETRY = 2


def tid(name: str) -> str:
    """data-testid selector 생성.

    사용법: tid('login-submit-btn') -> '[data-testid="login-submit-btn"]'
    """
    return f'[data-testid="{name}"]'


@asynccontextmanager
async def browser_context():
    """Playwright browser context manager."""
    pw = None
    browser = None
    context = None
    try:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="ko-KR",
        )
        context.set_default_timeout(TIMEOUT_SELECTOR)
        yield context
    finally:
        if context:
            try: await context.close()
            except Exception: pass
        if browser:
            try: await browser.close()
            except Exception: pass
        if pw:
            try: await pw.stop()
            except Exception: pass


async def safe_wait_visible(page, selector: str, timeout: int = TIMEOUT_SELECTOR) -> dict:
    """Wait for element to be visible."""
    try:
        el = await page.wait_for_selector(selector, timeout=timeout, state="visible")
        if el:
            return {"ok": True}
        return {"ok": False, "error": "selector_not_found", "selector": selector}
    except Exception as e:
        return {"ok": False, "error": "selector_not_found", "selector": selector, "detail": str(e)[:100]}


async def safe_wait_enabled(page, selector: str, timeout: int = TIMEOUT_SELECTOR) -> dict:
    """Wait for element to be visible AND enabled."""
    try:
        el = await page.wait_for_selector(selector, timeout=timeout, state="visible")
        if not el:
            return {"ok": False, "error": "selector_not_found", "selector": selector}
        if not await el.is_enabled():
            return {"ok": False, "error": "button_not_clickable", "selector": selector}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": "selector_not_found", "selector": selector, "detail": str(e)[:100]}


async def safe_click(page, selector: str, timeout: int = TIMEOUT_SELECTOR) -> dict:
    """Click with visibility + enabled check."""
    try:
        el = await page.wait_for_selector(selector, timeout=timeout, state="visible")
        if not el:
            return {"ok": False, "error": "selector_not_found", "selector": selector}
        if not await el.is_enabled():
            return {"ok": False, "error": "button_not_clickable", "selector": selector}
        await el.click()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(type(e).__name__), "selector": selector, "detail": str(e)[:100]}


async def safe_retry_click(page, selector: str, retries: int = DEFAULT_RETRY, timeout: int = TIMEOUT_SELECTOR) -> dict:
    """Click with retry."""
    last_result = {"ok": False, "error": "unknown"}
    for attempt in range(retries + 1):
        last_result = await safe_click(page, selector, timeout=timeout)
        if last_result["ok"]:
            return last_result
        if attempt < retries:
            import asyncio
            await asyncio.sleep(1)
    last_result["retries"] = retries
    return last_result


async def safe_fill(page, selector: str, value: str, timeout: int = TIMEOUT_SELECTOR) -> dict:
    """Fill input."""
    try:
        el = await page.wait_for_selector(selector, timeout=timeout, state="visible")
        if not el:
            return {"ok": False, "error": "selector_not_found", "selector": selector}
        await el.fill(value)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(type(e).__name__), "selector": selector, "detail": str(e)[:100]}


async def safe_select(page, selector: str, value: str, timeout: int = TIMEOUT_SELECTOR) -> dict:
    """Select option."""
    try:
        el = await page.wait_for_selector(selector, timeout=timeout, state="visible")
        if not el:
            return {"ok": False, "error": "selector_not_found", "selector": selector}
        await page.select_option(selector, value)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(type(e).__name__), "selector": selector, "detail": str(e)[:100]}


async def wait_for_url(page, url_pattern: str, timeout: int = TIMEOUT_PAGE_LOAD) -> dict:
    """Wait for URL change."""
    try:
        await page.wait_for_url(f"**{url_pattern}**", timeout=timeout)
        return {"ok": True, "url": page.url}
    except Exception as e:
        return {"ok": False, "error": "page_timeout", "expected": url_pattern, "actual": page.url, "detail": str(e)[:100]}


async def get_text(page, selector: str, timeout: int = TIMEOUT_SELECTOR) -> Optional[str]:
    """Get text content."""
    try:
        el = await page.wait_for_selector(selector, timeout=timeout)
        if el:
            return await el.text_content()
    except Exception:
        pass
    return None
