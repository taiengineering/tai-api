# TAI 백엔드 작업지시서 — 안전정보 게시판 + 공공API

> 작성일: 2026-03-28  
> 우선순위: 🔴 즉시 → 🟡 2~4주  
> 레포: taiengineering/tai-api  
> 배포: Railway (api.taieng.co.kr)

---

## 🔴 즉시 (이번 세션)

---

### 1. posts 테이블 생성 (안전정보 게시판 DB)

```sql
CREATE TABLE posts (
  id           BIGSERIAL PRIMARY KEY,
  title        TEXT NOT NULL,
  content      TEXT,
  summary      TEXT,                          -- 목록용 요약 (200자 이내)
  category     TEXT NOT NULL,                 -- 아래 값 참고
  source       TEXT NOT NULL DEFAULT 'TAI_MANUAL', -- 아래 값 참고
  source_url   TEXT,                          -- 원본 URL (KOSHA 등)
  ksic_code    TEXT,                          -- 업종 연관 (재해사례용)
  tags         TEXT[],                        -- 태그 배열
  thumbnail_url TEXT,
  view_count   INTEGER NOT NULL DEFAULT 0,
  is_published BOOLEAN NOT NULL DEFAULT TRUE,
  published_at TIMESTAMPTZ DEFAULT NOW(),
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_posts_category ON posts(category);
CREATE INDEX idx_posts_source ON posts(source);
CREATE INDEX idx_posts_published_at ON posts(published_at DESC);
CREATE INDEX idx_posts_ksic_code ON posts(ksic_code);
```

**category 값:**
```
'disaster_daily'   -- 건설업 일별 중대재해현황 (KOSHA API, 매일)
'accident_case'    -- 국내 재해사례 (KOSHA API, 주 1회)
'kosha_guide'      -- KOSHA GUIDE 기술지침 (분기 1회)
'law_update'       -- 법령 개정 안내 (월 1회)
'safety_tip'       -- 안전팁 (TAI 자체 작성)
```

**source 값:**
```
'KOSHA_DAILY'   -- 건설업 일별 중대재해 자동 수집
'KOSHA_API'     -- KOSHA API 주기 수집
'LAW_API'       -- 법제처 API
'TAI_MANUAL'    -- TAI 자체 작성
```

---

### 2. GET /posts — 목록 API

**파일:** `routers/posts.py` (신규 생성)

```python
# GET /posts
# Query params:
#   category: str (선택, 미입력 시 전체)
#   page: int (기본값 1)
#   size: int (기본값 9, 최대 50)
#   sort: str (기본값 'latest' | 'views')
#   search: str (선택, 제목 검색)
#   ksic_code: str (선택, 업종별 필터)

# Response:
# {
#   "items": [
#     {
#       "id": 1,
#       "title": "...",
#       "summary": "...",
#       "category": "disaster_daily",
#       "source": "KOSHA_DAILY",
#       "source_url": "https://...",
#       "view_count": 142,
#       "published_at": "2026-03-28T00:00:00Z"
#     }
#   ],
#   "total": 100,
#   "page": 1,
#   "size": 9,
#   "pages": 12
# }
```

---

### 3. GET /posts/{id} — 상세 API

```python
# GET /posts/{id}
# - 조회 시 view_count +1
# - 이전글/다음글 id 포함 반환

# Response:
# {
#   "id": 1,
#   "title": "...",
#   "content": "...",     -- 전체 본문
#   "category": "...",
#   "source": "...",
#   "source_url": "...",
#   "view_count": 143,
#   "published_at": "...",
#   "prev": {"id": null, "title": null},
#   "next": {"id": 2, "title": "다음글 제목"}
# }
```

---

### 4. GET /posts/latest — 메인 노출용

```python
# GET /posts/latest?limit=3
# - 메인 index.html 최신 안전정보 3카드용
# - is_published=true, 최신순
# - 인증 불필요 (공개 API)
```

---

### 5. GET /posts/stats/today — 오늘의 통계 위젯

```python
# GET /posts/stats/today
# - safety-news.html 헤더 오른쪽 위젯용

# Response:
# {
#   "disaster_today": "사망 2건 발생",  -- 오늘 disaster_daily 최신 title 파싱
#   "disaster_month": "28건 (3월)",
#   "accident_cases_recent": 12,         -- 최근 1주 accident_case 건수
#   "kosha_guides_total": 487            -- kosha_guide 전체 건수
# }
```

---

### 6. routers/kosha_api.py 신규 생성 (공공API 통합 허브)

**파일:** `routers/kosha_api.py`

아래 엔드포인트 뼈대 생성 (일단 빈 구현으로 시작, 순차 완성):

#### 6-1. POST /verify/business 🔴 (즉시 구현)

