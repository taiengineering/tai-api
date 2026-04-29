# Cursor 작업지시서 — engine-document 페이지 문서 전수조사 데이터 확장

> 작성일: 2026-04-29
> 작성자: Claude (TAI 비즈니스 창)
> 대상: admin.taieng.co.kr/html/horizontal-menu-template/engine-document
> 레포: taiengineering/tai-admin
> 난이도: 중 (프론트+백엔드)

---

## 1. 현재 상태

### 프론트엔드
- HTML: `admin/full-version/html/horizontal-menu-template/engine-document.html`
- JS: `admin/full-version/assets/js/tai/engine-document.page.js`
- 현재 11건의 법정서식(HWP 파일 다운로드)만 표시
- 3개 탭: 법정서식(11) / TAI표준서식(0) / 자유서식가이드(0)
- 테이블 컬럼: NO. / 서식코드 / 서식명 / 관련법령 / 제출처 / 접수방법 / 제출기한 / 과태료 / 관리
- 카테고리 필터 드롭다운 + 검색 입력
- 상단 통계카드: 전체 보관의무 / 보관 중 / 만료 임박(30일) / 만료 초과

### 백엔드 (tai-api)
- 현재 문서 서식 관련 API 없음 (프론트에서 하드코딩 또는 Supabase 직접 조회 추정)
- 기존 작업지시서 참고: `docs/TAI_엔진설정_문서메뉴_백엔드_작업지시서.md`
- 기존 작업지시서 참고: `docs/TAI_엔진설정_문서메뉴_프론트엔드_작업지시서.md`

---

## 2. 목표

179건의 문서 전수조사 데이터를 DB에 저장하고, engine-document 페이지에서 이를 조회·관리할 수 있도록 개선한다.

---

## 3. 작업 범위

### Phase 1: DB 테이블 생성 + 데이터 시딩 (백엔드)

#### 3-1. `document_forms` 테이블 생성 (Supabase Migration)

```sql
CREATE TABLE document_forms (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  doc_id TEXT UNIQUE NOT NULL,           -- DOC-OSH-001 등
  doc_name TEXT NOT NULL,                -- 서식명
  sector TEXT NOT NULL,                  -- 공통/산업/건설/건물
  category TEXT NOT NULL,                -- 착공전/일상/정기/작업시/사고시/감독대응/종료
  law_ref TEXT,                          -- 법 조항
  regulation_ref TEXT,                   -- 시행규칙·고시
  obligation TEXT DEFAULT '법정필수',     -- 법정필수/권고/실무관행
  penalty TEXT,                          -- 과태료/벌칙/없음
  submit_to TEXT,                        -- 제출처
  submit_timing TEXT,                    -- 제출 시기
  retention TEXT,                        -- 보관 기간
  writer TEXT,                           -- 작성 주체
  frequency TEXT,                        -- 작성 빈도
  tai_grade TEXT DEFAULT 'X',            -- A/B/C/D/X
  tai_difficulty TEXT DEFAULT 'X',       -- S/A/B/C/X
  ticket_cost INTEGER DEFAULT 0,         -- 이용권 소모 (A=0, B=10, C=30, D=50)
  existing_data TEXT,                    -- TAI에 이미 있는 데이터
  additional_input TEXT,                 -- 추가 입력 필요 필드
  priority INTEGER DEFAULT 5,            -- 개발 우선순위 (1~5)
  note TEXT,                             -- 비고
  file_url TEXT,                         -- HWP/양식 파일 URL (Supabase Storage)
  tab_type TEXT DEFAULT '법정서식',       -- 법정서식/TAI표준서식/자유서식가이드
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- 인덱스
CREATE INDEX idx_document_forms_sector ON document_forms(sector);
CREATE INDEX idx_document_forms_category ON document_forms(category);
CREATE INDEX idx_document_forms_tai_grade ON document_forms(tai_grade);
CREATE INDEX idx_document_forms_tab_type ON document_forms(tab_type);
```

#### 3-2. 데이터 시딩

179건의 CSV 데이터를 `document_forms` 테이블에 INSERT.
데이터 소스: `tai-api/docs/DOCUMENT_MAP_FULL.csv` (방금 이 세션에서 생성함 — tai-api GitHub에 없으면 outputs에서 가져올 것)

주의:
- CSV의 tai_grade별 ticket_cost 매핑: A=0, B=10, C=30, D=50, X=0
- tab_type 기본값: 전부 '법정서식'
- tai_grade가 A~D인 것 중 기존 11건에 해당하는 것은 file_url을 유지
- 100건 청크 단위로 INSERT (NOT EXISTS 서브쿼리 사용)

### Phase 2: 백엔드 API (tai-api)

