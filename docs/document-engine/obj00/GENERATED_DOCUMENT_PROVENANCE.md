# GENERATED_DOCUMENT_PROVENANCE

조사일: 2026-10-07
DB: Supabase vwlahtguyggrhvslabax
조사방법: SELECT (READ ONLY) via MCP execute_sql

---

## 전체 현황

| status | 건수 | 기대값 (master plan) | 일치 |
|---|---:|---:|---|
| GENERATED | 9 | 9 | YES |
| PENDING | 1,527 | 1,527 | YES |
| FAILED | 4 | 4 | YES |
| TEMPLATE_MISSING | 4 | 4 | YES |
| **합계** | **1,544** | **1,544** | YES |

---

## 날짜 범위

| status | 건수 | earliest | latest |
|---|---:|---|---|
| GENERATED | 9 | 2026-05-14 | 2026-05-16 |
| PENDING | 1,527 | 2026-05-16 | 2026-08-23 |
| FAILED | 4 | 2026-05-16 | 2026-05-16 |
| TEMPLATE_MISSING | 4 | 2026-05-16 | 2026-05-16 |

---

## export_type 분포

| export_type | 건수 |
|---|---:|
| PDF | 1,543 |
| HTML | 1 |

---

## storage 참조 현황 (1,544건 전체)

| 항목 | not null 건수 |
|---|---:|
| storage_path | 0 |
| download_url | 0 |
| failure_reason | 0 |
| runtime_document_id | 2 |
| form_schema_id | 2 |
| tenant_id | 1,542 |
| factory_id | 0 |

**결론**: 실제 파일이 storage에 존재하는 row가 없음. GENERATED 9건도 storage_path/download_url = NULL.

---

## tenant 분포

| tenant_id | status | 건수 |
|---|---|---:|
| anonymous | PENDING | 1,521 |
| mock_doc_01 | GENERATED | 2 |
| mock_doc_01 | PENDING | 1 |
| mock_doc_01 | FAILED | 1 |
| mock_doc_01 | TEMPLATE_MISSING | 1 |
| mock_large_01 | GENERATED | 2 |
| mock_large_01 | PENDING | 1 |
| mock_large_01 | FAILED | 1 |
| mock_large_01 | TEMPLATE_MISSING | 1 |
| mock_large_02 | GENERATED | 2 |
| mock_large_02 | PENDING | 1 |
| mock_large_02 | FAILED | 1 |
| mock_large_02 | TEMPLATE_MISSING | 1 |
| mock_stable_01 | GENERATED | 2 |
| mock_stable_01 | PENDING | 1 |
| mock_stable_01 | FAILED | 1 |
| mock_stable_01 | TEMPLATE_MISSING | 1 |
| tai | PENDING | 1 |
| NULL | GENERATED | 1 |
| NULL | PENDING | 1 |

---

## GENERATED 9건 상세

| id (앞8자) | form_code | document_name | tenant_id | runtime_doc | form_schema | created_at |
|---|---|---|---|---|---|---|
| 8f533c39 | NULL | NULL | NULL | 61055825 (존재) | 74cf8ca2 (존재) | 2026-05-14 |
| 2d308882 | STD-RISK-001 | 위험성평가 결과서 | mock_large_01 | NULL | NULL | 2026-05-16 |
| 39586092 | STD-INSPECT-001 | 안전점검 결과서 | mock_stable_01 | NULL | NULL | 2026-05-16 |
| 5b43a637 | BW-HIGH-001 | 고소작업 점검표 | mock_stable_01 | NULL | NULL | 2026-05-16 |
| cf4b49b8 | STD-RISK-001 | 위험성평가 결과서 | mock_doc_01 | NULL | NULL | 2026-05-16 |
| 31f2102d | STD-INSPECT-001 | 안전점검 결과서 | mock_doc_01 | NULL | NULL | 2026-05-16 |
| 7a1212dc | BW-HIGH-001 | 고소작업 점검표 | mock_large_02 | NULL | NULL | 2026-05-16 |
| fd35d13e | STD-RISK-001 | 위험성평가 결과서 | mock_large_02 | NULL | NULL | 2026-05-16 |
| be773765 | STD-INSPECT-001 | 안전점검 결과서 | mock_large_01 | NULL | NULL | 2026-05-16 |

모든 GENERATED 건: storage_path=NULL, download_url=NULL. 실제 파일 object 존재 여부 UNVERIFIED (Storage API 미호출).

---

## 1,521건 PENDING (anonymous) 특징

- tenant_id = `anonymous`
- runtime_document_id = NULL
- form_schema_id = NULL
- factory_id = NULL
- failure_reason = NULL

### PENDING Provenance (CORR-F)

```
current runtime generate code:
  POST /document-engine/documents/{doc_id}/generate
  → services/document_engine_svc.generate_document()
  → generated_document INSERT (status=PENDING) 확인
  → runtime_document_id를 body에서 받아 INSERT

historical 1,527 PENDING rows:
  → 동일 경로에서 생성됐다는 증거 NONE
  → runtime_document_id NULL = 현재 코드와 다른 INSERT 경로 가능성
  → 삽입 코드 codebase 전체 검색에서 미발견

PENDING_PROVENANCE = UNRESOLVED

판단 금지: 과거 row의 원인을 현재 코드만 보고 단정하지 않음.
```

---

## 생성 호출 경로 요약

| 경로 | storage write | PDF bytes | generated_document INSERT |
|---|---|---|---|
| `POST /document-engine/documents/{doc_id}/generate` | NO | NO | YES (PENDING) |
| `POST /documents/{doc_type}/generate` | NO | YES (StreamingResponse) | NO |
| `POST /document-forms/{doc_id}/generate` (TBM) | YES (documents 테이블) | YES (bytes) | NO |

**PENDING 1,527건 대부분**: `POST /document-engine/documents/{doc_id}/generate` 경로로 생성 후 실제 render/upload 단계가 구현되지 않아 PENDING 상태로 누적.
