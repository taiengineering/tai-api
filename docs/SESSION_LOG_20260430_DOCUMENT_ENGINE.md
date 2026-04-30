# 문서 엔진 세션 작업 내역 (2026-04-30)

> 세션 목표: TAI Safe 문서 엔진(engine-document) 전체 구축
> 결과: DB·백엔드·프론트·아키텍처·법적분석·TBM 이상표시까지 완료

---

## 완료 작업

### Phase 1: DB + 시딩
- `document_forms` 테이블 생성 (Supabase migration)
- 179건 4청크 INSERT 완료
- 실측: A:29 / B:49 / C:32 / D:25 / X:44 / 자동화가능:135

### Phase 2: 백엔드 API (기존 확인)
- `routers/document_forms.py` + `services/document_forms_service.py` 이미 존재
- GET /document-forms, /document-forms/stats, /document-forms/{id}

### Phase 3: 프론트엔드 전면 개편
- `engine-document.html` — 통계카드+필터+테이블+모달 전면 교체
- `engine-document.page.js` — API 전환(/engine/forms → /document-forms)
- 대상: admin + tadmin 양쪽

### Phase 4: 문서 자동생성 아키텍처
- `docs/DOCUMENT_ENGINE_ARCHITECTURE.md` — 엔진 설계서
- `templates/documents/DOC-OSH-056.html` — TBM HTML 템플릿 (Jinja2)
- `services/document_engine/renderer.py` — Jinja2 + Gotenberg PDF
- `services/document_engine/fetchers/tbm_fetcher.py` — TBM 데이터 패처
- `routers/document_engine.py` — preview/generate 엔드포인트
- main.py v5.39.0 등록

### Phase 5: 법적 필수 기재항목 갭 분석
- `docs/DOCUMENT_LEGAL_REQUIREMENTS_A_GRADE.md` (v3)
- 29건 중 28건 법정 양식 없음 → TAI 표준 설계 가능
- 6개 카테고리 분류, 갭 확인

### Phase 6: 최소 체크 원칙 + DB 변경
- 개인별 보호구 10개 체크박스 → 폐기
- 서명 = "보호구 착용 완료 + 건강 이상 없음" 포함
- 이상 시에만 관리감독자가 표시
- DB migration: `add_tbm_issue_and_edu_fields`
  - `tbm_attendees.issue_flag` BOOLEAN DEFAULT false
  - `tbm_attendees.issue_note` TEXT
  - `education_history.instructor_name` TEXT
  - `education_history.material_summary` TEXT

### Phase 7: TBM 이상 표시 기능
- `routers/tbm_issue.py` — PATCH /tbm/{id}/attendees/{aid}/issue
- main.py v5.40.0 등록
- `docs/WORKORDER_TBM_ISSUE_FLAG.md` — Cursor 프론트 작업지시서

### 핵심 결정사항
- 문서 헤더: 고객 회사명+시설명 (TAI는 푸터 "Powered by TAI Safe"만)
- 폰트: Pretendard Variable (CDN subset)
- 교육 모듈 미운영 → 교육 3건 후순위 보류
- 체크항목 최소화 원칙 확정

---

## 커밋 이력

| 커밋 | 내용 |
|------|------|
| sql/20260429_document_forms.sql | document_forms 테이블 + 179건 시딩 |
| engine-document.html | 프론트 전면 개편 |
| engine-document.page.js | JS API 전환 |
| DOCUMENT_ENGINE_ARCHITECTURE.md | 엔진 설계서 |
| DOC-OSH-056.html | TBM HTML 템플릿 |
| renderer.py + fetchers/ | 문서 렌더링 엔진 |
| document_engine.py | preview/generate API |
| main.py v5.39.0 | document_engine 등록 |
| DOCUMENT_LEGAL_REQUIREMENTS_A_GRADE.md v3 | 법적 갭 분석 |
| migration: add_tbm_issue_and_edu_fields | DB 컬럼 4개 추가 |
| tbm_issue.py | 이상 표시 API |
| main.py v5.40.0 | tbm_issue 등록 |
| WORKORDER_TBM_ISSUE_FLAG.md | Cursor 작업지시서 |

---

## PENDING 작업

| 순서 | 작업 | 우선순위 |
|------|------|----------|
| 1 | tbm-setting.html 프론트 — 이상 표시 UI (Cursor 작업지시서 준비됨) | ★★★★★ |
| 2 | 문서 템플릿 제작 — 카테고리 2+5 (22건, 데이터 즉시 가용) | ★★★★★ |
| 3 | 문서 템플릿 제작 — 카테고리 3+4 (TBM+보호구, 3건) | ★★★★ |
| 4 | 공사일지 법정 양식 템플릿 (1건) | ★★★ |
| 5 | ⏸ 교육 문서 템플릿 (3건) — 교육 모듈 가동 후 | - |

## 파일 위치

**tai-api:**
- docs/DOCUMENT_ENGINE_ARCHITECTURE.md
- docs/DOCUMENT_LEGAL_REQUIREMENTS_A_GRADE.md (v3)
- docs/DOCUMENT_MAP_FULL.csv
- docs/WORKORDER_TBM_ISSUE_FLAG.md
- templates/documents/DOC-OSH-056.html
- services/document_engine/renderer.py
- services/document_engine/fetchers/tbm_fetcher.py
- routers/document_engine.py
- routers/tbm_issue.py
- routers/document_forms.py

**tai-admin:**
- admin/.../engine-document.html
- admin/.../js/tai/engine-document.page.js
- tadmin/.../tbm-setting.html (이상표시 UI 추가 대상)
