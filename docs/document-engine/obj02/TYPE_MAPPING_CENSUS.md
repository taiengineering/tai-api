# TYPE_MAPPING_CENSUS

조사일: 2026-10-07
WO: WO-DOC-OBJ02-A-BINDING-READMODEL-DISCOVERY-001
DB: Supabase vwlahtguyggrhvslabax
실행자: Claude Code

---

## 전체 수치

| 항목 | 값 |
|---|---:|
| catalog total | 260 |
| mapping rows | 30 |
| mapped catalog | 30 |
| unmapped catalog | 230 |
| orphan mappings | 0 |
| coverage | 11.5% (30/260) |

---

## doc_type별 mapping 수

| doc_type | 건수 |
|---|---:|
| EQUIP | 15 |
| INSP | 4 |
| EDU | 3 |
| CHK | 2 |
| TBM | 2 |
| APPT | 2 |
| CONLOG | 1 |
| PPE | 1 |
| **합계** | **30** |

---

## doc_detail 분포 (EQUIP 전용)

| doc_detail | 건수 |
|---|---:|
| (NULL — non-EQUIP) | 16 |
| SCAFFOLD | 2 |
| MACHINE | 2 |
| HAZMAT | 2 |
| FIRE | 1 |
| ELEC | 1 |
| ELEV | 1 |
| ASBESTOS | 1 |
| CRANE | 1 |
| GUARD | 1 |
| GAS | 1 |
| BOILER | 1 |
| REFRIG | 1 |

---

## 분류 기준

- **MAPPED_EXISTING_CATALOG**: document_type_mapping.doc_id ∈ document_forms.doc_id (30건)
- **CATALOG_UNMAPPED**: document_forms.doc_id ∉ document_type_mapping.doc_id (230건)
- **MAPPING_ORPHAN**: document_type_mapping.doc_id ∉ document_forms.doc_id (0건)

---

## 제약 구조 (현재 DB)

| 제약 | 컬럼 | 상세 |
|---|---|---|
| PRIMARY KEY | id | uuid |
| UNIQUE | doc_id | 1 mapping row per doc |
| FK → document_forms | 없음 | 참조 무결성 미강제 |
| FK → runtime_form_schema | 없음 | schema 포인터 없음 |

---

## Python 소비자

document_type_mapping을 읽거나 쓰는 Python service/router: **없음** (codebase 전수 검색 결과)

삽입 경로: 2026-08-22 단일 배치 SQL 삽입. 이후 UPDATE 없음 (created_at = updated_at 동일).

---

## MUTATION

application code = 0 / DB write = 0
