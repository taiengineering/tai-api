# [Cursor 작업지시서] 네이버 지식인 SEO 자동화 파이프라인

작성일: 2026-05-02
파일: `naver_monitor.py` (Railway Cron)
레포: `taiengineering/tai-api`

---

## 목적

네이버 지식인에서 산업안전 관련 신규 질문을 감지하고,
Supabase DB의 실제 법령·판례 데이터를 기반으로 **답변 초안**을 생성하여
DB에 저장한다. 답변 게시는 반드시 담당자가 수동으로 진행한다.

> ⚠️ **자동 게시 금지**: 네이버 지식인은 API 자동 답변 게시를 허용하지 않으며
> 약관 위반에 해당한다. 본 파이프라인은 초안 생성 + DB 저장까지만 담당한다.

---

## 환경변수 (`.env` / Railway Variables)

```
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
GEMINI_API_KEY=...          ← 원본 지시서에 누락됨. 반드시 추가.
MONITOR_KEYWORDS=안전관리자 선임,중대재해,산업안전보건법,과태료,안전관리자 선임 의무
```

---

## Supabase 테이블 구조 (실제 확인됨)

### 읽기 전용 (법령/판례 조회용)

| 테이블 | 용도 | 핵심 컬럼 |
|---|---|---|
| `master_building_legal_rules` | 의무 룰 마스터 (1,601건 A등급) | `obligation_summary`, `obligation_type`, `law_name`, `condition_summary`, `penalty_amount` |
| `law_revision_board` | 최신 법령 개정 정보 | `law_name`, `title`, `summary`, `body`, `enforcement_date`, `impact_description` |
| `industrial_accident_precedents` | 산재 판례 | `case_name`, `summary`, `violation_laws`, `penalty_info`, `sentence_detail`, `fine_amount`, `keywords` |
| `kosha_safety_materials` | KOSHA 안전보건자료 (18,200건) | `title`, `url`, `category`, `sector` |

### 쓰기 (결과 저장용) — 신규 생성 필요

`naver_kin_log` 테이블을 **파이프라인 최초 실행 전** 수동으로 생성할 것:

```sql
CREATE TABLE naver_kin_log (
  id          uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  question_url     text UNIQUE NOT NULL,          -- 중복 처리 키
  question_title   text NOT NULL,
  question_desc    text,
  keyword          text,                           -- 매칭된 모니터 키워드
  draft_answer     text,                           -- Gemini 생성 초안
  matched_rules    jsonb,                          -- 근거로 사용한 DB 데이터
  status           text DEFAULT 'DRAFT'            -- DRAFT | POSTED | SKIP
    CHECK (status IN ('DRAFT','POSTED','SKIP')),
  posted_at        timestamptz,
  created_at       timestamptz DEFAULT now()
);

CREATE INDEX idx_naver_kin_log_url ON naver_kin_log(question_url);
CREATE INDEX idx_naver_kin_log_status ON naver_kin_log(status);
```

---

## 파일 구조

```
tai-api/
├── naver_monitor.py       ← 메인 파이프라인 (신규 생성)
├── railway.toml           ← Cron 설정 (신규 생성 또는 기존에 추가)
└── .env                   ← 환경변수 (GEMINI_API_KEY 추가)
```

---

## `naver_monitor.py` 상세 스펙

### import 및 설정

```python
"""
네이버 지식인 SEO 자동화 파이프라인
- 네이버 검색 API → 신규 질문 감지 (중복 제외)
- Supabase DB 법령/판례 조회
- Gemini 답변 초안 생성
- naver_kin_log 테이블에 저장 (자동 게시 금지)
"""
import os, logging, httpx, json
from datetime import datetime, timezone
from supabase import create_client

# 환경변수
NAVER_CLIENT_ID     = os.environ["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = os.environ["NAVER_CLIENT_SECRET"]
SUPABASE_URL        = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY   = os.environ["SUPABASE_ANON_KEY"]
GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"]
MONITOR_KEYWORDS    = [k.strip() for k in os.environ.get(
    "MONITOR_KEYWORDS",
    "안전관리자 선임,중대재해,산업안전보건법,과태료"
).split(",")]

GEMINI_MODEL = "gemini-1.5-flash"
NAVER_KIN_SEARCH_URL = "https://openapi.naver.com/v1/search/kin.json"
DIAGNOSIS_LINK = "https://taieng.co.kr/free-diagnosis.html"
```

