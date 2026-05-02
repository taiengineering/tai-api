#!/usr/bin/env python3
"""
네이버 지식iN 모니터링 v2 — 법령 DB + Gemini 초안 + Slack 알림.

- 자동 게시·지식iN 답변 등록 로직은 포함하지 않습니다.
- Gemini/슬랙 오류는 기록만 하고 다음 항목·종료까지 진행합니다.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests
from supabase import create_client

# --- 설정 ---
NAVER_KIN_API = "https://openapi.naver.com/v1/search/kin.json"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"
SLACK_POST_URL = "https://slack.com/api/chat.postMessage"
DIAGNOSIS_LINE = "3분 무료 진단: https://taieng.co.kr/free-diagnosis.html"

DEFAULT_KEYWORDS = (
    "안전관리자 선임,중대재해처벌법,산업안전보건법 과태료,안전보건관리체계"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def _strip_tags(text: str) -> str:
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", " ", text)
    t = html.unescape(t)
    return " ".join(t.split())


def _require_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        logging.error("Missing required environment variable: %s", name)
        sys.exit(1)
    return v


def _keywords() -> list[str]:
    raw = os.environ.get("NAVER_KIN_KEYWORDS", "").strip()
    if not raw:
        raw = DEFAULT_KEYWORDS
    parts = [k.strip() for k in raw.split(",")]
    return [k for k in parts if k]


def _gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"


def supabase_dashboard_link(supabase_url: str) -> str:
    m = re.search(r"https://([a-z0-9-]+)\.supabase\.co", supabase_url, re.I)
    if m:
        return f"https://supabase.com/dashboard/project/{m.group(1)}"
    return "https://supabase.com/dashboard"


def slack_env_ready() -> bool:
    t = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    c = os.environ.get("SLACK_CHANNEL_ID", "").strip()
    return bool(t and c)


def fetch_kin(keyword: str, client_id: str, client_secret: str) -> tuple[list[dict], dict]:
    params = {
        "query": keyword,
        "display": "30",
        "start": "1",
        "sort": "date",
    }
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Accept": "application/json",
    }
    r = requests.get(NAVER_KIN_API, params=params, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data.get("items") or [], data


def search_law_data(sb: Any, keyword: str) -> dict[str, list]:
    out: dict[str, list] = {"rules": [], "revisions": [], "precedents": []}

    try:
        q = (
            sb.table("master_building_legal_rules")
            .select(
                "law_name, obligation_summary, obligation_type, penalty_amount, condition_summary"
            )
            .ilike("obligation_summary", f"%{keyword}%")
            .eq("is_active", True)
            .limit(5)
        )
        out["rules"] = q.execute().data or []
    except Exception as e:
        logging.warning("master_building_legal_rules 조회 실패: %s", e)

    try:
        filt = f"title.ilike.%{keyword}%,summary.ilike.%{keyword}%"
        q = (
            sb.table("law_revision_board")
            .select(
                "law_name, title, summary, enforcement_date, impact_description"
            )
            .or_(filt)
            .eq("is_public", True)
            .order("enforcement_date", desc=True)
            .limit(3)
        )
        out["revisions"] = q.execute().data or []
    except Exception as e:
        logging.warning("law_revision_board 조회 실패: %s", e)

    try:
        q = (
            sb.table("industrial_accident_precedents")
            .select("case_name, summary, sentence_detail, fine_amount, violation_laws")
            .contains("keywords", [keyword])
            .eq("is_active", True)
            .limit(3)
        )
        out["precedents"] = q.execute().data or []
    except Exception as e:
        logging.warning("industrial_accident_precedents 조회 실패: %s", e)

    return out


def build_gemini_prompt(
    question_title: str,
    question_desc: str,
    law_data: dict[str, list],
) -> str:
    rules = law_data.get("rules") or []
    revisions = law_data.get("revisions") or []
    precedents = law_data.get("precedents") or []

    rules_text = "\n".join(
        [
            f"- [{r.get('law_name')}] {r.get('obligation_summary')} "
            f"(과태료: {r.get('penalty_amount', '미확인')})"
            for r in rules
        ]
    ) or "관련 의무 룰 없음"

    revisions_text = "\n".join(
        [
            f"- [{r.get('enforcement_date')}] {r.get('law_name')}: {r.get('summary')}"
            for r in revisions
        ]
    ) or "최근 개정 없음"

    precedents_text = "\n".join(
        [
            f"- {p.get('case_name')}: "
            f"{(p.get('summary') or '')[:100]}... "
            f"(벌금: {p.get('fine_amount', '미확인')}원)"
            for p in precedents
        ]
    ) or "관련 판례 없음"

    return f"""당신은 산업안전보건법 관련 정보를 정리하는 시스템 가이드 작성 보조입니다.
