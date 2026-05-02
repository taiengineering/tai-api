# [Cursor 작업지시서] naver_monitor.py v2 — 수집+Gemini초안+슬랙알림 통합

작성일: 2026-05-02
대상 파일: `naver_monitor.py` (tai-api 레포 루트)
배경: v1은 수집만. v2에서 수집 → Gemini 초안생성 → 슬랙 알림 3단계를 한 크론에 통합.

---

## 환경변수 추가 필요 (Railway Variables)

기존 변수 유지. 아래 3개 추가:

```
GEMINI_API_KEY=...               # Gemini Flash API 키 (이미 등록됨)
SLACK_BOT_TOKEN=xoxb-...         # 슬랙 Bot Token
SLACK_CHANNEL_ID=C...            # 알림 받을 채널 ID  ← 담당자 확인 필요
```

---

## 전체 흐름 (한 크론, 09:00 KST)

```
[Step 1] 네이버 지식인 API → 신규 질문 수집
         ↓ question_link UNIQUE 제약으로 중복 자동 제외
[Step 2] 신규 질문마다 Supabase 법령DB 조회
         - master_building_legal_rules (의무 룰)
         - law_revision_board (최신 개정)
         - industrial_accident_precedents (판례)
[Step 3] Gemini Flash → 답변 초안 생성
         - draft_answer 컬럼에 저장
         - status = 'DRAFT'
[Step 4] 슬랙 알림 전송 (신규 질문 수 > 0일 때만)
         - 수집 건수 요약
         - 각 질문 제목 + 초안 첫 200자 미리보기
         - Supabase 링크 (담당자 검토용)
```

---

## `naver_monitor.py` 전체 교체 스펙

기존 v1 파일을 아래 코드로 **완전 교체**한다.

