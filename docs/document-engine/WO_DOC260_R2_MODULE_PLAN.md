---
title: WO DOC260 R2 공통 모듈 개발계획 (R2_FINAL)
wo: WO-DOC260-OBJ10-DELIVERY-VALIDITY-AUDIT-001
revision: R2_FINAL
status: ANALYSIS_COMPLETE — 구현 미승인
created: 2026-11-01
next_gate: GPT_DOC260_R2_FINAL_SOURCE_IV
---

## 전수 분류 최종 결과

| route_group | 건수 | KEEP | STOP | HOLD |
|-------------|------|------|------|------|
| A_INTERNAL  | 63   | 63   | 0    | 0    |
| B_OFFICIAL  | 16   | 0    | 16   | 0    |
| C_PORTAL    | 0    | —    | —    | —    |
| D_ACCEPTED  | 0    | 0    | 0    | 0    |
| E_EXTERNAL  | 9    | 0    | 9    | 0    |
| F_SCOPE_OUT | 43   | 0    | 43   | 0    |
| U_UNRESOLVED| 129  | 0    | 0    | 129  |
| **합계**    | **260** | **63** | **68** | **129** |

**분류 이력:**
- DOC-BLD-015: A_INTERNAL → U_UNRESOLVED (자체보관+지자체 제출 혼재, 주 경로 미확정)
- D_ACCEPTED 0건: 38건 전체 U_UNRESOLVED 이동 (팩스/이메일 전달 ≠ 기관 수리 확인)
- F_SCOPE_OUT 43건: TAI_OUT_IDS 43건만 (AGENCY_ONLY 단독 근거 건 제외)
- B_OFFICIAL 16건: doc_format=ORIGINAL_ONLY 근거 — 공식서식 버전 확인 완료 의미 아님

**수치 분리:**

| 항목 | 건수 |
|------|------|
| route_confidence = CONFIRMED | 131 |
| route_confidence = PROBABLE  | 0   |
| route_confidence = UNVERIFIED | 129 |
| INTERNAL_USE_CONFIRMED (A_INTERNAL) | 63 |
| EXTERNAL_OUTPUT_ACCEPTED_CONFIRMED | 0 |
| EXTERNAL_OUTPUT_ACCEPTANCE_UNKNOWN | 129 |

---

## A_INTERNAL 63건 고객 개방 가능 수

운영 DB GPT 확인 기준 (직접 집계 불가, GPT 수치 사용):

| 상태 | 건수 | 근거 |
|------|------|------|
| CUSTOMER_READY_CONFIRMED | 0 | 저장·복원·권한 직접 확인 불가 |
| CUSTOMER_BLOCKED | 27 | 미승인 증적 25건 + 미승인 일반 필드 2건 (별도) |
| CUSTOMER_NOT_VERIFIED | 36 | 저장/복원/PDF/권한 미확인 (증적 없는 38건 - 2건) |
| **합계** | **63** | |

상세:
- 미승인 증적 있는 문서: 25건, 미승인 증적 행: 35개
- 미승인 일반 입력 필드: 2건 (증적 없는 38건 내 포함)
- 등록된 증적 없는 문서: 38건 (증적 Gate 없음, 나머지 Gate 미확인)

**해석 주의:** A_INTERNAL 63건 = 분류 완료. 고객 개방 = 별도 Gate 조건 충족 필요.

---

## 공통 모듈 9개 명시적 정의 (R2_FINAL)

### M1. CATALOG — 문서 목록·상세 조회

**목적:** 260종 문서 목록 조회, 상세 정보 표시, 서식 진입점

| 항목 | 내용 |
|------|------|
| 코드 | `tai-admin: useDocumentFormsList.ts` |
| API | `GET /document-engine/form-schemas`, `GET /document-engine/form-schemas/{id}` |
| 제공 기능 | 카탈로그 검색·필터, 문서별 상태 표시 |
| 적용 문서 | 260건 (전체) |
| 구현 상태 | **IMPLEMENTED_VERIFIED** |
| 현재 Gate | 없음 |
| GAP | 없음 |
| 신규 구현 필요 | 없음 |

---

### M2. EDITOR — 필드 웹편집

**목적:** runtime_field 기준 동적 입력 UI, 필드 타입별 편집기

| 항목 | 내용 |
|------|------|
| 코드 | `tai-admin: useDocumentFormsEditor.ts` |
| API | `GET /document-engine/documents/{id}/runtime-fields`, `PATCH /document-engine/documents/{id}` |
| 제공 기능 | text/textarea/number/date/file/signature 필드 편집, 유효성 검증 |
| 적용 문서 | A_INTERNAL 63건 + D_ACCEPTED 확정 건 (현재 0건) |
| 구현 상태 | **IMPLEMENTED_VERIFIED** |
| 현재 Gate | G1 2건(CON-019, OSH-045): DB UPDATE + Owner 승인 필요 |
| GAP | 없음 (기능 구현 완료) |
| 신규 구현 필요 | 없음 |
| 개방 조건 | 각 문서 증적 Gate + G1 Gate 해제 |

---

### M3. SAVE_RESTORE — 저장·복원