아래 지식iN 질문에 대해 TAI 엔지니어링 DB에서 조회된 데이터만 근거로 답변 초안을 작성하세요.

[절대 금지 — 프롬프트·답변 모두]
- '법률 상담', '법률 자문', '법적 조언', '변호사' 등 법률 서비스를 암시하는 표현
- DB에 없는 법령 조문·판례 번호를 임의로 만들어내기
- 과장·확신 표현(예: "반드시", "무조건") → "일반적으로", "해당 조건에서는" 등으로 완화

[답변 구조]
1. 핵심 요약 (2~3줄)
2. 적용 법령 및 의무 (위 DB 근거만)
3. 최근 개정 사항 (있을 경우)
4. 유사 판례 (있을 경우)

---
[질문 제목] {question_title}
[질문 내용] {question_desc}

[DB 조회 — 의무 룰]
{rules_text}

[DB 조회 — 최근 법령 개정]
{revisions_text}

[DB 조회 — 유사 판례]
{precedents_text}
---

답변 마지막 줄에는 반드시 아래 문구만 단독으로 넣으세요(추가 문장 없이):
{DIAGNOSIS_LINE}
"""


def generate_draft_gemini(prompt: str, api_key: str) -> str | None:
    model = _gemini_model()
    url = f"{GEMINI_API}/{model}:generateContent"
    try:
        r = requests.post(
            url,
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            headers={"Content-Type": "application/json"},
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        cands = data.get("candidates") or []
        if not cands:
            logging.warning("Gemini 응답에 candidates 없음: %s", data)
            return None
        parts = (cands[0].get("content") or {}).get("parts") or []
        if not parts:
            return None
        text = parts[0].get("text") or ""
        text = text.strip()
        if DIAGNOSIS_LINE not in text:
            text = text.rstrip() + "\n\n" + DIAGNOSIS_LINE
        return text
    except Exception as e:
        logging.exception("Gemini 초안 생성 실패: %s", e)
        return None


def row_exists(sb: Any, question_link: str) -> bool:
    try:
        r = (
            sb.table("naver_kin_log")
            .select("id")
            .eq("question_link", question_link)
            .limit(1)
            .execute()
        )
        return bool(r.data)
    except Exception as e:
        logging.warning("중복 조회 실패(계속 진행): %s", e)
        return False


def insert_log(
    sb: Any,
    row: dict[str, Any],
) -> tuple[bool, str | None]:
    """
    Returns (inserted, error_message_if_any).
    409/duplicate → inserted False, no error string for caller to count as skip.
    """
    try:
        sb.table("naver_kin_log").insert(row).execute()
        return True, None
    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg or "23505" in msg:
            return False, None
        logging.exception("naver_kin_log insert 실패: %s", e)
        return False, str(e)


def send_slack_notification(
    token: str,
    channel_id: str,
    new_items: list[dict[str, str]],
    dashboard_url: str,
) -> None:
    n = len(new_items)
    lines = [f"🔍 네이버 지식인 신규 *{n}건* 수집 완료", ""]
    for i, it in enumerate(new_items[:5], 1):
        title = it.get("title") or "(제목 없음)"
        link = it.get("link") or ""
        preview = (it.get("draft_preview") or "")[:200]
        lines.append(f"*{i}. {title}*")
        lines.append(link)
        lines.append(f"> {preview}")
        lines.append("")
    lines.append(f"Supabase: {dashboard_url}")
    text = "\n".join(lines)
    try:
        r = requests.post(
            SLACK_POST_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"channel": channel_id, "text": text},
            timeout=30,
        )
        body = r.json()
        if not body.get("ok"):
            logging.error("Slack API 오류: %s", body)
    except Exception as e:
        logging.exception("Slack 알림 전송 실패: %s", e)


def main() -> None:
    naver_id = _require_env("NAVER_CLIENT_ID")
    naver_secret = _require_env("NAVER_CLIENT_SECRET")
    supabase_url = _require_env("SUPABASE_URL")
    supabase_key = _require_env("SUPABASE_SERVICE_ROLE_KEY")
    gemini_key = _require_env("GEMINI_API_KEY")

    sb = create_client(supabase_url, supabase_key)
    run_at = datetime.now(timezone.utc).isoformat()
    sort_mode = "date"

    new_for_slack: list[dict[str, str]] = []
    stats = {
        "keywords": _keywords(),
        "api_items": 0,
        "skipped_duplicate": 0,
        "skipped_gemini": 0,
        "inserted": 0,
        "insert_errors": 0,
    }

    for kw in _keywords():
        try:
            items, _env = fetch_kin(kw, naver_id, naver_secret)
        except Exception as e:
            logging.exception("[네이버 API] keyword=%s: %s", kw, e)
            continue

        for idx, item in enumerate(items):
            stats["api_items"] += 1
            link = (item.get("link") or "").strip()
            if not link:
                continue

            if row_exists(sb, link):
                stats["skipped_duplicate"] += 1
                continue

            title = _strip_tags(item.get("title") or "")
            desc = _strip_tags(item.get("description") or "")

            try:
                law_data = search_law_data(sb, kw)
            except Exception as e:
                logging.warning("법령 데이터 조회 예외 — 빈 근거로 진행: %s", e)
                law_data = {"rules": [], "revisions": [], "precedents": []}

            prompt = build_gemini_prompt(title, desc, law_data)
            draft = None
            try:
                draft = generate_draft_gemini(prompt, gemini_key)
            except Exception as e:
                logging.exception("Gemini 호출 예외: %s", e)

            if not draft:
                stats["skipped_gemini"] += 1
                continue

            row = {
                "question_link": link,
                "question_title": title[:2000] if title else None,
                "question_description": (desc[:8000] if desc else None),
                "search_keyword": kw,
                "sort_mode": sort_mode,
                "item_index": idx,
                "raw_item": item,
                "draft_answer": draft,
                "matched_rules": law_data,
                "run_at": run_at,
                "status": "DRAFT",
            }

            inserted, err = insert_log(sb, row)
            if inserted:
                stats["inserted"] += 1
                new_for_slack.append(
                    {
                        "title": title,
                        "link": link,
                        "draft_preview": draft,
                    }
                )
            elif err:
                stats["insert_errors"] += 1
            else:
                stats["skipped_duplicate"] += 1

    dashboard = supabase_dashboard_link(supabase_url)

    if slack_env_ready() and new_for_slack:
        try:
            send_slack_notification(
                os.environ["SLACK_BOT_TOKEN"].strip(),
                os.environ["SLACK_CHANNEL_ID"].strip(),
                new_for_slack,
                dashboard,
            )
        except Exception as e:
            logging.exception("Slack 알림 블록 실패: %s", e)
    elif not slack_env_ready():
        logging.info("Slack 환경변수 미설정 — 알림 생략 후 정상 종료")

    print(json.dumps({"ok": True, "run_at": run_at, **stats}, ensure_ascii=False))


if __name__ == "__main__":
    main()
