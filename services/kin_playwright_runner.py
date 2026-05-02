"""
네이버 지식인 답변 폼 — Playwright로 초안 입력만 수행 (등록 버튼은 사람이 클릭).

환경 변수:
  NAVER_COOKIES — JSON 배열 (Playwright cookie 형식: name, value, domain, path 필수)
  KIN_PLAYWRIGHT_HEADLESS — true/false (기본 true)
  KIN_KEEP_BROWSER_OPEN — true면 browser.close() 호출 안 함 (로컬 검수용; 서버에서는 false 권장)
  KIN_OPEN_ANSWER_SELECTORS — 답변 작성 버튼 후보 CSS, 쉼표 구분
  KIN_EDITOR_SELECTORS — 에디터 textarea/contenteditable 후보 CSS, 쉼표 구분
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
logger = logging.getLogger(__name__)

DEFAULT_OPEN_SELECTORS = (
    "a.btn_answer_write,"
    "button.btn_answer_write,"
    ".btn_answer,"
    "a[href*='answer']"
)
DEFAULT_EDITOR_SELECTORS = (
    "textarea#contents,"
    "textarea.se_text_input,"
    "textarea.textarea_write,"
    ".answer_area textarea,"
    "div.se_component_wrap div[contenteditable='true'],"
    "[contenteditable='true']"
)


def _parse_cookie_json(raw: str) -> list[dict]:
    data = json.loads(raw)
    if isinstance(data, dict) and "cookies" in data:
        data = data["cookies"]
    if not isinstance(data, list):
        raise ValueError("NAVER_COOKIES must be a JSON array of cookie objects")
    out = []
    for c in data:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        value = c.get("value")
        domain = c.get("domain")
        path = c.get("path", "/")
        if not name or value is None or not domain:
            logger.warning("Skipping invalid cookie entry: %s", c)
            continue
        entry = {"name": name, "value": str(value), "domain": domain, "path": path}
        for opt in ("expires", "httpOnly", "secure", "sameSite"):
            if opt in c:
                entry[opt] = c[opt]
        out.append(entry)
    return out


def _split_selectors(env_name: str, default: str) -> list[str]:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        raw = default
    return [s.strip() for s in raw.split(",") if s.strip()]


async def _type_human_like(locator, text: str) -> None:
    """키보드로 한 글자씩 입력, 글자 간 지연 random 50~150ms."""
    await locator.click()
    pg = locator.page
    await asyncio.sleep(0.15)
    for ch in text:
        if ch == "\r":
            continue
        if ch == "\n":
            await pg.keyboard.press("Enter")
        else:
            await pg.keyboard.type(ch, delay=0)
        await asyncio.sleep(random.randint(50, 150) / 1000.0)


async def fill_kin_answer_editor(
    question_link: str,
    draft_text: str,
) -> None:
    """질문 페이지를 열고 답변 에디터에 초안을 입력한다. 등록/전송은 하지 않는다."""
    from playwright.async_api import async_playwright

    cookies_raw = os.environ.get("NAVER_COOKIES", "").strip()
    if not cookies_raw:
        raise RuntimeError("NAVER_COOKIES 환경 변수가 설정되어 있지 않습니다.")

    cookies = _parse_cookie_json(cookies_raw)
    headless = os.environ.get("KIN_PLAYWRIGHT_HEADLESS", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    keep_open = os.environ.get("KIN_KEEP_BROWSER_OPEN", "false").lower() in (
        "1",
        "true",
        "yes",
    )

    open_selectors = _split_selectors(
        "KIN_OPEN_ANSWER_SELECTORS", DEFAULT_OPEN_SELECTORS
    )
    editor_selectors = _split_selectors(
        "KIN_EDITOR_SELECTORS", DEFAULT_EDITOR_SELECTORS
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(locale="ko-KR")
        await context.add_cookies(cookies)
        page = await context.new_page()
        try:
            await page.goto(question_link, wait_until="domcontentloaded", timeout=90_000)
            await asyncio.sleep(1.0)

            # 답변 창 열기 (이미 열려 있으면 예외 무시)
            for sel in open_selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.click(timeout=5000)
                        await asyncio.sleep(1.2)
                        break
                except Exception as e:
                    logger.debug("open selector %s: %s", sel, e)

            editor_locator = None
            for sel in editor_selectors:
                loc = page.locator(sel).first
                try:
                    await loc.wait_for(state="visible", timeout=15_000)
                    editor_locator = loc
                    break
                except Exception:
                    continue

            # iframe 내부 시도
            if editor_locator is None:
                for frame in page.frames:
                    if frame == page.main_frame:
                        continue
                    for sel in editor_selectors:
                        loc = frame.locator(sel).first
                        try:
                            await loc.wait_for(state="visible", timeout=5000)
                            editor_locator = loc
                            break
                        except Exception:
                            continue
                    if editor_locator:
                        break

            if editor_locator is None:
                raise RuntimeError(
                    "답변 에디터를 찾지 못했습니다. KIN_EDITOR_SELECTORS 를 조정하세요."
                )

            await _type_human_like(editor_locator, draft_text)
            logger.info(
                "Kin draft typed (%s chars), awaiting human submit.", len(draft_text)
            )
        finally:
            if not keep_open:
                await context.close()
                await browser.close()
            else:
                logger.warning(
                    "KIN_KEEP_BROWSER_OPEN=true — browser.close()를 호출하지 않았습니다. "
                    "전용 워커에서만 사용하세요."
                )