#### 3-3. 라우터 생성: `routers/document_forms.py`

```python
# GET /document-forms
# 쿼리 파라미터: sector, category, tai_grade, tab_type, search, page, per_page
# 응답: { items: [...], total: N, page: N, per_page: N }

# GET /document-forms/{doc_id}
# 응답: 단건 상세

# GET /document-forms/stats
# 응답: { total: N, by_sector: {...}, by_grade: {...}, by_tab: {...} }
```

규칙:
- `from db.supabase_client import get_supabase`
- Router/Service 분리 (docs/DEV_RULES_SERVICE_LAYER.md 준수)
- 한 파일 최대 400줄

### Phase 3: 프론트엔드 수정 (tai-admin)

#### 3-4. engine-document.html 수정

대상: `admin/full-version/html/horizontal-menu-template/engine-document.html`

변경 사항:

1. **카테고리 필터 확장**
   - 현재: "전체" 드롭다운
   - 추가: 섹터 필터 (전체/공통/산업/건설/건물)
   - 추가: TAI등급 필터 (전체/A/B/C/D/X)
   - 추가: 카테고리 필터 (전체/착공전/일상/정기/작업시/사고시/감독대응/종료)

2. **테이블 컬럼 변경**
   - 기존 유지: 체크박스 / NO. / 서식코드 / 서식명 / 관련법령 / 제출처 / 제출기한 / 과태료
   - 추가: TAI등급 (뱃지: A=초록/B=파랑/C=주황/D=빨강/X=회색)
   - 추가: 티켓 (소모 매수 표시, X등급은 '-')
   - 관리 컬럼: 다운로드(HWP있으면) + 미리보기

3. **상단 통계카드 변경**
   - 전체 문서: 179건
   - TAI 자동화 가능: 115건 (A+B+C+D)
   - 등급A (SaaS 포함): 30건
   - 등급X (전문기관): 64건

4. **탭 카운트 동적 업데이트**
   - 법정서식 (179)
   - TAI표준서식 (0) — 추후 개발
   - 자유서식가이드 (0) — 추후 개발

#### 3-5. engine-document.page.js 수정

대상: `admin/full-version/assets/js/tai/engine-document.page.js`

변경 사항:

1. API 연동: 기존 하드코딩 → `GET /document-forms` API 호출
2. 필터 연동: 섹터/등급/카테고리 셀렉트박스 → API 쿼리 파라미터
3. 검색 연동: 서식명/법령명 검색 → API search 파라미터
4. 페이지네이션 추가 (179건이므로 필요)
5. 통계카드 동적 업데이트: `GET /document-forms/stats` API 호출

---

## 4. UI 디자인 참고

### TAI 등급 뱃지 스타일
```html
<span class="badge bg-label-success">A</span>  <!-- 무료 -->
<span class="badge bg-label-info">B</span>     <!-- 10매 -->
<span class="badge bg-label-warning">C</span>  <!-- 30매 -->
<span class="badge bg-label-danger">D</span>   <!-- 50매 -->
<span class="badge bg-label-secondary">X</span> <!-- 범위밖 -->
```

---

## 5. 필수 준수 규칙

- 200줄+ 파일 MCP 수정 금지 → Cursor 사용
- `from db.supabase_client import get_supabase`
- Router에 SQL 금지 → Service 레이어에서 처리
- `/health` 절대 503 금지
- 테이블 첫 번째 컬럼: 전체선택 체크박스
- 두 번째 컬럼: 순번(No.) 출력
- 카카오 API 전면 금지

---

## 6. 작업 순서

1. Supabase Migration: `document_forms` 테이블 생성
2. 데이터 시딩: 179건 INSERT
3. 백엔드: `routers/document_forms.py` + `services/document_forms_service.py` 생성
4. 프론트엔드: engine-document.html 수정 (필터 확장, 컬럼 추가)
5. 프론트엔드: engine-document.page.js 수정 (API 연동)
6. 테스트: 필터, 검색, 페이지네이션 동작 확인

---

## 7. 참고 문서

- `tai-api/docs/DOCUMENT_SERVICE_PLAN.md` — 문서생성·자동제출 서비스 기획서
- `tai-api/docs/DOCUMENT_MAP_ANALYSIS.md` — 전수조사 분석 결과
- `tai-api/docs/DOCUMENT_MAP_KEY30.csv` — 핵심 30건
- `tai-api/docs/DEV_RULES_SERVICE_LAYER.md` — 서비스 계층 분리 규칙
- `tai-admin/docs/TAI_엔진설정_문서메뉴_프론트엔드_작업지시서.md` — 기존 작업지시서
- `tai-admin/docs/TAI_엔진설정_문서메뉴_백엔드_작업지시서.md` — 기존 작업지시서