### Step 1 — 네이버 지식인 신규 질문 수집

```python
async def fetch_kin_questions(keyword: str, display: int = 10) -> list[dict]:
    """
    네이버 지식인 검색 API로 최신 질문 수집.
    sort=date 로 최신순 정렬.
    반환: [{title, link, description}, ...]
    """
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": display, "sort": "date"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(NAVER_KIN_SEARCH_URL, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json().get("items", [])
```

### Step 2 — 중복 확인 (핵심 — 원본 지시서에 없던 로직)

```python
def is_already_processed(sb, question_url: str) -> bool:
    """
    naver_kin_log 테이블에 이미 있는 URL이면 True.
    중복 처리 방지의 핵심.
    """
    r = sb.table("naver_kin_log") \
          .select("id") \
          .eq("question_url", question_url) \
          .limit(1) \
          .execute()
    return len(r.data) > 0
```

### Step 3 — Supabase 법령/판례 조회

```python
def search_law_data(sb, keyword: str) -> dict:
    """
    키워드로 세 테이블에서 관련 데이터 조회.
    - master_building_legal_rules: obligation_summary ILIKE
    - law_revision_board: title + summary ILIKE
    - industrial_accident_precedents: keywords 배열 포함 검색
    반환: {rules: [...], revisions: [...], precedents: [...]}
    """
    # 의무 룰 (A등급만)
    rules = sb.table("master_building_legal_rules") \
              .select("law_name, obligation_summary, obligation_type, penalty_amount, condition_summary") \
              .ilike("obligation_summary", f"%{keyword}%") \
              .eq("is_active", True) \
              .limit(5) \
              .execute().data

    # 최신 법령 개정
    revisions = sb.table("law_revision_board") \
                  .select("law_name, title, summary, enforcement_date, impact_description") \
                  .or_(f"title.ilike.%{keyword}%,summary.ilike.%{keyword}%") \
                  .eq("is_public", True) \
                  .order("enforcement_date", desc=True) \
                  .limit(3) \
                  .execute().data

    # 판례
    precedents = sb.table("industrial_accident_precedents") \
                   .select("case_name, summary, sentence_detail, fine_amount, violation_laws") \
                   .contains("keywords", [keyword]) \
                   .eq("is_active", True) \
                   .limit(3) \
                   .execute().data

    return {"rules": rules, "revisions": revisions, "precedents": precedents}
```

### Step 4 — Gemini 답변 초안 생성

```python
async def generate_draft(question_title: str, question_desc: str, law_data: dict) -> str:
    """
    Gemini API로 답변 초안 생성.
    
    프롬프트 규칙:
    - '법률 상담/자문' 절대 금지 → '조건코드 기반 자동 판정 결과'로 표현
    - 과장·확신 표현 금지 (예: "반드시", "무조건" → "일반적으로", "해당 조건에서는")
    - 법령 근거는 실제 DB 데이터만 인용 (hallucination 금지)
    - 답변 하단에 진단 링크 삽입
    """
    rules_text = "\n".join([
        f"- [{r['law_name']}] {r['obligation_summary']} (과태료: {r.get('penalty_amount','미확인')})"
        for r in law_data.get("rules", [])
    ]) or "관련 의무 룰 없음"

    revisions_text = "\n".join([
        f"- [{r['enforcement_date']}] {r['law_name']}: {r['summary']}"
        for r in law_data.get("revisions", [])
    ]) or "최근 개정 없음"

    precedents_text = "\n".join([
        f"- {p['case_name']}: {p['summary'][:100]}... (벌금: {p.get('fine_amount','미확인')}원)"
        for p in law_data.get("precedents", [])
    ]) or "관련 판례 없음"

    prompt = f"""
당신은 산업안전보건법 전문 정보 제공 시스템입니다.
아래 지식인 질문에 대해 TAI 엔지니어링 DB 데이터를 기반으로 답변 초안을 작성하세요.

[절대 금지]
- '법률 상담', '법률 자문', '법적 조언' 표현 금지
- DB에 없는 법령 조문 번호나 내용 임의 생성 금지
- 확신 표현("반드시", "무조건") 금지 → "해당 조건에서는", "일반적으로"로 대체

[답변 구조]
1. 핵심 요약 (2~3줄)
2. 적용 법령 및 의무 (DB 근거 데이터만)
3. 최근 개정 사항 (있을 경우)
4. 유사 판례 (있을 경우)
5. 진단 권유 링크

---
[질문 제목] {question_title}
[질문 내용] {question_desc}

[DB 조회 결과 — 적용 의무 룰]
{rules_text}

[DB 조회 결과 — 최근 법령 개정]
{revisions_text}

[DB 조회 결과 — 유사 판례]
{precedents_text}
---

답변 마지막에 반드시 아래 문구를 포함하세요:
"사업장 유형·규모에 따라 적용 법령이 달라집니다. 3분 무료 진단으로 해당 사업장 기준을 확인하세요: {DIAGNOSIS_LINK}"
"""

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
```