**목적:** 작성 중 데이터 저장, 기존 작성본 복원

| 항목 | 내용 |
|------|------|
| 코드 | `tai-admin: useDocumentFormsGenerate.ts` + `useDocumentFormsRestore.ts` |
| API | `POST /document-engine/documents/{id}/save`, `GET /document-engine/documents/{id}/restore` |
| 제공 기능 | 자동저장, 수동저장, 버전별 복원 |
| 적용 문서 | EDITOR 적용 문서와 동일 |
| 구현 상태 | **IMPLEMENTED_VERIFIED** |
| 현재 Gate | EDITOR와 동일 |
| GAP | 없음 |
| 신규 구현 필요 | 없음 |

---

### M4. ATTACHMENT — 첨부파일

**목적:** 파일/이미지 필드 업로드, 저장된 파일 표시

| 항목 | 내용 |
|------|------|
| 코드 | `tai-admin: useDocumentFormsFileAttachment.ts` |
| API | `POST /document-engine/documents/{id}/file/{fieldKey}/upload` |
| 제공 기능 | 파일 업로드, per-field 업로드 상태, 에러 처리 |
| 적용 문서 | EDITOR 적용 문서 중 file/image 필드 포함 건 |
| 구현 상태 | **IMPLEMENTED_VERIFIED** |
| 현재 Gate | EDITOR와 동일 |
| GAP | 없음 |
| 신규 구현 필요 | 없음 |

---

### M5. SIGNATURE — 서명·증적

**목적:** 서명 필드 처리, 법정 증적 연결

| 항목 | 내용 |
|------|------|
| 코드 | `tai-admin: useDocumentFormsSignature.ts` |
| API | `POST /document-engine/documents/{id}/signature/{fieldKey}` |
| 제공 기능 | 서명 적용, 증적 상태 표시 |
| 적용 문서 | EDITOR 적용 문서 중 signature 필드 포함 건 |
| 구현 상태 | **IMPLEMENTED_VERIFIED** |
| 현재 Gate | 증적 CANDIDATE 해제 — 별도 Gate (이번 WO 범위 밖) |
| GAP | 없음 (기능 구현 완료) |
| 신규 구현 필요 | 없음 |
| 개방 조건 | 증적 Gate 해제 별도 결정 필요 |

---

### M6. OFFICIAL_DL — 공식 원본 다운로드/연결

**목적:** B_OFFICIAL 문서의 정부 공식서식 원본 파일 제공

| 항목 | 내용 |
|------|------|
| 코드 | `tai-api: routers/reference_forms.py` |
| API | `GET /reference-forms/{slug}`, `GET /reference-forms/{slug}/files/{file_id}/download` |
| 제공 기능 | TAI 참조서식 CMS 조회·다운로드 (승인 바인딩 포함) |
| 적용 문서 | B_OFFICIAL 16건 (ORIGINAL_ONLY) |
| 구현 상태 | **IMPLEMENTED_NOT_VERIFIED** |
| 주의 사항 | reference_forms.py = TAI 내부 CMS. 정부 공식서식(고용부/소방청 등) 직접 제공과 다름 — 출처·버전·파일 접근 계약 확인 필요 |
| 현재 Gate | 공식서식 버전·출처 계약 미확인, DOC-OSH-065 제품 범위 판단 보류 |
| GAP | 공식서식 연결 계약 확인 (B_OFFICIAL 16건 각각) — **NEW_IMPLEMENTATION_GAP_1** |
| 신규 구현 필요 | 조건부 — 기존 reference_forms.py 재사용 가능 여부 계약 확인 후 결정 |

---

### M7. PDF_GEN — HTML→PDF 출력

**목적:** 작성 완료 문서의 PDF 생성 및 다운로드

| 항목 | 내용 |
|------|------|
| 코드 | `tai-api: 문서엔진 렌더러` + `tai-admin: useDocumentLifecycle.ts` (`generateDocPdf`) |
| API | `POST /document-engine/documents/{id}/generate` |
| 제공 기능 | HTML 렌더링 → PDF 변환, 다운로드 |
| 적용 문서 | D_ACCEPTED 확정 건 (현재 0건) — D_ACCEPTED 확정 시 해당 전량 |
| 구현 상태 | **IMPLEMENTED_VERIFIED** |
| 현재 Gate | D_ACCEPTED 0건 — 기관 수리 확인 후 D_ACCEPTED 복귀 시 즉시 사용 가능 |
| GAP | 없음 (기능 구현 완료) |
| 신규 구현 필요 | 없음 |

---

### M8. PORTAL_LINK — 기관 포털 연결 안내

**목적:** C_PORTAL 문서에 대한 기관 포털 URL 안내 및 이동

| 항목 | 내용 |
|------|------|
| 코드 | `tai-admin: index.vue` (tabler-external-link 아이콘 UI 존재) |
| 제공 기능 | 기관 포털 외부 링크 표시 |
| 적용 문서 | C_PORTAL 확정 건 (현재 0건) |
| 구현 상태 | **PARTIALLY_IMPLEMENTED** (링크 표시 UI 존재, 포털 URL 데이터 계약 없음) |
| 현재 Gate | C_PORTAL 확정 건 없음 |
| GAP | C_PORTAL 확정 건 발생 시 포털 URL 데이터 연결 계약 — **NEW_IMPLEMENTATION_GAP_2** |
| 신규 구현 필요 | 조건부 — 링크 UI 재사용 가능, 포털별 URL 데이터 계약만 신규 |

