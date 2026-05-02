#!/usr/bin/env python3
"""
네이버 지식iN 모니터링 v3.2
- pubDate 기준 24시간 이내 항목만 처리
- penalty_summary 컬럼 사용
- Gemini 429 재시도 (최대 3회)
- kin_keyword_sets / kin_prompt_settings DB 동적 로드
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests
from supabase import create_client

# --- 기본값 ---
NAVER_KIN_API    = "https://openapi.naver.com/v1/search/kin.json"
GEMINI_API       = "https://generativelanguage.googleapis.com/v1beta/models"
SLACK_POST_URL   = "https://slack.com/api/chat.postMessage"
DIAGNOSIS_LINE   = "3분 무료 진단: https://taieng.co.kr/free-diagnosis.html"
DEFAULT_KEYWORDS = "안전관리자 선임,중대재해처벌법,산업안전보건법 과태료,안전보건관리체계"

# 필터링 기준
HOURS_LIMIT = 24  # 등록 후 N시간 이내만 수집

# Gemini rate limit 대응
GEMINI_DELAY_SEC  = 3.0
GEMINI_RETRY_MAX  = 3
GEMINI_RETRY_WAIT = 15.0

DEFAULT_FORBIDDEN = """법률 상담, 법률 자문, 법적 조언, 변호사 등 법률 서비스를 암시하는 표현 금지
DB에 없는 법령 조문·판례 번호를 임의로 만들어내기 금지
과장·확신 표현(반드시, 무조건) → 일반적으로, 해당 조건에서는 등으로 완화"""

DEFAULT_STRUCTURE = """1. 핵심 요약 (2~3줄)
2. 적용 법령 및 의무 (DB 근거만)
3. 최근 개정 사항 (있을 경우)
4. 유사 판례 (있을 경우)
5. 진단 권유 링크"""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


# ════════════════ 유틸 ════════════════

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


def _gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"


def supabase_dashboard_link(supabase_url: str) -> str:
    m = re.search(r"https://([a-z0-9-]+)\.supabase\.co", supabase_url, re.I)
    return f"https://supabase.com/dashboard/project/{m.group(1)}" if m else "https://supabase.com/dashboard"


def slack_env_ready() -> bool:
    return bool(os.environ.get("SLACK_BOT_TOKEN", "").strip() and
                os.environ.get("SLACK_CHANNEL_ID", "").strip())


def is_within_hours(pub_date_str: str, hours: int = HOURS_LIMIT) -> bool:
    """네이버 pubDate(RFC 822)가 현재로부터 N시간 이내인지 확인."""
    if not pub_date_str:
        return True  # pubDate 없으면 통과
    try:
        pub_dt = parsedate_to_datetime(pub_date_str)
        # timezone-aware 변환
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return pub_dt >= cutoff
    except Exception as e:
        logging.warning("pubDate 파싱 실패(%s) — 통과 처리: %s", pub_date_str, e)
        return True


# ════════════════ DB 설정 로드 ════════════════

def load_active_keywords(sb: Any) -> list[str]:
    try:
        r = sb.table("kin_keyword_sets").select("keywords").eq("is_active", True).limit(1).execute()
        if r.data and r.data[0].get("keywords"):
            kws = r.data[0]["keywords"]
            logging.info("DB 키워드 세트 로드: %s", kws)
            return kws
    except Exception as e:
        logging.warning("kin_keyword_sets 조회 실패 — 환경변수 fallback: %s", e)
    raw = os.environ.get("NAVER_KIN_KEYWORDS", "").strip() or DEFAULT_KEYWORDS
    return [k.strip() for k in raw.split(",") if k.strip()]


def load_active_prompt(sb: Any) -> dict:
    try:
        r = sb.table("kin_prompt_settings").select("*").eq("is_active", True).limit(1).execute()
        if r.data:
            logging.info("DB 프롬프트 로드: %s", r.data[0].get("name"))
            return r.data[0]
    except Exception as e:
        logging.warning("kin_prompt_settings 조회 실패 — 기본값 사용: %s", e)
    return {}


# ════════════════ 네이버 지식iN ════════════════

def fetch_kin(keyword: str, client_id: str, client_secret: str) -> list[dict]:
    r = requests.get(
        NAVER_KIN_API,
        params={"query": keyword, "display": "30", "start": "1", "sort": "date"},
        headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("items") or []


# ════════════════ Supabase 법령 조회 ════════════════

def search_law_data(sb: Any, keyword: str) -> dict[str, list]:
    out: dict[str, list] = {"rules": [], "revisions": [], "precedents": []}

    try:
        out["rules"] = (
            sb.table("master_building_legal_rules")
            .select("law_name, obligation_summary, obligation_type, penalty_summary")
            .ilike("obligation_summary", f"%{keyword}%")
            .eq("is_active", True)
            .limit(5)
            .execute()
        ).data or []
    except Exception as e:
        logging.warning("master_building_legal_rules 조회 실패: %s", e)

    try:
        out["revisions"] = (
            sb.table("law_revision_board")
            .select("law_name, title, summary, enforcement_date")
            .or_(f"title.ilike.%{keyword}%,summary.ilike.%{keyword}%")
            .eq("is_public", True)
            .order("enforcement_date", desc=True)
            .limit(3)
            .execute()
        ).data or []
    except Exception as e:
        logging.warning("law_revision_board 조회 실패: %s", e)

    try:
        out["precedents"] = (
            sb.table("industrial_accident_precedents")
            .select("case_name, summary, sentence_detail, fine_amount")
            .contains("keywords", [keyword])
            .eq("is_active", True)
            .limit(3)
            .execute()
        ).data or []
    except Exception as e:
        logging.warning("industrial_accident_precedents 조회 실패: %s", e)

    return out


# ════════════════ Gemini 초안 생성 ════════════════

def build_prompt(title: str, desc: str, law_data: dict, prompt_cfg: dict) -> str:
    forbidden = (prompt_cfg.get("forbidden")          or DEFAULT_FORBIDDEN).strip()
    structure = (prompt_cfg.get("answer_structure")   or DEFAULT_STRUCTURE).strip()
    closing   = (prompt_cfg.get("closing_message")    or DIAGNOSIS_LINE).strip()
    extra     = (prompt_cfg.get("extra_instructions") or "").strip()

    rules = "\n".join(
        f"- [{r.get('law_name')}] {r.get('obligation_summary')} (처벌: {r.get('penalty_summary','미확인')})"
        for r in (law_data.get("rules") or [])
    ) or "관련 의무 룰 없음"

    revisions = "\n".join(
        f"- [{r.get('enforcement_date')}] {r.get('law_name')}: {r.get('summary')}"
        for r in (law_data.get("revisions") or [])
    ) or "최근 개정 없음"

    precedents = "\n".join(
        f"- {p.get('case_name')}: {(p.get('summary') or '')[:100]}... (벌금: {p.get('fine_amount','미확인')}원)"
        for p in (law_data.get("precedents") or [])
    ) or "관련 판례 없음"

    extra_block = f"\n[추가 지시사항]\n{extra}\n" if extra else ""

    return f"""당신은 산업안전보건 정보 제공 시스템입니다.
