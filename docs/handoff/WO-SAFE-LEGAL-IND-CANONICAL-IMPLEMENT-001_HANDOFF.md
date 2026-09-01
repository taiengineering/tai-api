# WO-SAFE-LEGAL-IND-CANONICAL-IMPLEMENT-001 — SESSION HANDOFF

작성: 2026-09-01 · 브랜치 `wo-safe-legal-ind-implement-001` · HEAD `faeb74f5`
역할: Claude=executor/evidence, GPT=design/verify, 운영자(Taiwang)=실행권한. 본 문서는 evidence 기록.

---

## 0. 한 줄 요약
INDUSTRIAL 법령진단을 위해 **별도 진단 저장모델을 만들지 않고**, 기존 SaaS canonical 자산
(factories / factory_process / equipment_assets / factory_materials)을 확장·결선하고,
그 자산을 Marketing 29-field transport로 조립한 뒤 **기존 LEG Runtime 호출 지점**에 전달하는
코드까지 완성(READ→transport→handoff). DB APPLY/MERGE/DEPLOY는 미실행(운영자 권한).

```
SaaS canonical assets → 29-field transport → LEG facility → evaluate_rtm()  = COMPLETE (code)
```

---

## 1. STEP 상태 (GPT 독립검증 기준)
| STEP | 내용 | 상태 |
|---|---|---|
| STEP1 | canonical migration(factories +9 / factory_process +3 / equipment_assets +2 / NEW factory_materials); 구 profile 설계 폐기 | CLOSED |
| STEP2 | 폐기 profile artifact 제거(router/service/test 삭제 + registry 정리) | CLOSED |
| STEP3A | factories 확장(작업형태·환경 7 + completion_year/구조원천 결선, strict, sparse PATCH) | CLOSED |
| STEP3B | canonical vocabulary(system_codes 4 category/15 item DML artifact + Factory vocab 검증) | CLOSED |
| STEP4 | factory_process 확장(hazard_codes/worker_count/activity_types + auth/ownership) | CLOSED |
| STEP5 | equipment_assets 확장(usage_types/relation_types) | CLOSED |
| STEP6 (+PATCH-1) | factory_materials CRUD 신규(identity gate + DELETE result contract) | CLOSED |
| STEP7 (+PATCH-1) | canonical→Marketing 29 assembler(READ-only; building_qualifications/regulated_facility_types 항상 UNRESOLVED) | CLOSED |
| STEP8 | LEG handoff(기존 leg_runtime_client.build_facility + evaluate_rtm 재사용) | CLOSED |

---

## 2. commit lineage (main baseline b7cbf3bb → )
```
… (R2/legacy) … → 1e381b7f STEP1 canonical migration
  → f0c3512e/061b4c06/7965b9bb/97a54b84   STEP2 registry+3 deletes
  → d76c46ad/45796d29                       STEP3A (tests, factories.py)
  → 7b215bac/4ee9cb92/939773e2              STEP3B (vocab DML+svc+test, factories, step3a test)
  → 87031933/dadfe4aa                        STEP4 (factory_process_v3, test)
  → 8aea3d2e/eea7c7c7                        STEP5 (equipment_assets, test)
  → 2c8e16a7/932f99ea/e6d6214c              STEP6 (registry, factory_materials, test)
  → 549becc0/0ec20159                        STEP6-PATCH-1 (DELETE contract, test)
  → aa048a7d                                  STEP7 (assembler + test)
  → 8634cbcf/6bdbbd0d                        STEP7-PATCH-1 (assembler, test)
  → faeb74f5                                  STEP8 (handoff + test)   ← HEAD
```