### Step 5 — 결과 저장

```python
def save_draft(sb, question_url: str, question_title: str, question_desc: str,
               keyword: str, draft: str, law_data: dict):
    sb.table("naver_kin_log").insert({
        "question_url": question_url,
        "question_title": question_title,
        "question_desc": question_desc[:500],
        "keyword": keyword,
        "draft_answer": draft,
        "matched_rules": law_data,
        "status": "DRAFT",
    }).execute()
```

### Step 6 — 메인 실행 흐름

```python
import asyncio

async def main():
    sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    total_new = 0

    for keyword in MONITOR_KEYWORDS:
        try:
            questions = await fetch_kin_questions(keyword)
        except Exception as e:
            logging.error(f"[{keyword}] 네이버 API 오류: {e}")
            continue

        for q in questions:
            url   = q.get("link", "")
            title = q.get("title", "").replace("<b>", "").replace("</b>", "")
            desc  = q.get("description", "").replace("<b>", "").replace("</b>", "")

            if not url or is_already_processed(sb, url):
                continue

            try:
                law_data = search_law_data(sb, keyword)
                draft    = await generate_draft(title, desc, law_data)
                save_draft(sb, url, title, desc, keyword, draft, law_data)
                total_new += 1
                logging.info(f"[NEW] {keyword} | {title[:40]}")
            except Exception as e:
                logging.error(f"[FAIL] {url}: {e}")
                # 실패해도 중복 방지용으로 SKIP 저장
                sb.table("naver_kin_log").insert({
                    "question_url": url,
                    "question_title": title,
                    "keyword": keyword,
                    "status": "SKIP",
                    "draft_answer": f"ERROR: {str(e)[:200]}",
                    "matched_rules": {},
                }).execute()

    logging.info(f"완료: 신규 {total_new}건 처리")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main())
```

---

## `railway.toml` — Cron 설정

```toml
[deploy]
startCommand = "python naver_monitor.py"

[[crons]]
schedule = "0 9 * * *"     # 매일 오전 9시 (KST) 실행
command   = "python naver_monitor.py"
```

> Railway 환경은 UTC 기준. KST 09:00 = UTC 00:00 → `"0 0 * * *"`로 변경할 것.

---

## 의존성 추가 (`requirements.txt`)

기존 의존성에 아래 추가:

```
google-generativeai>=0.5.0   # Gemini SDK (또는 httpx 직접 호출로 대체 가능)
supabase>=2.0.0
httpx>=0.27.0
```

---

## DB 사전 작업 (코드 실행 전 Supabase에서 수동 실행)

위 Step 3의 `naver_kin_log` 테이블 CREATE SQL을 Supabase SQL Editor에서 직접 실행할 것.

---

## 실행 후 확인

```sql
-- 생성된 초안 확인
SELECT keyword, question_title, status, created_at
FROM naver_kin_log
ORDER BY created_at DESC
LIMIT 20;

-- 초안 내용 확인
SELECT draft_answer FROM naver_kin_log WHERE status = 'DRAFT' LIMIT 1;
```

---

## 주의사항

1. **자동 게시 절대 금지** — `naver_kin_log`의 `draft_answer`를 담당자가 검토 후 수동 게시
2. **법령 hallucination 방지** — Gemini가 DB에 없는 법령을 만들어낼 수 있음. 프롬프트에 명시했으나, 게시 전 반드시 법령 조문 검증 필요
3. **네이버 API 일일 한도** — 검색 API는 하루 25,000콜. 키워드 × 10건 = 여유 있음
4. **Gemini 비용** — Flash 모델 사용으로 최소화. 키워드 5개 × 10건 = 50콜/일 수준

---

## 커밋 메시지

```
feat(seo): 네이버 지식인 모니터링 파이프라인 추가 (naver_monitor.py)
```