---

### M9. RECEIPT_STORE — 외부 발급 문서 수령·보관

**목적:** E_EXTERNAL 문서(외부 기관·전문가 발급)의 수령 및 사내 보관

| 항목 | 내용 |
|------|------|
| 코드 | `tai-api: routers/documents.py` (`POST /upload`, `POST /upload-multiple`) |
| 제공 기능 | 범용 파일 업로드·보관 (인증·회사 범위 적용) |
| 적용 문서 | E_EXTERNAL 9건 (현재 모두 STOP) |
| 구현 상태 | **IMPLEMENTED_NOT_VERIFIED** (범용 업로드 존재, 외부발급 문서 전용 계약 없음) |
| 현재 Gate | E_EXTERNAL 전량 STOP — 신규 개발 불필요 |
| GAP | E_EXTERNAL STOP→KEEP 전환 시 범용 업로드와 외부발급 보관 계약 차이 확인 |
| 신규 구현 필요 | 없음 (현재 STOP) |

---

## GAP 최종 요약

| 구분 | 모듈 | 내용 |
|------|------|------|
| **NEW_IMPLEMENTATION_GAP_1** | OFFICIAL_DL | 공식서식 연결 계약 확인 — 기존 reference_forms.py 재사용 여부 결정 필요 |
| **NEW_IMPLEMENTATION_GAP_2** | PORTAL_LINK | C_PORTAL 확정 건 발생 시 포털 URL 데이터 계약 — 현재 해당 없음 |

나머지 7개 모듈 (CATALOG/EDITOR/SAVE_RESTORE/ATTACHMENT/SIGNATURE/PDF_GEN/RECEIPT_STORE)은 기존 구현 재사용 — 신규 구현 불필요.

---

## 작업 패키지 (R2_FINAL)

### WP-A: A_INTERNAL 63건 — 사업장 자체보관 그룹
- 기존 M2~M5 전량 재사용 (EDITOR+SAVE_RESTORE+ATTACHMENT+SIGNATURE)
- CUSTOMER_BLOCKED 27건: 증적 Gate 해제 별도 결정 필요
- CUSTOMER_NOT_VERIFIED 36건: 저장/복원/권한 확인 후 개방
- G1 2건(CON-019, OSH-045): DB UPDATE + Owner 승인 필요
- 신규 구현 없음

### WP-B: U_UNRESOLVED 129건 — 제출 경로 확인 그룹
- 팩스/이메일 전달 확인 38건 우선: 기관별 수리 정책 공개 자료 확인
  - 확인 후 D_ACCEPTED 복귀 → M7(PDF_GEN) 즉시 재사용
- 노동포털(labor.moel.go.kr) 22건: 서식 업로드 허용 여부 확인 → C_PORTAL 또는 D_ACCEPTED
- 조사 작업만 (코딩 없음) — 129건 개별 작업 금지, 기관·포털·출력형식 단위로 묶어 확인

### WP-C: B_OFFICIAL 16건 — 공식 원본 그룹
- NEW_IMPLEMENTATION_GAP_1 해소 필요 (OFFICIAL_DL 계약 확인)
- DOC-OSH-065 제품 범위 Owner 결정 후 15~16건 확정
- 신규 구현: 조건부 (reference_forms.py 재사용 여부 확인 후 결정)

---

## 작업 우선순위 (R2_FINAL)

1. **WP-A Gate 확인** — CUSTOMER_NOT_VERIFIED 36건 중 저장/복원/권한 충족 건 식별
2. **G1 DB 변경 + Owner 승인** — CON-019, OSH-045 (WP-A 내 2건)
3. **WP-B 조사** — 팩스/이메일 38건 기관 수리 정책 확인 (노동포털 22건 우선)
4. **WP-C 계약 확인** — OFFICIAL_DL 계약 확인 후 B_OFFICIAL 착수 여부 결정

---

## Owner 결정 필요 사항 (R2_FINAL)

| # | 항목 | 내용 |
|---|------|------|
| 1 | A_INTERNAL 증적 Gate 해제 | CUSTOMER_BLOCKED 27건 해제 기준 결정 |
| 2 | G1 DB 변경 | CON-019 + OSH-045 UPDATE + G1_APPROVED_FIELD_IDS |
| 3 | WP-B 조사 방법 | 기관 수리 정책 확인 범위 (공개 자료 vs 기관 문의) |
| 4 | B_OFFICIAL 계약 | OFFICIAL_DL 공식서식 연결 승인 |
| 5 | AGENCY_ONLY 3건 | DOC-OSH-065/066/067 제품 범위 포함 여부 |
| 6 | D_ACCEPTED 복귀 기준 | 기관 수리 확인 요건 결정 (공개 자료 충분 여부) |
