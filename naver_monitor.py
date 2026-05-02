#!/usr/bin/env python3
"""
네이버 지식iN 모니터링 v4.0

[두 단계 분리 실행]
  STEP=collect  : 네이버 질문 수집 → DB 저장 (draft_answer 없이)
  STEP=generate : DB 미처리 건 → Gemini 초안 생성 → 슬랙 전송
  STEP 미설정   : collect → generate 순서로 전체 실행

[스케줄 예시]
  크론 09:00 → STEP=collect  (수집)
  크론 09:10 → STEP=generate (생성 + 슬랙)
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

# ── 기본값 ──
NAVER_KIN_API    = "https://openapi.naver.com/v1/search/kin.json"
GEMINI_API       = "https://generativelanguage.googleapis.com/v1beta/models"
SLACK_POST_URL   = "https://slack.com/api/chat.postMessage"
DIAGNOSIS_LINE   = "3분 무료 진단: https://taieng.co.kr/free-diagnosis.html"
DEFAULT_KEYWORDS = "안전관리자 선임,중대재해처벌법,산업안전보건법 과태료,안전보건관리체계"

HOURS_LIMIT      = 24    # 수집 기준: N시간 이내 질문만
GEMINI_DELAY_SEC = 2.0   # Gemini 호출 간 딜레이
GEMINI_RETRY_MAX = 3     # 429 재시도 최대 횟수
GEMINI_RETRY_WAIT= 15.0  # 429 대기(초)

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


# ════════════════════════════════════════
#  유틸
# ════════════════════════════════════════

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


def _test_mode() -> bool:
    return os.environ.get("TEST_MODE", "").strip() == "1"


def supabase_dashboard_link(supabase_url: str) -> str:
    m = re.search(r"https://([a-z0-9-]+)\.supabase\.co", supabase_url, re.I)
    return f"https://supabase.com/dashboard/project/{m.group(1)}" if m else "https://supabase.com/dashboard"


def slack_env_ready() -> bool:
    return bool(os.environ.get("SLACK_BOT_TOKEN", "").strip() and
                os.environ.get("SLACK_CHANNEL_ID", "").strip())


def is_within_hours(pub_date_str: str, hours: int = HOURS_LIMIT) -> bool:
    if not pub_date_str:
        return True
    try:
        pub_dt = parsedate_to_datetime(pub_date_str)
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        return pub_dt >= datetime.now(timezone.utc) - timedelta(hours=hours)
    except Exception as e:
        logging.warning("pubDate 파싱 실패(%s) — 통과 처리: %s", pub_date_str, e)
        return True


# ════════════════════════════════════════
#  DB 설정 로드
# ════════════════════════════════════════

def load_active_keywords(sb: Any) -> list[str]:
    try:
        r = sb.table("kin_keyword_sets").select("keywords").eq("is_active", True).limit(1).execute()
        if r.data and r.data[0].get("keywords"):
            kws = r.data[0]["keywords"]
            logging.info("DB 키워드 세트: %s", kws)
            return kws
    except Exception as e:
        logging.warning("kin_keyword_sets 조회 실패 — fallback: %s", e)
    raw = os.environ.get("NAVER_KIN_KEYWORDS", "").strip() or DEFAULT_KEYWORDS
    return [k.strip() for k in raw.split(",") if k.strip()]


def load_active_prompt(sb: Any) -> dict:
    try:
        r = sb.table("kin_prompt_settings").select("*").eq("is_active", True).limit(1).execute()
        if r.data:
            logging.info("DB 프롬프트: %s", r.data[0].get("name"))
            return r.data[0]
    except Exception as e:
        logging.warning("kin_prompt_settings 조회 실패 — 기본값 사용: %s", e)
    return {}


# ════════════════════════════════════════
#  STEP 1 : 수집 (collect)
# ════════════════════════════════════════

def fetch_kin(keyword: str, client_id: str, client_secret: str, display: int = 30) -> list[dict]:
    r = requests.get(
        NAVER_KIN_API,
        params={"query": keyword, "display": str(display), "start": "1", "sort": "date"},
        headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("items") or []


def row_exists(sb: Any, question_link: str) -> bool:
    try:
        r = sb.table("naver_kin_log").select("id").eq("question_link", question_link).limit(1).execute()
        return bool(r.data)
    except Exception as e:
        logging.warning("중복 조회 실패: %s", e)
        return False


def step_collect(sb: Any, naver_id: str, naver_secret: str, test: bool = False) -> dict:
    """
    네이버 질문 수집 → DB 저장 (draft_answer=None, status=DRAFT)
    Gemini 호출 없음.
    """
    keywords = load_active_keywords(sb)
    if test:
        keywords = keywords[:1]

    run_at = datetime.now(timezone.utc).isoformat()
    stats  = {"keywords": keywords, "api_items": 0, "skipped_old": 0,
               "skipped_duplicate": 0, "inserted": 0, "insert_errors": 0}

    for kw in keywords:
        try:
            items = fetch_kin(kw, naver_id, naver_secret, display=5 if test else 30)
        except Exception as e:
            logging.exception("[네이버 API] %s: %s", kw, e)
            continue

        logging.info("[collect] [%s] %d건 조회", kw, len(items))
        saved = 0

        for item in items:
            if test and saved >= 1:
                break

            stats["api_items"] += 1
            link = (item.get("link") or "").strip()
            if not link:
                continue

            if not is_within_hours(item.get("pubDate", ""), HOURS_LIMIT):
                stats["skipped_old"] += 1
                continue

            if row_exists(sb, link):
                stats["skipped_duplicate"] += 1
                continue

            title = _strip_tags(item.get("title") or "")
            desc  = _strip_tags(item.get("description") or "")

            row = {
                "question_link":        link,
                "question_title":       title[:2000] or None,
                "question_description": desc[:8000] or None,
                "search_keyword":       kw,
                "sort_mode":            "date",
                "raw_item":             item,
                "run_at":               run_at,
                "status":               "DRAFT",
                # draft_answer 없이 저장
            }

            try:
                sb.table("naver_kin_log").insert(row).execute()
                stats["inserted"] += 1
                saved += 1
                logging.info("✅ [collect] 저장: %s", title[:60])
            except Exception as e:
                msg = str(e).lower()
                if "duplicate" in msg or "unique" in msg or "23505" in msg:
                    stats["skipped_duplicate"] += 1
                else:
                    stats["insert_errors"] += 1
                    logging.error("insert 실패: %s", e)

    logging.info("[collect] 완료: %s", stats)
    return stats


# ════════════════════════════════════════
#  STEP 2 : 생성 (generate)
# ════════════════════════════════════════

def search_law_data(sb: Any, keyword: str) -> dict[str, list]:
    out: dict[str, list] = {"rules": [], "revisions": [], "precedents": []}
    try:
        out["rules"] = (
            sb.table("master_building_legal_rules")
            .select("law_name, obligation_summary, obligation_type, penalty_summary")
            .ilike("obligation_summary", f"%{keyword}%")
            .eq("is_active", True).limit(5).execute()
        ).data or []
    except Exception as e:
        logging.warning("rules 조회 실패: %s", e)

    try:
        out["revisions"] = (
            sb.table("law_revision_board")
            .select("law_name, title, summary, enforcement_date")
            .or_(f"title.ilike.%{keyword}%,summary.ilike.%{keyword}%")
            .eq("is_public", True).order("enforcement_date", desc=True).limit(3).execute()
        ).data or []
    except Exception as e:
        logging.warning("revisions 조회 실패: %s", e)

    try:
        out["precedents"] = (
            sb.table("industrial_accident_precedents")
            .select("case_name, summary, sentence_detail, fine_amount")
            .contains("keywords", [keyword])
            .eq("is_active", True).limit(3).execute()
        ).data or []
    except Exception as e:
        logging.warning("precedents 조회 실패: %s", e)

    return out


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


def call_gemini(prompt: str, api_key: str) -> str | None:
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
                logging.error("Gemini 최종 실패: %s", e)
                return None
        except Exception as e:
            logging.exception("Gemini 예외: %s", e)
            return None
    return None


def send_slack(token: str, channel: str, row: dict, dashboard: str) -> None:
    """1건 처리 완료 시 즉시 슬랙 전송."""
    title   = row.get("question_title") or "(제목없음)"
    link    = row.get("question_link") or ""
    draft   = (row.get("draft_answer") or "")[:300]
    keyword = row.get("search_keyword") or ""
    text = (
        f"🔔 *네이버 지식인 초안 생성 완료*\n\n"
        f"*질문:* {title}\n"
        f"*키워드:* `{keyword}`\n"
        f"{link}\n\n"
        f"> {draft}\n\n"
        f"📊 {dashboard}"
    )
    try:
        r = requests.post(
            SLACK_POST_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
            json={"channel": channel, "text": text},
            timeout=30,
        )
        body = r.json()
        if not body.get("ok"):
            logging.error("Slack 오류: %s", body)
        else:
            logging.info("✉️  Slack 전송 완료: %s", title[:40])
    except Exception as e:
        logging.exception("Slack 전송 실패: %s", e)


def step_generate(sb: Any, gemini_key: str, dashboard: str, test: bool = False) -> dict:
    """
    DB에서 draft_answer가 없는 DRAFT 건을 한 건씩 처리.
    Gemini 초안 생성 → DB 업데이트 → 슬랙 즉시 전송.
    """
    prompt_cfg = load_active_prompt(sb)

    # draft_answer가 NULL인 DRAFT 건 조회
    limit = 1 if test else 100
    try:
        r = (
            sb.table("naver_kin_log")
            .select("*")
            .eq("status", "DRAFT")
            .is_("draft_answer", "null")
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        pending = r.data or []
    except Exception as e:
        logging.error("미처리 건 조회 실패: %s", e)
        return {"error": str(e)}

    logging.info("[generate] 미처리 %d건 처리 시작", len(pending))
    stats = {"pending": len(pending), "generated": 0, "failed": 0, "slack_sent": 0}

    slack_ok = slack_env_ready()
    token    = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    channel  = os.environ.get("SLACK_CHANNEL_ID", "").strip()

    for row in pending:
        row_id   = row["id"]
        title    = row.get("question_title") or ""
        desc     = row.get("question_description") or ""
        keyword  = row.get("search_keyword") or ""

        logging.info("[generate] 처리 중: %s", title[:60])

        # 법령 DB 조회
        try:
            law_data = search_law_data(sb, keyword)
        except Exception as e:
            logging.warning("법령 조회 실패: %s", e)
            law_data = {"rules": [], "revisions": [], "precedents": []}

        # Gemini 초안 생성
        prompt = build_prompt(title, desc, law_data, prompt_cfg)
        draft  = call_gemini(prompt, gemini_key)

        if not draft:
            stats["failed"] += 1
            logging.warning("Gemini 실패 — 건너뜀: %s", title[:40])
            continue

        # DB 업데이트
        try:
            sb.table("naver_kin_log").update({
                "draft_answer": draft,
                "matched_rules": law_data,
            }).eq("id", row_id).execute()
            stats["generated"] += 1
            logging.info("✅ [generate] 초안 저장: %s", title[:60])
        except Exception as e:
            logging.error("draft_answer 업데이트 실패: %s", e)
            stats["failed"] += 1
            continue

        # 슬랙 즉시 전송
        if slack_ok:
            row["draft_answer"] = draft  # 전송용으로 갱신
            send_slack(token, channel, row, dashboard)
            stats["slack_sent"] += 1

    logging.info("[generate] 완료: %s", stats)
    return stats


# ════════════════════════════════════════
#  메인
# ════════════════════════════════════════

def main() -> None:
    naver_id     = _require_env("NAVER_CLIENT_ID")
    naver_secret = _require_env("NAVER_CLIENT_SECRET")
    sb_url       = _require_env("SUPABASE_URL")
    sb_key       = _require_env("SUPABASE_SERVICE_KEY")
    gemini_key   = _require_env("GEMINI_API_KEY")

    sb        = create_client(sb_url, sb_key)
    step      = os.environ.get("STEP", "").strip().lower()   # collect / generate / (비어있으면 전체)
    test      = _test_mode()
    dashboard = supabase_dashboard_link(sb_url)
    run_at    = datetime.now(timezone.utc).isoformat()

    if test:
        logging.info("🧪 TEST MODE 활성화")

    result: dict = {"ok": True, "run_at": run_at, "step": step or "all"}

    if step == "collect":
        result["collect"] = step_collect(sb, naver_id, naver_secret, test=test)

    elif step == "generate":
        result["generate"] = step_generate(sb, gemini_key, dashboard, test=test)

    else:
        # STEP 미설정 → 수집 후 바로 생성
        result["collect"]  = step_collect(sb, naver_id, naver_secret, test=test)
        result["generate"] = step_generate(sb, gemini_key, dashboard, test=test)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
