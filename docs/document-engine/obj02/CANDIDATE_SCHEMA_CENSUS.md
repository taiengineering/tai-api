# CANDIDATE_SCHEMA_CENSUS

조사일: 2026-10-07
WO: WO-DOC-OBJ02-A-BINDING-READMODEL-DISCOVERY-001
DB: Supabase vwlahtguyggrhvslabax
실행자: Claude Code

---

## 전체 모수

| status | 건수 |
|---|---:|
| CANDIDATE | 323 |
| APPROVED_FOR_RUNTIME_USE | 1 |
| **합계** | **324** |

---

## source_table별 분포 (CANDIDATE 323건)

| source_table | 건수 |
|---|---:|
| document_forms | 260 |
| document_form_master | 63 |
| **합계** | **323** |

(APPROVED 1건도 source_table = document_form_master)

---

## form_type별 분포 (CANDIDATE 323건)

| source_table | form_type | 건수 |
|---|---|---:|
| document_forms | OFFICIAL | 260 |
| document_form_master | CUSTOM | 31 |
| document_form_master | OFFICIAL | 24 |
| document_form_master | INTERNAL | 8 |
| **합계** | | **323** |

---

## document_family별 분포 (CANDIDATE 323건)

### document_forms 기원 (260건)

| document_family | 건수 |
|---|---:|
| 일상 | 98 |
| 정기 | 72 |
| 작업시 | 24 |
| 착공전 | 23 |
| 사고시 | 22 |
| 변경시 | 15 |
| 종료 | 4 |
| 감독대응 | 2 |
| **합계** | **260** |

### document_form_master 기원 (63건 CANDIDATE)

| document_family | form_type | 건수 |
|---|---|---:|
| UNRESOLVED | CUSTOM | 21 |
| UNRESOLVED | OFFICIAL | 15 |
| DOCUMENT | CUSTOM | 10 |
| 예시 | INTERNAL | 4 |
| 관리자선해임 | OFFICIAL | 3 |
| 재해보고 | OFFICIAL | 2 |
| 가이드 | INTERNAL | 1 |
| 허가신고 | OFFICIAL | 1 |
| 검사 | OFFICIAL | 1 |
| 안전계획 | OFFICIAL | 1 |
| 안전점검 | OFFICIAL | 1 |
| 위험성평가 | OFFICIAL | 1 |
| 교육 | OFFICIAL | 1 |
| 위원회 | OFFICIAL | 1 |
| **합계** | | **63** |

---

## Exact Evidence 수치 (CANDIDATE 323건)

| 증거 종류 | 건수 |
|---|---:|
| exact doc_id evidence (E1) | 260 |
| exact source_id resolvable (E2) | 63 (document_form_master PK 일치) |
| exact form_code evidence (E3) | 63 |
| no exact evidence | 0 |
| duplicate source identity | 0 |

---

## Human Review 단위 설계 모수

| 구분 | 건수 | 비고 |
|---|---:|---|
| catalog-bindable (doc_id 있음) | 260 | doc_id = document_forms.doc_id |
| form_master-only (doc_id 없음) | 63 | catalog 미연결 상태 |
| catalog 미반영 form_master schema | 63 | 별도 review 단위 필요 |

---

## MUTATION

application code = 0 / DB write = 0
