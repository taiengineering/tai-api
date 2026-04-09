# TAI Safe 미기록 세션 작업내역 — 2026-04-05~07

## 2026-04-07 법령엔진 세션 (TAI 법령엔진)

### 법령엔진 completeness 개선

**condition_code 설정 완료:**
- Construction ACTION 46건: `condition_code = 'construction_amount'`
- Building DOCUMENT 46건: 법령 유형 기반 condition_code 설정
- Manufacturing REPORT 22건 / ACTION 29건: condition_code 설정
- 전체 완성도: Building ~98%, Manufacturing ~98%, Construction ~95%

**document_form_master 확장:**
- 4개 컬럼 추가: `executor_type_code`, `executor_role`, `submit_deadline_days`, `submit_frequency`
- 27건 → 63건으로 확장
  - 선임 신고 서식 8건 추가
  - 점검 기록 서식 10건 추가
  - 건설 작업 유형별 작업 전 체크리스트 18건 추가

**form_code 매핑 개선:**

| obligation_type | 개선 전 | 개선 후 |
|----------------|---------|---------|
| APPOINT | 16% | 60% |
| INSPECT | 11% | 57% |
| BEFORE_WORK | 0% | 83% |
| DOCUMENT | 0% | 100% |

### inspection_sets.py v1.6.0

**신규 엔드포인트 2개:**
- `POST /inspection-sets/{set_id}/generate-items` — 단일 세트 점검 항목 자동 생성
- `POST /inspection-sets/generate-all-items` — 전체 일괄 생성 (dry_run 지원)

**로직:**
- `legal_rule_id` → `master_building_legal_rules` 조회
- obligation_type → check_type 매핑: INSPECT/ACTION/BEFORE_WORK→PASS_FAIL, APPOINT/DOCUMENT→CHECK, REPORT/NOTIFY→DATE
- MANUAL 세트 (legal_rule_id 없음) 스킵
- 이미 항목 있는 세트 스킵 (NOT EXISTS)

**결과:** inspection_set_items 0건 → 67건 생성

### e2e 테스트 파일
- `tests/test_e2e_form_flow.py` 생성
- 12개 시나리오 (Building/Manufacturing/Construction 섹터별)
- 의무→서식→제출기관→담당자 전체 흐름 검증

---

## 2026-04-07 기획 세션 (TAI 기획4)

### 안전관리자 관점 현황 분석

**DB 직접 쿼리 결과 확인:**
- `work_schedules`: 전체 MANUAL source_type (법령엔진 연동 0건)
- `inspection_set_items`: 296개 세트에 항목 0건
- `notifications`: 42개 설정에도 발송 0건
- `tbm_meetings`, `risk_assessments`, `form_submissions`: 모두 0건
- `work_assignments`: 1,161건 중 1,071건(92%) 담당자 미배정

**핵심 문제 진단:**
> 법령엔진 → 작업일정 → 담당자 배정 → D-3 알림 파이프라인이 끊어져 있음

### Work Order 문서 3개 작성 및 GitHub 업로드
- `docs/WORK_ORDER_20260407_backend_pipeline.md` — 법령→스케줄 자동생성 파이프라인
- `docs/WORK_ORDER_20260407_legal_engine_inspection_items.md` — 점검항목 자동생성
- 안전관리자 대시보드 work order (safe.taieng.co.kr/tadmin 용)

**중요 결정:** 안전관리자 대시보드는 admin이 아닌 **safe.taieng.co.kr(tadmin)** 에 구현

---

## 2026-04-07 프론트엔드 세션 (TAI 프론트5)

### 신규 HTML 페이지 생성

**engine-document.html** (문서 관리)
- 엔진 설정 하위 문서 관리 화면
- `document_form_master` 테이블 연동

**contract-kmong.html** (크몽 진단 요청 관리)
- `public_diagnosis_requests` 테이블 연동
- 기능:
  - 목록 (checkbox + No. 컬럼)
  - 상세 모달 (법령 진단 실행 포함)
  - HTML 편집기 팝업
  - PDF 발급 버튼 (xhtml2pdf → Supabase Storage)
- **버그 수정:** `data-skin="default"` 누락으로 Vuexy 레이아웃 미렌더링 → 추가

### 기존 페이지 업데이트

**engine-legal.html**
- rules 탭에 source 필터 추가
- condition_code 컬럼 추가

**engine-legal-ai.html**
- draft 카드에 법령 원문(article text) 미리보기 추가

### taieng.co.kr 공개 사이트

**요금제 페이지 추가** (`/tai-safe`)
- 베이직: 79,000원/월
- 프리미엄: 149,000원/월
- 엔터프라이즈: 별도 문의

**14개 사이트 HTML footer 사업자 정보 추가**
- 사업자등록번호: 723-39-01422
- 주소: 서울 강남구 테헤란로79길 6 JS타워 3층 V1314
- 전화: (이메일 문의)

---

## 2026-04-06 세션 (TAI 기획/백엔드)

### engine_qa.py v1.2.0
- 점수 시스템 변경

### legal_engine.py
- 중복 제거 수정 (deduplication fix)

### SPECIAL_FACILITY 섹터 제거
- `law_rule_generator.py` v1.5.0으로 업데이트
- SPECIAL_FACILITY 섹터 전체 제외 처리

### schedule_pipeline.py v1.0.0 (신규)
- `POST /legal-engine/generate-schedules/{factory_id}` — 최신 진단 결과 → work_schedules 생성
- `POST /notifications/trigger-due-alerts` — D-7/D-3/당일 마감 알림 생성

### construction.py v2.0.0
- 현장 등록 시 factories 자동 생성 (sector='CONSTRUCTION')
- 법령진단 자동 실행 + 일정 자동 생성
- user_role '025 현장소장' DB 추가

---

## 2026-04-05 세션 (프론트엔드·백엔드)

### GitHub Actions CI 4-job 파이프라인
- DB integrity check
- mapping coverage 검증
- API tests 78 cases
- Layer tests 29 cases

### DB 제약조건 5개 추가
- APPOINT target_code 영어 형식 강제
- INSPECT executor_type 유효값 제한
- 유효 섹터 코드 제한
- 유효 obligation_type 제한

### contract_kmong.py v1.0.0
- 크몽 법령 진단 5개 API
- HTML→PDF (xhtml2pdf) → Supabase Storage `diagnosis-pdfs` 버킷

### engine_document.py v1.0.0
- 문서 메뉴 백엔드 4개 엔드포인트
- DB 마이그레이션 + 10개 표준 TAI 서식 레코드

---

## 페르소나 기반 UX 분석 세션 (기획 참고용)

다음 페르소나들로 시스템 갭 분석 진행:
- **이창은 (지친 건설안전관리자)**: 법령엔진→작업일정 파이프라인 단절 발견
- **못된 현장소장 시뮬레이션**: 건설 섹터 테이블 전체 0건 확인
- **철두철미 건설안전관리자**: TBM/위험성평가/교육 이행 0건 지적
- **산업안전보건감독관 관점**: 작업자 직접 접점 UI·전자서명·사진 증빙 부재 지적

**공통 결론:**
1. 작업자가 직접 상호작용하는 인터페이스(모바일) 필요
2. 법령→일정→담당자→완료→기록 루프 미완결
3. TBM·위험성평가·교육이수가 법적 증빙의 핵심이나 0건
