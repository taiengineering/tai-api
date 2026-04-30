# TAI engine-document 문서 엔진 개발 — 개발 창 전달 프롬프트

아래 내용을 새 Claude 창(개발 창)에 복사하여 붙여넣으세요.

---

## 복사 시작 ▼▼▼

TAI Engineering 개발 창입니다. engine-document 페이지 개선 작업을 진행합니다.

## 배경

TAI Safe는 산업안전 통합 관리 SaaS 플랫폼입니다. 문서 자동생성·자동제출 서비스를 기획하여, 179건의 산업안전 법정 문서를 전수조사하고 TAI 자동화 판단(등급 A/B/C/D/X)을 완료했습니다.

핵심 개념: "빈 양식을 파는 게 아니라, 사용자가 매일 입력한 데이터(점검·TBM·교육 등)가 법정 문서로 자동 변환되는 엔진"을 만드는 것입니다.

## 현재 상태

### Cursor Phase 1~2 완료
- `sql/20260429_document_forms.sql` — 테이블 마이그레이션 파일 (document_forms)
- `scripts/seed_document_forms_from_csv.py` — CSV 시딩 스크립트 (179건, upsert, 100건 청크)
- `routers/document_forms.py` — 백엔드 API (GET /document-forms, /stats, /{doc_id})
- `services/document_forms_service.py` — 서비스 레이어
- `main.py` — document_forms_router 등록 완료

### 블로커: Supabase 테이블 생성 + 시딩 미완료
- Supabase MCP 연결 끊김 → 대시보드 SQL Editor에서 직접 실행 필요
- 테이블 생성: Supabase SQL Editor에서 `sql/20260429_document_forms.sql` 실행
- 시딩: 환경변수 설정 후 `python scripts/seed_document_forms_from_csv.py`
- 또는 Supabase MCP가 연결되면 직접 실행

### Phase 3 미착수 (프론트엔드)
- 대상 파일:
  - `admin/full-version/html/horizontal-menu-template/engine-document.html` (tai-admin 레포)
  - `admin/full-version/assets/js/tai/engine-document.page.js` (tai-admin 레포)

## 작업 순서

### Step 1: Supabase 테이블 생성 + 179건 시딩
Supabase MCP가 연결되어 있으면 직접 실행. 아니면 대표님에게 대시보드에서 실행 요청.

프로젝트 ID: vwlahtguyggrhvslabax (서울 리전)
데이터 소스: `tai-api/docs/DOCUMENT_MAP_FULL.csv` (179건)

### Step 2: 프론트엔드 수정 (Phase 3)
작업지시서: `tai-api/docs/WORKORDER_ENGINE_DOCUMENT_V2.md` 참조

변경 사항:
1. 필터 확장: 섹터(공통/산업/건설/건물), TAI등급(A/B/C/D/X), 카테고리(착공전/일상/정기 등)
2. 테이블 컬럼 추가: TAI등급 뱃지 + 티켓(소모매수)
3. 상단 통계카드: 전체 179건 / TAI 자동화 가능 115건 / 등급A 30건 / 등급X 64건
4. 탭 카운트 동적 업데이트
5. API 연동: 기존 하드코딩 → GET /document-forms API 호출
6. 페이지네이션 추가

### Step 3: 배포 확인

## 참고 문서 (tai-api 레포)
- `docs/WORKORDER_ENGINE_DOCUMENT_V2.md` — Cursor 작업지시서 (상세)
- `docs/DOCUMENT_SERVICE_PLAN.md` — 문서생성·자동제출 서비스 기획서
- `docs/DOCUMENT_MAP_FULL.csv` — 179건 전체 CSV
- `docs/DOCUMENT_MAP_ANALYSIS.md` — 전수조사 분석 결과
- `docs/DEV_RULES_SERVICE_LAYER.md` — 서비스 계층 분리 규칙

## 기술 스택
- Backend: FastAPI/Python → Railway 싱가포르
- DB: Supabase 서울 (vwlahtguyggrhvslabax)
- Frontend: HTML + Bootstrap5 Vuexy → Cloudflare Pages
- 레포: taiengineering/tai-api (백엔드), taiengineering/tai-admin (프론트엔드)

## 필수 규칙
- `from db.supabase_client import get_supabase`
- 200줄+ 파일 MCP 수정 금지 → Cursor 사용
- Router에 SQL 금지 → Service 레이어에서 처리
- 테이블 첫 번째 컬럼: 전체선택 체크박스, 두 번째: 순번(No.)
- `/health` 절대 503 금지
- 카카오 API 전면 금지

먼저 `docs/WORKORDER_ENGINE_DOCUMENT_V2.md`를 읽고 작업을 시작해주세요.

## 복사 끝 ▲▲▲
