# TAI 비즈니스 기획 창 — 세션 로그 2026-04-29

> 작성일: 2026-04-29
> 작성자: Claude (TAI 비즈니스 창)

---

## 완료 작업

### 1. 문서생성·자동제출 서비스 기획서 v1.0
- 이용권(티켓) 과금 체계 설계 (30매 49K ~ 500매 490K)
- SaaS 구독자 월간 보너스 (STARTER 5매, BUSINESS 10매, PRO 20매)
- PG 결제 연동 방침 ("포인트" 금지 → "이용권"으로 등록)
- 문서 등급 A/B/C/D/X 정의 + 티켓 소모량
- 기술 구조 (자동생성 + 관공서 제출 흐름)
- DB 스키마 설계 (tickets, ticket_transactions, documents, document_templates)
- 수익 시뮬레이션 (100개소 기준 월 3,160만원, 연 3.79억)
- GitHub: `docs/DOCUMENT_SERVICE_PLAN.md`

### 2. 문서 전수조사 179건 수집 완료
- ChatGPT에서 3축 교차검증 방식으로 수집
- OSH(공통/산업) 60건 + 건설현장 43건 + 건설법률 15건 + 중대재해법 12건 + 건물 19건 + 시설 18건 + 화학물질 12건
- TAI 자동화 판단 매핑 완료 (A 30건 / B 40건 / C 25건 / D 20건 / X 64건)
- GitHub: `docs/DOCUMENT_MAP_FULL.csv` (179건 전체)
- GitHub: `docs/DOCUMENT_MAP_KEY30.csv` (핵심 30건)
- GitHub: `docs/DOCUMENT_MAP_ANALYSIS.md` (분석 결과)

### 3. engine-document 페이지 개선 착수
- 현재 페이지 확인 (admin.taieng.co.kr/engine-document, 11건 HWP만 보관)
- Cursor 작업지시서 작성 및 GitHub 업로드
- GitHub: `docs/WORKORDER_ENGINE_DOCUMENT_V2.md`

### 4. Cursor Phase 1~2 완료
- Phase 1: DB 마이그레이션 파일 (`sql/20260429_document_forms.sql`) + 시딩 스크립트 (`scripts/seed_document_forms_from_csv.py`)
- Phase 2: 백엔드 API 구현 (`routers/document_forms.py` + `services/document_forms_service.py` + main.py 등록)
- 블로커: Supabase MCP 연결 끊김 → 테이블 생성 + 179건 시딩 미완료

### 5. 재도전성공패키지 관련
- 추경 공고 확인 (접수마감: 2026-05-07 16:00)
- 발표일 추정: 서류 5월말, 최종 6월 중하순
- K-Startup 특허 입력 위치 확인 (Step 04 성과현황 또는 Step 03 과제정보)

### 6. 핵심 기획 결정
- "문서 폼을 파는 게 아니라 데이터가 문서로 변환되는 키트를 파는 것" 확정
- TAI가 할 수 있는 것 115건(64%), 못 하는 것 64건(36%) → TAI Fix 연결 기회
- 특허 0067716번의 실질적 수익화 경로 확인

---

## 미완료 / 블로커

| 항목 | 상태 | 블로커 |
|---|---|---|
| Supabase document_forms 테이블 생성 | ⏸ | Supabase MCP 재연결 또는 대시보드 직접 실행 |
| 179건 데이터 시딩 | ⏸ | 테이블 생성 선행 |
| Phase 3 프론트엔드 (engine-document.html) | ⏸ | 시딩 완료 선행 |
| 사업계획서 HWP 입력 | ⏸ | 대표님 직접 (마감 D-8) |
| K-Startup 전산입력 (특허 포함) | ⏸ | 대표님 직접 |
| 폐업사실증명원 전체 발급 | ⏸ | 법인은 세무서 문의 필요 |
| 결제 페이지 구성 (이니시스 카드심사) | ⏸ | 개발 창에서 처리 |

---

## GitHub 커밋 이력 (오늘)

| 커밋 | 내용 |
|---|---|
| c310a113 | 사업계획서 매출200억 반영 수정 |
| (이전 세션) | DOCUMENT_SERVICE_PLAN.md 업로드 |
| 159ee6c3 | DOCUMENT_MAP_KEY30.csv + DOCUMENT_MAP_ANALYSIS.md |
| 49769de4 | DOCUMENT_MAP_FULL.csv (179건 전체) |
| b62fb34f | WORKORDER_ENGINE_DOCUMENT_V2.md (Cursor 작업지시서) |

---

## 내일 작업 목록 (2026-04-30)

### 우선순위 1: Supabase 시딩 완료
1. Supabase 대시보드 SQL Editor에서 `sql/20260429_document_forms.sql` 실행 (테이블 생성)
2. 환경변수 설정 후 `python scripts/seed_document_forms_from_csv.py` 실행 (179건 시딩)
3. 시딩 결과 확인 (`SELECT COUNT(*) FROM document_forms`)

### 우선순위 2: Cursor Phase 3 (프론트엔드)
4. engine-document.html 수정 (필터 확장, 컬럼 추가, 통계카드 변경)
5. engine-document.page.js 수정 (API 연동, 페이지네이션)
6. 배포 확인 (admin.taieng.co.kr/engine-document)

### 우선순위 3: 사업계획서 마감 준비 (D-8)
7. 사업계획서 HWP 입력 (대표님 직접)
8. K-Startup 전산입력 (과제명, 특허 출원목록)
9. 증빙서류: 폐업사실증명원 발급 (세무서 전화)

### 우선순위 4: 결제 페이지
10. 이니시스 카드심사 진입을 위한 결제 페이지 구성 (개발 창)