## 3. 산출 파일 (HEAD blob)
```
docs/sql/20260901_safe_ind_legal_diagnosis_profile_up.sql     55fed3c5   (STEP1 UP: 캐노니컬 확장 migration)
docs/sql/20260901_safe_ind_legal_diagnosis_profile_down.sql   109ff7db   (STEP1 DOWN)
docs/sql/20260901_safe_ind_canonical_vocab_up.sql             f33a15fb   (STEP3B vocab DML UP, 4 cat/15 item)
docs/sql/20260901_safe_ind_canonical_vocab_down.sql           b688359b   (STEP3B vocab DML DOWN)
router_registry/saas_core.py                                  5b9d8b05   (factory_materials 등록; 구 profile 미등록)
routers/factories.py                                          7167aecd   (STEP3A/3B)
routers/factory_process_v3.py                                 7c22146c   (STEP4)
routers/equipment_assets.py                                   b7db7fb1   (STEP5, v1.8.0)
routers/factory_materials.py                                  8877d3ba   (STEP6+PATCH-1, v1.0.1)
services/factory_canonical_vocab_svc.py                       14742fb5   (STEP3B vocab 검증, system_codes SoT)
services/safe_industrial_canonical_assembler.py              ce8fc7cb   (STEP7+PATCH-1, 29 assembler)
services/safe_industrial_leg_handoff.py                       61d72b20   (STEP8 handoff)
tests/test_factory_canonical_step3a.py                        68d52d67
tests/test_factory_canonical_step3b.py                        0a69aef0
tests/test_factory_process_canonical_step4.py                 e90943f9
tests/test_equipment_canonical_step5.py                       20d5163c
tests/test_factory_materials_canonical_step6.py               5726677c
tests/test_safe_industrial_canonical_assembler.py            dea7f1e8
tests/test_safe_industrial_leg_handoff.py                     83ba3d55
삭제: routers/factory_legal_diagnosis.py · services/safe_industrial_legal_profile_svc.py · tests/test_safe_industrial_legal_profile.py (STEP2)
```

## 4. canonical → Marketing 29 매핑 요지 (STEP7)
- EXISTING/DIRECT+TRANSFORM(factories): address, ksic_major, worker_count(=employee_count, calc 금지),
  total_floor_area(=building_area), floor_count, basement_count(=underground_floor_count),
  built_year(=completion_year), has_safety_manager, electric_capacity(=electrical_capacity_kw),
  has_boiler, has_chemical_substance, has_high_pressure_gas, gas_capacity_kg, elevator_count,
  annual_energy_toe, work_height_m, has_truck_loading_unloading, truck_loading_height_m,
  has_manual_heavy_handling, manual_handling_weight_kg
- DERIVED/UNRESOLVED(정규화 매핑 미확정 — no-invention): building_use_type, main_structure
- DIRECT VOCAB(system_codes code→code_name; unknown→unresolved): business_activity_types, hazardous_work_environments
- 항상 UNRESOLVED(부분-direct false completeness 금지): building_qualifications, regulated_facility_types
- COMPOSITE(active-only, 정확표현 불가 시 field NULL+unresolved): material_profile(factory_materials),
  process_list(factory_process), equipment_list(equipment_assets)
- 불변원칙: NULL→output NULL, false/0/[] 보존, 추정/현재연도/LLM/fuzzy 0, factory_process_id transport 미출력, DB WRITE 0

## 5. STEP8 handoff 경계
- 기존 `clients/leg_runtime_client`의 `build_facility`(exact-name `_LEG_INPUT_FIELDS` + 승인 alias `has_chemical←has_chemical_substance` + sector gate) 재사용 → 신규 allowlist/alias/default 0
- 얇은 어댑터로 STEP7 `values`만 노출 → facility 생성 → `evaluate_rtm(facility)` 정확히 1회 → LEG raw passthrough
- structural(material/process/equipment/business/hazard/building/regulated) → has_* primitive 파생 0
- unresolved 비차단, 결과 판정/저장/billing 0, DB READ/WRITE 0

---

## 6. 미실행/범위 밖 (다음 WO 후보)
```
DB APPLY(migration UP)         = 0  (운영자 apply 권한)
SYSTEM_CODES INSERT(vocab DML) = 0  (운영자 apply 권한)
MERGE / DEPLOY                 = 0
실제 LEG NETWORK CALL          = 0  (LEG_RUNTIME_URL 결선 시 동작)
required-unresolved 실행 차단 게이트 = 미결정
LEG 결과 판정/가공/저장/billing     = 범위 밖
frontend 결선(admin factory-list 등) = 범위 밖
building_use_type/main_structure 정규화 exact map = 미확정(별도 승인 필요)
building_qualifications/regulated_facility_types 원자 완결 derive = 미완성(법적/물리)
```

## 7. 표준 불변 (전 STEP 공통, 모두 0)
```
factory_process_id mutation = 0    building-register /apply use = 0
LEG / tai-www / tai-admin / CONSTRUCTION / BUILDING delta = 0
PRJ_SEARCH/QUERY/USE = 0    history rewrite(amend/rebase/force) = 0
```

## 8. 다음 세션
운영자 지시로 **건설(CONSTRUCTION) 작업**을 이어서 진행 예정. 본 브랜치는 canonical INDUSTRIAL 구현이 코드상 완료(CLOSED)된 상태이며, 실제 DB APPLY/MERGE/DEPLOY 및 runtime-이후(판정·게이트·frontend)는 운영자/GPT 지시 대기.
