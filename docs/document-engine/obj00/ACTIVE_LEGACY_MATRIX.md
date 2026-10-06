# ACTIVE_LEGACY_MATRIX

조사일: 2026-10-07
대상: taiengineering/tai-api (main aa46bbb7)
분류 기준: 명시적 증거만 사용 (추정 금지)

---

## 분류 vocabulary

| 분류 | 정의 |
|---|---|
| ACTIVE_MOUNTED | router_registry에 등록 + main에서 로드됨 |
| ACTIVE_NOT_CONSUMED | 코드 존재, 미탑재이나 active service chain이 import함 |
| LEGACY | unmounted + 명시적 증거 (archive 위치/주석/replacement/미탑재/active consumer 없음) |
| ARCHIVED | _archive/ 폴더 또는 명시적 archived |
| UNKNOWN | 증거 불충분 |

---

## 라우터 분류

| 라우터 파일 | prefix | 마운트 | 분류 | 근거 |
|---|---|---|---|---|
| routers/document_forms.py | /document-forms | YES | ACTIVE_MOUNTED | router_registry/document_engine.py 등록 |
| routers/document_engine.py | /document-forms | YES | ACTIVE_MOUNTED | router_registry/document_engine.py 등록 (TBM 생성 경로) |
| routers/document_engine_api.py | /document-engine | YES | ACTIVE_MOUNTED | router_registry/document_engine.py 등록 |
| routers/engine_document.py | /engine/forms | YES | ACTIVE_MOUNTED | router_registry/document_engine.py 등록 |
| routers/document_monitoring.py | /document-monitoring | YES | ACTIVE_MOUNTED | router_registry/document_engine.py 등록 |
| routers/compliance_report.py | /compliance-report | YES | ACTIVE_MOUNTED | router_registry/document_engine.py 등록 |
| routers/document_generate.py | /documents/{doc_type} | YES | ACTIVE_MOUNTED | router_registry/document_engine.py 등록 |
| routers/documents.py | /documents | NO | LEGACY | 미탑재 + active consumer 없음 + 테스트 없음. last commit: `03e13509 fix(documents): 문서 API에 인증·회사 스코프를 붙인다` |
| routers/document_runtime.py | /document-runtime | NO | LEGACY | 미탑재 + active consumer 없음 + 테스트 없음. last commit: `b29b5411 feat: Runtime Data Binding Engine — PHASE A~I 구현` |
| routers/document_schema.py | /document-schema | NO | LEGACY | 미탑재 + active consumer 없음. test는 service(renderer)만 테스트하고 router 미테스트. last commit: `bf487e3d feat: Document Schema Layer` |

---

## 서비스 분류

| 서비스 파일 | 분류 | 근거 |
|---|---|---|
| services/document_engine_svc.py | ACTIVE_MOUNTED | routers/document_engine_api.py(MOUNTED)에서 import |
| services/document_engine/renderer.py | ACTIVE_MOUNTED | routers/document_engine.py + routers/compliance_report.py + services/document_engine/generator.py |
| services/document_engine/generator.py | ACTIVE_MOUNTED | routers/document_generate.py(MOUNTED)에서 import |
| services/document_svc.py | ACTIVE_MOUNTED | routers/document_engine.py + 다수 mounted router에서 import |
| services/document_forms_service.py | ACTIVE_MOUNTED | routers/document_forms.py(MOUNTED)에서 import |
| services/document_schema_renderer.py | ACTIVE_MOUNTED | services/document_confirm_svc.py → routers/document_engine_api.py chain |
| services/document_confirm_svc.py | ACTIVE_MOUNTED | routers/document_engine_api.py(MOUNTED) status route에서 import |
| services/document_snapshot_integrity.py | ACTIVE_NOT_CONSUMED | services/document_confirm_svc.py에서 import (active chain의 일부). 직접 router는 없음 |
| services/runtime_document_context.py | LEGACY | grep 결과 어느 파일에서도 import 없음 (codebase 전체 검색) |

---

## Fetcher 분류

| 파일 | 분류 |
|---|---|
| services/document_engine/fetchers/base_fetcher.py | ACTIVE_MOUNTED |
| services/document_engine/fetchers/inspection_fetcher.py | ACTIVE_MOUNTED |
| services/document_engine/fetchers/tbm_fetcher.py | ACTIVE_MOUNTED |

---

## LEGACY로 분류된 파일 요약

| 파일 | LEGACY 선언 근거 |
|---|---|
| routers/documents.py | (1) 미탑재 (2) active consumer 없음 (3) 테스트 없음 |
| routers/document_runtime.py | (1) 미탑재 (2) active consumer 없음 (3) 테스트 없음 |
| routers/document_schema.py | (1) 미탑재 (2) active consumer 없음 (3) 라우터 직접 테스트 없음 |
| services/runtime_document_context.py | (1) codebase 전체에서 import 없음 |