```python
# POST /verify/business
# - 국세청 사업자등록정보 상태조회 API 연동
# - 환경변수: NTS_API_KEY
# - 공개 API (선임/수선 신청 폼에서 호출)

# Request body:
# { "biz_no": "0000000000" }   -- 하이픈 제거한 10자리

# Response:
# {
#   "valid": true,
#   "status": "계속사업자",    -- "계속사업자" | "휴업자" | "폐업자"
#   "biz_name": "주식회사 예시"
# }

# 국세청 API 엔드포인트:
# POST https://api.odcloud.kr/api/nts-businessman/v1/status
# Headers: Authorization: Infuser {NTS_API_KEY}
# Body: { "b_no": ["0000000000"] }
```

#### 6-2. GET /kosha/accident-cases 🟡 (2~4주)

```python
# GET /kosha/accident-cases?ksic_code={code}&limit=3
# - KOSHA 국내재해사례 API 연동
# - 법령진단 결과 하단 연동용
# - 환경변수: KOSHA_ACCIDENT_API_KEY
```

#### 6-3. GET /kosha/guides 🟡 (2~4주)

```python
# GET /kosha/guides?rule_code={code}
# GET /kosha/guides/{guide_no}
# - KOSHA GUIDE (코샤가이드) 조회
# - 법령진단 결과 [기술지침 보기] 버튼 연동
# - 환경변수: KOSHA_GUIDE_API_KEY
```

#### 6-4. GET /region-safety 🟡 (2~4주)

```python
# GET /region-safety?sigungu_code={code}
# - 행안부 안전정보 통합공개 API 연동
# - 대시보드 위젯용
# - 환경변수: REGION_SAFETY_API_KEY
```

---

### 7. main.py 라우터 등록

```python
# main.py에 추가:
from routers import posts, kosha_api

app.include_router(posts.router, prefix="", tags=["posts"])
app.include_router(kosha_api.router, prefix="", tags=["kosha"])
```

---

## 🟡 2~4주 (다음 우선순위)

### 8. 배치 스케줄러 — 건설업 일별 중대재해 수집

```python
# 매일 오전 06:00 Railway Cron 또는 APScheduler
# KOSHA 건설업 일별 중대재해현황 API 호출
# → posts 테이블 INSERT (category='disaster_daily', source='KOSHA_DAILY')
# 환경변수: KOSHA_DISASTER_API_KEY

# POST /admin/disaster-stats-sync (수동 트리거용도 제공)
```

### 9. 배치 — 국세청 공급자 월 1회 재검증

```python
# POST /admin/verify/suppliers
# - users 또는 contracts 테이블에서 user_type='manager'|'repair' 전체 조회
# - 사업자번호 국세청 API 일괄 재검증 (10건씩 배치)
# - 폐업 감지 시 is_active=false + 관리자 알림 (Resend)
```

---

## 환경변수 추가 목록 (Railway)

| 변수명 | 용도 | 우선순위 |
|--------|------|----------|
| `NTS_API_KEY` | 국세청 사업자 검증 | 🔴 즉시 |
| `KOSHA_DISASTER_API_KEY` | 건설업 일별 중대재해 | 🟡 |
| `KOSHA_ACCIDENT_API_KEY` | 국내 재해사례 | 🟡 |
| `KOSHA_GUIDE_API_KEY` | KOSHA GUIDE | 🟡 |
| `KOSHA_LAW_API_KEY` | 안전보건법령 스마트검색 | 🟡 |
| `REGION_SAFETY_API_KEY` | 행안부 안전정보 | 🟡 |

> 📌 공공데이터포털 마이페이지 → 각 API 인증키 확인 후 Railway 환경변수에 등록

---

## 프론트엔드 연동 포인트

| 화면 | API | 비고 |
|------|-----|------|
| safety-news.html 목록 | `GET /posts?category=&page=&size=9` | 더미 데이터 주석 해제 |
| safety-news-detail.html | `GET /posts/{id}` | 이전/다음글 포함 |
| index.html 최신 3카드 | `GET /posts/latest?limit=3` | 자동 교체 |
| safety-news.html 통계 위젯 | `GET /posts/stats/today` | LIVE 수치 |
| apply-manager/repair.html | `POST /verify/business` | 검증 없이 제출만 받음 (어드민 검증) |

> ⚠️ 프론트는 더미 데이터 아래 `/* TODO: API 연동 시 주석 해제 */` 처리 완료  
> API 구현 후 주석만 해제하면 바로 연동됨

---

## 완료 보고 기준

```
🔴 즉시 완료 체크리스트:
□ posts 테이블 Supabase 생성
□ GET /posts (목록, 페이지네이션)
□ GET /posts/{id} (상세, view_count +1)
□ GET /posts/latest?limit=3
□ GET /posts/stats/today
□ routers/kosha_api.py 생성
□ POST /verify/business (국세청 연동)
□ main.py 라우터 등록
□ Railway 환경변수 NTS_API_KEY 추가
□ Railway 배포 확인
```
