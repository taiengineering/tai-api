# SCHEMA_BINDING_FEASIBILITY

조사일: 2026-10-07
WO: WO-DOC-OBJ02-A-BINDING-READMODEL-DISCOVERY-001
Source: 현재 DB 제약 + 소스 코드 근거만 사용
실행자: Claude Code

---

## 현재 제약 구조 사실

### document_type_mapping

| 제약 | 컬럼 | 상세 |
|---|---|---|
| PRIMARY KEY | id | uuid |
| UNIQUE | doc_id | 1 mapping row per catalog doc |
| FK (inbound) | 없음 | 다른 테이블에서 이 테이블 참조 없음 |
| FK (outbound) | 없음 | document_forms, runtime_form_schema 참조 없음 |

### runtime_form_schema

| 제약 | 컬럼 | 상세 |
|---|---|---|
| PRIMARY KEY | id | uuid |
| FK | schema_candidate_id → document_schema_candidate.id | candidate 테이블 참조 |
| UNIQUE | 없음 | doc_id uniqueness는 source_trace JSON 내에서만 (DB 제약 없음) |

### 현재 데이터 cardinality

| 항목 | 값 |
|---|---|
| 1 doc_id → 1 schema 성립 여부 | YES (현재 데이터 기준 중복 없음) |
| DB 제약으로 강제 여부 | NO (JSON 컬럼, 제약 없음) |

---

## 방안 A — document_type_mapping에 runtime_form_schema_id 추가

### Required DDL

```sql
ALTER TABLE document_type_mapping
  ADD COLUMN runtime_form_schema_id UUID
  REFERENCES runtime_form_schema(id);
```

### Current-source impact

| 항목 | 값 |
|---|---|
| 영향 rows | document_type_mapping 30행 |
| 초기 채워야 할 값 | 30건 중 source_trace.doc_id로 schema 역조회 가능 (30건 전부 catalog-bound) |
| 미커버 catalog | 230건은 여전히 binding 없음 |
| consumer 영향 | document_type_mapping Python consumer = 0 → 영향 없음 |

### Cardinality support

- doc_id UNIQUE 제약으로 1 doc → 1 mapping row 보장됨
- 1 mapping row당 1 schema_id → 1:1 강제 가능
- version upgrade: FK pointer UPDATE 필요. 이전 version 참조 소실.

### Migration risk

LOW DDL (nullable column 추가). 그러나:
- 230건 catalog 여전히 미결 (30건만 coverage)
- schema version 변경 시 pointer 재업데이트 필요
- FK 추가 후 document_type_mapping 미사용 Python code 상태 변화 없음

---

## 방안 B — 별도 binding table

### Required DDL

```sql
CREATE TABLE document_schema_binding (
  doc_id TEXT NOT NULL REFERENCES document_forms(doc_id),
  schema_id UUID NOT NULL REFERENCES runtime_form_schema(id),
  schema_version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (doc_id)
);
```

### Current-source impact

| 항목 | 값 |
|---|---|
| 초기 INSERT 필요 | 260건 (source_trace.doc_id 있는 schema 전량) |
| FK to document_forms | 필요 (doc_id TEXT FK) |
| form_master-only schema 64건 | 이 테이블로 binding 불가 (doc_id 없음) |
| consumer 영향 | 새 테이블 — 기존 코드 영향 없음 |

### Cardinality support

- PRIMARY KEY(doc_id) → 1:1 DB 제약 강제
- schema version upgrade = UPDATE (이전 binding 덮어쓰기)
- multi-version 지원 필요 시 PRIMARY KEY(doc_id, schema_version) 변경 필요

### Migration risk

MEDIUM:
- 새 테이블 생성 DDL 필요
- 260건 초기 INSERT 필요
- rollback: DROP TABLE (안전)
- form_master-only 64건은 여전히 미결

---

## 방안 C — runtime_form_schema.source_trace만 사용

### Required DDL

없음. 현재 데이터로 바로 사용 가능.

### Current-source impact

| 항목 | 값 |
|---|---|
| 변경 필요 | 없음 |
| 조회 방식 | SELECT id FROM runtime_form_schema WHERE source_trace->>'doc_id' = $1 |
| 260건 | doc_id로 즉시 조회 가능 |
| 64건 | form_code 경유, catalog 미연결 |

### Cardinality support

- 1:1 현재 성립하나 DB 제약 없음 → 중복 삽입 방지 불가
- version 관리: status 컬럼(CANDIDATE/APPROVED) 필터로 구현 가능

### Migration risk

NONE. 기존 데이터 사용. 단:
- source_trace JSON 쿼리는 인덱스 없으면 FULL SCAN
- doc_id uniqueness 미강제 → 중복 위험 (현재 0건, 향후 보장 없음)

---

## 비교 요약 (사실 기반, 추천 없음)

| 항목 | A (mapping-column) | B (binding-table) | C (source-trace-only) |
|---|---|---|---|
| Required DDL | ALTER TABLE 1 | CREATE TABLE 1 + 260 INSERT | 없음 |
| catalog coverage | 30/260 | 260/260 | 260/260 (doc_id 경로) |
| form_master-only binding | 미결 (30건 추가 가능) | 미결 (64건 doc_id 없음) | 미결 (64건 doc_id 없음) |
| Cardinality enforcement | UNIQUE(doc_id) 기존 활용 | PRIMARY KEY 신규 | 없음 |
| Migration risk | LOW | MEDIUM | NONE |
| Version upgrade | pointer UPDATE | pointer UPDATE | status 필터 |
| Rollback | nullable column DROP | DROP TABLE | N/A |

**NO RECOMMENDATION MADE**

---

## MUTATION

application code = 0 / DB write = 0