```python
#!/usr/bin/env python3
"""
네이버 지식인 모니터링 v2
- 수집 → Gemini 초안 생성 → 슬랙 알림 (한 크론에 통합)
- 자동 게시 금지. 수동 검토 후 게시.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

import requests

NAVER_KIN_API    = "https://openapi.naver.com/v1/search/kin.json"
GEMINI_API_URL   = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
DIAGNOSIS_LINK   = "https://taieng.co.kr/free-diagnosis.html"
SUPABASE_TABLE   = "naver_kin_log"


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def _strip_tags(text: str) -> str:
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", " ", text)
    t = html.unescape(t)
    return " ".join(t.split())


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _require_env(name: str) -> str:
    v = _env(name)
    if not v:
        print(f"[ERROR] Missing env: {name}", file=sys.stderr)
        sys.exit(1)
    return v


def _keywords() -> list[str]:
    raw = _env("NAVER_KIN_KEYWORDS")
    if not raw:
        return ["안전관리자 선임", "중대재해처벌법", "산업안전보건법 과태료", "안전보건관리체계"]
    return [k.strip() for k in raw.split(",") if k.strip()]


# ── Step 1: 네이버 API ────────────────────────────────────────────────────────

def fetch_kin_items(keyword: str) -> list[dict[str, Any]]:
    r = requests.get(
        NAVER_KIN_API,
        params={"query": keyword, "display": "30", "start": "1", "sort": "date"},
        headers={
            "X-Naver-Client-Id":     _require_env("NAVER_CLIENT_ID"),
            "X-Naver-Client-Secret": _require_env("NAVER_CLIENT_SECRET"),
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("items") or []


# ── Step 2: Supabase 법령 조회 ────────────────────────────────────────────────

def search_law_data(keyword: str, sb_url: str, sb_key: str) -> dict:
    headers = {
        "apikey": sb_key,
        "Authorization": f"Bearer {sb_key}",
        "Content-Type": "application/json",
    }
    base = sb_url.rstrip("/") + "/rest/v1"

    def _get(path: str, params: dict) -> list:
        try:
            r = requests.get(f"{base}/{path}", headers=headers, params=params, timeout=10)
            return r.json() if r.ok else []
        except Exception:
            return []

    kw = keyword[:30]
    rules = _get("master_building_legal_rules", {
        "select": "law_name,obligation_summary,penalty_amount",
        "obligation_summary": f"ilike.*{kw}*",
        "is_active": "eq.true",
        "limit": "5",
    })
    revisions = _get("law_revision_board", {
        "select": "law_name,title,summary,enforcement_date",
        "title": f"ilike.*{kw}*",
        "is_public": "eq.true",
        "order": "enforcement_date.desc",
        "limit": "3",
    })
    precedents = _get("industrial_accident_precedents", {
        "select": "case_name,summary,sentence_detail,fine_amount",
        "keywords": f"cs.{{{kw}}}",
        "is_active": "eq.true",
        "limit": "3",
    })
    return {"rules": rules, "revisions": revisions, "precedents": precedents}


# ── Step 3: Gemini 초안 생성 ──────────────────────────────────────────────────

def generate_draft(title: str, desc: str, law_data: dict) -> str:
    def _fmt_rules(items: list) -> str:
        if not items:
            return "관련 의무 룰 없음"
        return "\n".join(
            f"- [{r.get('law_name','')}] {r.get('obligation_summary','')} (과태료: {r.get('penalty_amount','미확인')})"
            for r in items
        )

    def _fmt_revisions(items: list) -> str:
        if not items:
            return "최근 개정 없음"
        return "\n".join(
            f"- [{r.get('enforcement_date','')}] {r.get('law_name','')}: {r.get('summary','')}"
            for r in items
        )

    def _fmt_precedents(items: list) -> str:
        if not items:
            return "관련 판례 없음"
        return "\n".join(
            f"- {p.get('case_name','')}: {str(p.get('summary',''))[:80]}... (벌금: {p.get('fine_amount','미확인')}원)"
            for p in items
        )

    prompt = f"""당신은 산업안전보건 정보 제공 시스템입니다.

[절대 금지]
- '법률 상담', '법률 자문', '법적 조언' 표현 금지
- DB에 없는 법령 조문 번호나 내용 임의 생성 금지
- 확신 표현("반드시", "무조건") 금지 → "해당 조건에서는", "일반적으로"로 대체

[답변 구조]
1. 핵심 요약 (2~3줄)
2. 적용 법령 및 의무 (아래 DB 데이터 기반)
3. 최근 개정 사항 (있을 경우)
4. 유사 판례 (있을 경우)
5. 하단 필수 문구

[지식인 질문]
제목: {title}
내용: {desc[:300]}

[DB 조회 결과 — 의무 룰]
{_fmt_rules(law_data.get('rules', []))}

[DB 조회 결과 — 최근 개정]
{_fmt_revisions(law_data.get('revisions', []))}

[DB 조회 결과 — 판례]
{_fmt_precedents(law_data.get('precedents', []))}

답변 마지막에 반드시 포함:
"사업장 유형·규모에 따라 적용 법령이 달라집니다. 3분 무료 진단으로 확인하세요: {DIAGNOSIS_LINK}"
"""
    r = requests.post(
        GEMINI_API_URL,
        params={"key": _require_env("GEMINI_API_KEY")},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=30,
    )
    if not r.ok:
        return f"[Gemini 오류 {r.status_code}]"
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return "[초안 파싱 실패]"


# ── Supabase INSERT ────────────────────────────────────────────────────────────

def supabase_insert(sb_url: str, sb_key: str, row: dict) -> tuple[bool, int]:
    headers = {
        "apikey": sb_key,
        "Authorization": f"Bearer {sb_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    r = requests.post(
        sb_url.rstrip("/") + f"/rest/v1/{SUPABASE_TABLE}",
        headers=headers,
        json=row,
        timeout=30,
    )
    if r.status_code in (200, 201):
        return True, r.status_code
    if r.status_code == 409:
        return False, 409
    print(f"[Supabase 오류] {r.status_code}: {r.text[:300]}", file=sys.stderr)
    return False, r.status_code


# ── Step 4: 슬랙 알림 ─────────────────────────────────────────────────────────

def send_slack(inserted_rows: list[dict], run_at: str) -> None:
    token      = _env("SLACK_BOT_TOKEN")
    channel_id = _env("SLACK_CHANNEL_ID")
    if not token or not channel_id:
        print("[SKIP] SLACK_BOT_TOKEN 또는 SLACK_CHANNEL_ID 미설정", file=sys.stderr)
        return
    if not inserted_rows:
        return

    lines = [
        f"*🔍 네이버 지식인 신규 {len(inserted_rows)}건 수집 완료*",
        f"수집 시각: {run_at[:16]} UTC",
        "",
    ]
    for row in inserted_rows[:5]:  # 최대 5건만 미리보기
        draft_preview = (row.get("draft_answer") or "")[:200].replace("\n", " ")
        lines += [
            f"*Q.* {row['question_title']}",
            f"<{row['question_link']}|질문 보기>",
            f"초안: {draft_preview}...",
            "---",
        ]
    if len(inserted_rows) > 5:
        lines.append(f"외 {len(inserted_rows)-5}건 더 있음")
    lines.append(f"\n<https://supabase.com/dashboard/project/vwlahtguyggrhvslabax/editor|Supabase에서 전체 확인 →>")

    requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"channel": channel_id, "text": "\n".join(lines), "unfurl_links": False},
        timeout=10,
    )


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    sb_url = _require_env("SUPABASE_URL")
    sb_key = _require_env("SUPABASE_SERVICE_ROLE_KEY")
    run_at = datetime.now(timezone.utc).isoformat()

    total_new, total_dup, total_seen = 0, 0, 0
    inserted_rows: list[dict] = []

    for kw in _keywords():
        try:
            items = fetch_kin_items(kw)
        except Exception as e:
            print(f"[ERROR] 네이버 API ({kw}): {e}", file=sys.stderr)
            continue

        for idx, item in enumerate(items):
            total_seen += 1
            link  = (item.get("link") or "").strip()
            title = _strip_tags(item.get("title") or "")
            desc  = _strip_tags(item.get("description") or "")
            if not link:
                continue

            # Step 2: 법령 조회
            law_data = search_law_data(kw, sb_url, sb_key)

            # Step 3: Gemini 초안
            try:
                draft = generate_draft(title, desc, law_data)
            except Exception as e:
                draft = f"[초안 생성 실패: {e}]"

            row = {
                "question_link":        link,
                "question_title":       title[:2000],
                "question_description": desc[:8000],
                "search_keyword":       kw,
                "sort_mode":            "date",
                "item_index":           idx,
                "raw_item":             item,
                "draft_answer":         draft,
                "matched_rules":        law_data,
                "run_at":               run_at,
                "status":               "DRAFT",
            }

            inserted, code = supabase_insert(sb_url, sb_key, row)
            if inserted:
                total_new += 1
                inserted_rows.append(row)
            elif code == 409:
                total_dup += 1

    # Step 4: 슬랙 알림
    send_slack(inserted_rows, run_at)

    result = {
        "ok":               True,
        "run_at":           run_at,
        "keywords":         _keywords(),
        "seen":             total_seen,
        "inserted":         total_new,
        "skipped_duplicate":total_dup,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

---

## `railway.toml` — Cron 유지

기존 그대로:

```toml
[[crons]]
schedule = "0 0 * * *"   # KST 09:00
command   = "python naver_monitor.py"
```

---

## Railway 환경변수 추가

기존 변수 외 아래 2개 추가:

| 변수 | 값 |
|---|---|
| `SLACK_BOT_TOKEN` | Slack Bot Token (xoxb-...) |
| `SLACK_CHANNEL_ID` | 알림 받을 채널 ID |

`GEMINI_API_KEY`는 이미 등록됨.

---

## 슬랙 알림 메시지 예시

```
🔍 네이버 지식인 신규 3건 수집 완료
수집 시각: 2026-05-02 00:00 UTC

Q. 안전관리자 선임 의무 기준이 어떻게 되나요?
질문 보기 (링크)
초안: 산업안전보건법 제17조에 따라 상시 근로자 50인 이상 사업장은...

---
Q. 중대재해처벌법 적용 대상 기준
...

Supabase에서 전체 확인 →
```

---

## 주의사항

- 자동 게시 로직 포함하지 말 것
- Gemini 실패 시 초안을 `[초안 생성 실패: ...]`로 저장하고 계속 진행 (크론 중단 금지)
- 슬랙 미설정 시 알림 없이 정상 종료 (크론 중단 금지)
- 신규 건 0개면 슬랙 메시지 전송 안 함

---

## 커밋 메시지

```
feat(seo): naver_monitor v2 — Gemini 초안생성 + 슬랙 알림 통합
```
