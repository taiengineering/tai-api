# RUNTIME_SCHEMA_SOURCE_TRACE_CENSUS

조사일: 2026-10-07
WO: WO-DOC-OBJ02-A-BINDING-READMODEL-DISCOVERY-001
DB: Supabase vwlahtguyggrhvslabax
실행자: Claude Code

---

## 전체 수치

| 항목 | 값 |
|---|---:|
| runtime_form_schema total | 324 |
| APPROVED_FOR_RUNTIME_USE | 1 |
| CANDIDATE | 323 |

---

## source_trace JSON key 전수 census

| key | non-null count | 비고 |
|---|---:|---|
| source_id | 324 | 전량 non-null |
| source_table | 324 | 전량 non-null |
| doc_id | 260 | document_forms 기원 전용 |
| form_code | 64 | document_form_master 기원 전용 |

doc_id와 form_code는 상호 배타적: doc_id가 non-null인 행은 form_code=null, form_code가 non-null인 행은 doc_id=null.

---

## source_table별 분포

| source_table | 건수 | doc_id non-null | form_code non-null |
|---|---:|---:|---:|
| document_forms | 260 | 260 | 0 |
| document_form_master | 64 | 0 | 64 |
| **합계** | **324** | **260** | **64** |

---

## doc_id distinct count

| 항목 | 값 |
|---|---:|
| doc_id non-null | 260 |
| doc_id distinct | 260 |
| doc_id 중복 | 0 |

1 doc_id → 1 schema 성립 (현재 데이터 기준). 중복 없음.

---

## form_code distinct count (document_form_master 기원)

| 항목 | 값 |
|---|---:|
| form_code non-null | 64 |
| form_code distinct | 64 (전수 추정 — 중복 source_identity 0건 확인) |
| source_id 중복 | 0 |

---

## source_table 조합 확인

doc_id와 form_code가 동시에 non-null인 행: **0** (상호 배타적 구조 확인됨)

---

## Approved Schema source_trace

| schema_id | doc_id | form_code | source_id | source_table |
|---|---|---|---|---|
| dc79ac3c-388c-42dc-b029-3dd9bda54a47 | null | GEN-INSPECT-RESULT-001 | 4236fb68-a620-4804-8951-7064ad908cd4 | document_form_master |

---

## 관측 사실

1. 324건 전량 source_id + source_table이 존재 — 기원 테이블 추적 가능.
2. 260건(document_forms)은 doc_id로 catalog에 직접 연결됨.
3. 64건(document_form_master)은 document_forms.doc_id와 직접 연결 경로 없음 (document_form_master에 doc_id 컬럼 없음).
4. 두 경로 간 교차 연결 FK: 현재 DB에 없음.

---

## MUTATION

application code = 0 / DB write = 0
