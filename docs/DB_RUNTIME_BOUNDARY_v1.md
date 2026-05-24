# DB_RUNTIME_BOUNDARY_v1 — Logical Ownership Boundary

> Date: 2026-05-24
> Phase: 2 — Logical Boundary Separation ONLY
> Status: Design document. No migration executed. No schema changed.

---

## ⛔ MIGRATION PROHIBITION NOTICE

이 문서는 **논리적 분리 설계**이다.
실제 schema 이동, table rename, FK 변경 등은 **수행되지 않았으며 수행해서는 안 된다.**

현재 모든 테이블은 `public` schema에 존재하며,
이 문서는 **향후 분리를 위한 boundary 설계**일 뿐이다.

---

## Inventory Summary

| DB | Tables | Non-empty | Empty |
|---|---|---|---|
| taieng (main) | 550 | 329 | 221 |
| 45cm-ops-db | 16 | 10 | 6 |
| 45cm-prj-db | 2 | 0 | 2 |
| **Total** | **568** | **339** | **229** |

---

# PART 1 — Runtime Schema Candidate (~262 tables)

## 1A. Core Runtime (6 confirmed canonical)

| table | readers | writers | runtime critical |
|---|---|---|---|
| master_building_legal_rules | legal_runtime.py | law_db_insert.py, law_to_rules.py | YES |
| facility_applicability (+detail) | diagnosis_service.py, compiler_core.py | run_facility_applicability.py | YES |
| task_candidate (+relation) | diagnosis_service.py, runtime_evaluator_svc.py | run_task_candidate.py, compiler_core.py | YES |
| schedule_candidate | diagnosis_service.py | run_schedule_candidate.py | YES |
| penalty_obligation_relation (+candidate, numeric, reference_link) | diagnosis_service.py | run_penalty_candidate.py, compiler_core.py | YES |
| compliance_review_queue (+package) | diagnosis_service.py | run_compliance_package.py, compiler_core.py | YES |

## 1B. Runtime Infrastructure (98 runtime_* tables)

Key tables with data:

| table | rows | function |
|---|---|---|
| runtime_compliance_evidence | 50,301 | 준수 증거 |
| runtime_operational_work_order | 20,129 | 작업지시 |
| runtime_notification_event | 30,500 | 알림 이벤트 |
| runtime_review_decision | 5,101 | 검토 결정 |
| runtime_metadata_resolution | 3,395 | 메타데이터 해석 |
| runtime_assignment_requirement | 1,724 | 할당 요건 |
| runtime_field | 1,303 | 필드 정의 |
| runtime_escalation_queue | 933 | 에스컬레이션 |
| runtime_checklist_item | 802 | 체크리스트 |
| runtime_task/schedule/instance | 339 each | 실행 인스턴스 |

~40개 empty runtime_* tables = 향후 기능 예비 (RESERVED).

## 1C. Legal Corpus (31 law_* tables)

법령 데이터. Source-of-truth.

| table | rows |
|---|---|
| law_article_part | 143,544 |
| law_item | 65,426 |
| law_paragraph | 50,180 |
| law_article | 35,412 |
| law_article_inheritance | 15,850 |
| dict_legal_terms | 14,942 |
| 기타 25개 | varies |

## 1D. Master/Reference (52 tables)

process_equipment_map (187K), equipment_model_master (2.8K), kosha_safety_materials (30K) 등.

## 1E. Product/SaaS (40 tables)

payments, subscriptions, price_*, connect_*, fix_*, matching_*, diagnosis_* 등.

## 1F. Registry/Config (41 tables)

alert_rule_registry, flow_*, workflow_*, notification_*_registry, monitoring_config 등.

---

# PART 2 — Extraction Schema Candidate (~79 tables, ~2.4M rows)

> Extraction lineage must be preserved.
> Not temporary data.

## 2A. Stage Pipeline (6)

stage_1_clauses, stage_2_elements, stage_3_objects, semantic_clause* (all 0 rows)

## 2B. Candidate/Graph (26)

rule_candidate (34K), rule_candidate_slot (146K), rule_candidate_relation (59K), *_candidate tables

## 2C. Evidence Pipeline (8)

evidence_candidate (275K), evidence_normalized (283K), evidence_token (237K), evidence_validation (144K)

## 2D. Constraint/Family/Numeric (7)

constraint_node (284K), constraint_edge (54K), family_relation (16K), numeric_* (4 tables)

## 2E. Residual Pipeline (9)

residual_candidate (111K), residuals (111K), residual_failed_reasons (111K)

## 2F. Draft/Executable (4)

draft_slot (50K), draft_condition_graph (10K), executable_draft (10K)

## 2G. Mapping/Compatibility (14)

form_mapping_candidate (68K), compatibility_validation (59K), appendix_runtime_metadata (31K), admrule_kr_mapping_raw (21K)

## 2H. Rule Classification (5)

rule_classify_subtype (35), rule_clause_split (11), rule_classify_if_pattern (8)

---

# PART 3 — Historical/Audit (~35 tables)

> Historical tables are preserved for traceability.

cron_job_log (32K), business_event (18K), track_issue_log (8K), engine_integrity_event (2K), verification_log (1.6K), mail_logs (740) 등.

---

# PART 4 — Legacy/Contaminated (5 tables, FROZEN)

| table | rows |
|---|---|
| master_building_legal_rules_legacy_contaminated | 2,002 |
| master_legal_rules_pending_review_legacy_contaminated | 1,454 |
| master_legal_rules_preserved_legacy_contaminated | 321 |
| law_parsing_result_legacy_contaminated | 469 |
| inspection_master_v1_backup | 150 |

FROZEN. Archive 이동은 인간 승인 후에만.

---

# PART 5 — Quarantine (97 empty tables)

> ownership 미확정 상태. 삭제 후보가 아님.

주요 그룹:
- construction_* (5): 건설 기능 미구현
- import_* (7): 임포트 파이프라인 미구현  
- education_* (4): 교육 기능 미구현
- operational_* (5): 운영 기능 미구현
- notification_* (4 empty): 알림 기능 일부
- safety_* (3 empty): 안전 기능 일부
- rule_* (5 empty): 규칙 파이프라인 일부
- 기타 64개: 개별 기능 미구현

미배치 non-empty 37개도 boundary 배치 확인 필요.

---

# PART 6 — Forbidden Migration Boundary

Forbidden without explicit human approval:

- ❌ DROP TABLE
- ❌ TRUNCATE
- ❌ DELETE
- ❌ ALTER TABLE
- ❌ Schema relocation
- ❌ FK rewiring
- ❌ Runtime table rename
- ❌ Extraction lineage deletion
- ❌ Audit log deletion
- ❌ Index/RLS modification
- ❌ Migration execution
- ❌ Backup overwrite

---

# PART 7 — Future Schema Direction (참고, 미실행)

```
public (현재 전체)
  ├── runtime.*     — 런타임 실행 (~262)
  ├── extraction.*  — 추출 파이프라인 (~79)
  ├── audit.*       — 감사/이력 (~35)
  ├── archive.*     — 레거시 (5)
  └── quarantine.*  — 미분류 (97+37)
```

이것은 설계 참고사항이다. 실행하지 않았고, 실행해서는 안 된다.