아래 지식iN 질문에 대해 TAI 엔지니어링 DB 데이터만 근거로 답변 초안을 작성하세요.

[절대 금지]
{forbidden}

[답변 구조]
{structure}
{extra_block}
---
[질문 제목] {title}
[질문 내용] {desc}

[DB — 의무 룰]
{rules}

[DB — 최근 법령 개정]
{revisions}

[DB — 유사 판례]
{precedents}
---

답변 마지막 줄에 반드시 아래 문구만 단독으로 넣으세요:
{closing}
"""


def generate_draft(prompt: str, api_key: str) -> str | None:
    model = _gemini_model()
    url   = f"{GEMINI_API}/{model}:generateContent"

    for attempt in range(1, GEMINI_RETRY_MAX + 1):
        try:
            time.sleep(GEMINI_DELAY_SEC)
            r = requests.post(
                url,
                params={"key": api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                headers={"Content-Type": "application/json"},
                timeout=120,
            )
            if r.status_code == 429:
                wait = GEMINI_RETRY_WAIT * attempt
                logging.warning("Gemini 429 — %d초 대기 후 재시도 (%d/%d)", wait, attempt, GEMINI_RETRY_MAX)
                time.sleep(wait)
                continue
            r.raise_for_status()
            data  = r.json()
            parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
            text  = (parts[0].get("text") or "").strip() if parts else ""
            if not text:
                return None
            if DIAGNOSIS_LINE not in text:
                text = text.rstrip() + "\n\n" + DIAGNOSIS_LINE
            return text
        except requests.exceptions.HTTPError as e:
            if attempt == GEMINI_RETRY_MAX:
                logging.error("Gemini 최종 실패 (%d회 시도): %s", attempt, e)
                return None
        except Exception as e:
            logging.exception("Gemini 예외: %s", e)
            return None
    return None


# ════════════════ Supabase INSERT ════════════════

def row_exists(sb: Any, question_link: str) -> bool:
    try:
        r = sb.table("naver_kin_log").select("id").eq("question_link", question_link).limit(1).execute()
        return bool(r.data)
    except Exception as e:
        logging.warning("중복 조회 실패(계속 진행): %s", e)
        return False


def insert_log(sb: Any, row: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        sb.table("naver_kin_log").insert(row).execute()
        return True, None
    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg or "23505" in msg:
            return False, None
        logging.exception("naver_kin_log insert 실패: %s", e)
        return False, str(e)


# ════════════════ Slack ════════════════

def send_slack(token: str, channel: str, items: list[dict], dashboard: str) -> None:
    lines = [f"🔍 네이버 지식인 신규 *{len(items)}건* 수집 완료 (최근 {HOURS_LIMIT}시간)", ""]
    for i, it in enumerate(items[:5], 1):
        lines += [
            f"*{i}. {it.get('title','(제목없음)')}*",
            it.get("link", ""),
            f"> {(it.get('draft_preview') or '')[:200]}",
            "",
        ]
    lines.append(f"📊 Supabase: {dashboard}")
    try:
        r = requests.post(
            SLACK_POST_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
            json={"channel": channel, "text": "\n".join(lines)},
            timeout=30,
        )
        body = r.json()
        if not body.get("ok"):
            logging.error("Slack API 오류: %s", body)
        else:
            logging.info("Slack 전송 완료")
    except Exception as e:
        logging.exception("Slack 전송 실패: %s", e)


# ════════════════ 메인 ════════════════

def main() -> None:
    naver_id     = _require_env("NAVER_CLIENT_ID")
    naver_secret = _require_env("NAVER_CLIENT_SECRET")
    sb_url       = _require_env("SUPABASE_URL")
    sb_key       = _require_env("SUPABASE_SERVICE_KEY")
    gemini_key   = _require_env("GEMINI_API_KEY")

    sb     = create_client(sb_url, sb_key)
    run_at = datetime.now(timezone.utc).isoformat()

    keywords   = load_active_keywords(sb)
    prompt_cfg = load_active_prompt(sb)

    logging.info("실행 키워드 %d개: %s", len(keywords), keywords)
    logging.info("프롬프트: %s", prompt_cfg.get("name", "기본값(DB 없음)"))
    logging.info("수집 기준: 최근 %d시간 이내 등록 질문", HOURS_LIMIT)

    new_for_slack: list[dict] = []
    stats = {
        "keywords": keywords,
        "api_items": 0,
        "skipped_old": 0,        # 24시간 초과 항목
        "skipped_duplicate": 0,
        "skipped_gemini": 0,
        "inserted": 0,
        "insert_errors": 0,
    }

    for kw in keywords:
        try:
            items = fetch_kin(kw, naver_id, naver_secret)
        except Exception as e:
            logging.exception("[네이버 API] keyword=%s: %s", kw, e)
            continue

        logging.info("[%s] API 수집 %d건", kw, len(items))

        for idx, item in enumerate(items):
            stats["api_items"] += 1
            link = (item.get("link") or "").strip()
            if not link:
                continue

            # ── 24시간 필터 ──
            pub_date = item.get("pubDate", "")
            if not is_within_hours(pub_date, HOURS_LIMIT):
                stats["skipped_old"] += 1
                logging.debug("건너뜀(오래됨): %s | %s", pub_date, link)
                continue

            if row_exists(sb, link):
                stats["skipped_duplicate"] += 1
                continue

            title = _strip_tags(item.get("title") or "")
            desc  = _strip_tags(item.get("description") or "")

            try:
                law_data = search_law_data(sb, kw)
            except Exception as e:
                logging.warning("법령 조회 예외: %s", e)
                law_data = {"rules": [], "revisions": [], "precedents": []}

            prompt = build_prompt(title, desc, law_data, prompt_cfg)
            draft  = generate_draft(prompt, gemini_key)

            if not draft:
                stats["skipped_gemini"] += 1
                continue

            row = {
                "question_link":        link,
                "question_title":       title[:2000] or None,
                "question_description": desc[:8000] or None,
                "search_keyword":       kw,
                "sort_mode":            "date",
                "item_index":           idx,
                "raw_item":             item,
                "draft_answer":         draft,
                "matched_rules":        law_data,
                "run_at":               run_at,
                "status":               "DRAFT",
            }

            inserted, err = insert_log(sb, row)
            if inserted:
                stats["inserted"] += 1
                logging.info("✅ 저장: %s", title[:50])
                new_for_slack.append({"title": title, "link": link, "draft_preview": draft})
            elif err:
                stats["insert_errors"] += 1
            else:
                stats["skipped_duplicate"] += 1

    dashboard = supabase_dashboard_link(sb_url)
    if slack_env_ready() and new_for_slack:
        send_slack(
            os.environ["SLACK_BOT_TOKEN"].strip(),
            os.environ["SLACK_CHANNEL_ID"].strip(),
            new_for_slack, dashboard,
        )
    elif not slack_env_ready():
        logging.info("Slack 환경변수 미설정 — 알림 생략")

    logging.info("완료: %s", stats)
    print(json.dumps({"ok": True, "run_at": run_at, **stats}, ensure_ascii=False))


if __name__ == "__main__":
    main()
