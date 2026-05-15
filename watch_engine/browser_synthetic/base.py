"""Browser Synthetic Base — Playwright 공통 기반.

Chromium headless 기반.
실패 시 서비스 영향 없음.
"""

import logging
import os
from typing import Optional
from contextlib import asynccontextmanager

logger = logging.getLogger("watch_engine.browser_synthetic.base")

PLAYWRIGHT_HEADLESS = os.environ.get("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
PLAYWRIGHT_BASE_URL = os.environ.get("PLAYWRIGHT_BASE_URL", "https://taieng.co.kr")
PLAYWRIGHT_TIMEOUT = int(os.environ.get("PLAYWRIGHT_TIMEOUT_MS", "15000"))


@asynccontextmanager
async def browser_context():
    """Playwright browser context manager. Fail-safe."""
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
        context.set_default_timeout(PLAYWRIGHT_TIMEOUT)
        yield context
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        if pw:
            try:
                await pw.stop()
            except Exception:
                pass


async def safe_click(page, selector: str, timeout: int = 5000) -> dict:
    """Safe click with result dict."""
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


async def safe_fill(page, selector: str, value: str, timeout: int = 5000) -> dict:
    """Safe fill with result dict."""
    try:
        el = await page.wait_for_selector(selector, timeout=timeout, state="visible")
        if not el:
            return {"ok": False, "error": "selector_not_found", "selector": selector}
        await el.fill(value)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(type(e).__name__), "selector": selector, "detail": str(e)[:100]}


async def safe_select(page, selector: str, value: str, timeout: int = 5000) -> dict:
    """Safe select option."""
    try:
        el = await page.wait_for_selector(selector, timeout=timeout, state="visible")
        if not el:
            return {"ok": False, "error": "selector_not_found", "selector": selector}
        await page.select_option(selector, value)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(type(e).__name__), "selector": selector, "detail": str(e)[:100]}


async def wait_for_url(page, url_pattern: str, timeout: int = 10000) -> dict:
    """Wait for URL to contain pattern."""
    try:
        await page.wait_for_url(f"**{url_pattern}**", timeout=timeout)
        return {"ok": True, "url": page.url}
    except Exception as e:
        return {"ok": False, "error": "page_timeout", "expected": url_pattern, "actual": page.url, "detail": str(e)[:100]}


async def get_text(page, selector: str, timeout: int = 5000) -> Optional[str]:
    """Get text content from selector."""
    try:
        el = await page.wait_for_selector(selector, timeout=timeout)
        if el:
            return await el.text_content()
    except Exception:
        pass
    return None
