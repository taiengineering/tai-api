# DOCUMENT_LIBRARY_STORAGE_EVIDENCE

조사일: 2026-10-07
DB: Supabase vwlahtguyggrhvslabax

---

## documents 테이블 현황

| 항목 | 값 |
|---|---|
| 총 건수 | 4 |
| 카테고리 종류 | general (전체) |
| source 종류 | AUTO_GENERATED (전체) |
| generated_by 종류 | member_quote_pdf_v1 (전체) |
| 문서 모듈 관련 건수 | 0 |

### 4건 상세

| 파일명 | file_size | mime_type | bucket_id | uploaded_at |
|---|---:|---|---|---|
| TAI_견적서_QT-20260906-1C1B5A0B.pdf | 200,105 bytes | application/pdf | company-docs | 2026-09-06 |
| TAI_견적서_QT-20260906-DA1A0D61.pdf | 200,231 bytes | application/pdf | company-docs | 2026-09-06 |
| TAI_견적서_QT-20260907-0EA909A2.pdf | 193,894 bytes | application/pdf | company-docs | 2026-09-07 |
| TAI_견적서_QT-20260930-1B0C35F7.pdf | 196,304 bytes | application/pdf | company-docs | 2026-09-30 |

모두 견적서 PDF. 문서 모듈 생성 결과물 없음.

---

## Storage 버킷

### company-docs
- 용도: documents 테이블 linked 파일 저장
- 실제 사용: member_quote_pdf_v1 생성 견적서 4건
- path convention: UNVERIFIED (Storage API 미호출)
- public: **false (PRIVATE)** — GPT 독립검증 2026-10-07
- object_count: **5** — GPT 독립검증 2026-10-07
- signed URL 방식: services/document_svc.py `create_signed_url()` 사용

### form-outputs
- 용도: generated_document 테이블의 bucket_id default값
- public: **true (PUBLIC)** — GPT 독립검증 2026-10-07
- object_count: **0** — GPT 독립검증 2026-10-07
- generated_document에서 storage_path=NULL 이므로 실제 upload 기록 없음

---

## Generated Document Storage 실증 (CORR-C)

GPT 독립검증 2026-10-07 확인.

| 항목 | 값 |
|---|---|
| generated_document total | 1,544 |
| storage_path NOT NULL | 0 |
| storage_path NULL | 1,544 |
| status=GENERATED | 9 |
| GENERATED + storage_path NOT NULL | 0 |
| GENERATED + storage_path NULL | 9 |

**사실**: GENERATED 상태로 기록된 9건조차 실제 storage object 연결이 없음. `status=GENERATED`는 현재 파일 존재를 보장하지 않음.

---

## signed URL 생성 경로

`services/document_svc.py`:
- `create_signed_url(bucket: str, path: str, expires_in: int = 3600)` → Supabase Storage API
- 실제 호출 경로: routers/document_engine.py TBM generate → document_svc.register_generated → documents 테이블 INSERT

---

## Download API 상태

| 경로 | 라우터 | 마운트 여부 |
|---|---|---|
| GET /documents/{doc_id}/download | routers/documents.py | NOT MOUNTED |
| GET /engine/forms/{form_code}/download | routers/engine_document.py | 엔드포인트 미존재 (404) |

문서 직접 다운로드 API: **현재 미탑재 또는 미구현**
