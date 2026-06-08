# Legal Diagnosis — Layer Interface Problems (Stage 2)

**Repo:** `taiengineering/tai-api`  
**Date:** 2026-06-08  
**Scope:** 6-layer 소비자 법령진단 Compiler Core 경로 (`run_anonymous_diagnosis`) — **인터페이스 문제만 기록, 수정안 없음**  
**Reference:** `docs/LEGAL_DIAGNOSIS_LAYER_SURVEY.md` (1단계 조사)  
**DB:** Supabase `vwlahtguyggrhvslabax` (MCP `execute_sql`)

**Pipeline:**
```
[1] DiagnoseStep1Body
  → [2] create_temp_factory + evaluate_single_factory (factories row)
  → [3] FIELD_MAP × draft_slot.binding_field
  → [4] fetch_compiler_candidates → _compiler_result_to_step1_format
  → [5] diagnosis_transform._extract_obligations
  → [6] _partial_from_full / _build_partial
```

---

## Executive Summary

| 구간 | 핵심 문제 | 최고 심각도 |
|------|-----------|-------------|
| [1→2] | `facility_ctx`에만 존재하는 입력이 `factories`에 미저장 → Layer 3 평가가 DB row 기준 | **CRITICAL** |
| [2→3] | `binding_field IS NULL` 슬롯 1,917건 평가 제외; `fac_col=None` 3키는 영구 `MISSING_DATA` | **HIGH** |
| [3→4] | 익명 임시 factory는 `task_candidate` 없음 → applicability fallback만 사용; task_type 명명 불일치 | **CRITICAL** |
| [4→5] | `obligations` wrapper(`items[]`) 미전개 → Transform 제목·evidence 전부 손실 | **HIGH** |
| [5→6] | 동일 `full_result`라도 진입 경로별 `partial_result` 스키마 불일치 | **MEDIUM** |

---

## [1→2] DiagnoseStep1Body (33필드) vs `create_temp_factory` (15 DB 컬럼)

### 1.2.1 스키마 대응

**`DiagnoseStep1Body` 필드 수:** 33 (`factory_id`, `sector`, `input` + 본문 30개) — `schemas/legal_engine.py`

**`create_temp_factory` INSERT 컬럼 (15 + 메타):**

| # | DB 컬럼 | 값 출처 (`facility_ctx` / body) |
|---|---------|--------------------------------|
| 1 | `name` | `[ANON]{sector}-{ts}` |
| 2 | `sector` | `body.sector` |
| 3 | `site_type` | **`sector_raw`** (섹터 코드, 예: `BUILDING`) |
| 4 | `is_active` | `false` |
| 5 | `status_code` | `ANON_TEMP` |
| 6 | `employee_count` | `worker_count` 또는 `employee_count` |
| 7 | `building_area` | `building_area` / `total_floor_area` |
| 8 | `electrical_capacity_kw` | `electrical_capacity_kw` / `electric_capacity` |
| 9 | `transformer_capacity_kva` | `transformer_capacity_kva` |
| 10 | `gas_capacity_m3` | `gas_capacity_m3` |
| 11 | `gas_capacity_kg` | `gas_capacity_kg` |
| 12 | `construction_amount` | `construction_amount` |
| 13 | `ksic_code` | `ksic_code` |
| 14 | `construction_type` | `construction_type` |
| 15 | `subcontractor_worker_count` | `subcontractor_worker_count` / `subcon_workers` |

**Layer 3 평가 입력:** `evaluate_single_factory`는 **`factories` SELECT `*`** 만 사용 (`anonymous_factory_service.py:173–176`). `facility_ctx`는 Layer 4 `result_data.facility_context`에만 남고 평가 루프에는 미사용.

### 1.2.2 누락 필드 목록 및 평가 영향

| 입력 필드 / `facility_ctx` 키 | `factories` 저장 | 평가 영향 | 근거 |
|------------------------------|------------------|-----------|------|
| `factory_id` | N/A (신규 UUID) | 없음 | 임시 factory 의도적 신규 생성 |
| `input` (`region`, `site_kind`, `scale`, `anonymous_flow` 등) | **미저장** | **간접** | tier/UX 메타; FIELD_MAP 직접 키 아님 |
| `building_use_type` → `building_use_code` | **미저장** | **있음** | `facility_type` scope는 `site_type` 컬럼 참조인데 `site_type=sector`로 덮어씀 → 건물 용도 무시 |
| `floor_count` | **미저장** | 없음 (현 FIELD_MAP) | draft_slot에 해당 `binding_field` 없음 |
| `elevator_count` | **미저장** | 없음 (현 FIELD_MAP) | 승강기 조건 슬롯 없음 |
| `boiler_capacity_kw` / `has_boiler` | **미저장** | 없음 (현 FIELD_MAP) | 보일러 전용 binding 없음 |
| `annual_energy_toe` | **미저장** | 없음 (현 FIELD_MAP) | 에너지 binding 없음 |
| `has_high_pressure_gas` | **미저장** (kg만 간접) | **있음** | `gas_capacity_kg`만 저장; 불리언만 제출 시 kg=0이면 가스 관련 numeric/scope 약화 |
| `has_hazardous_material` | **미저장** | 없음 (현 FIELD_MAP) | |
| `has_chemical_substance` | **미저장** | 없음 (현 FIELD_MAP) | |
| `facility_type` (SPECIAL) → `building_use_code` | **미저장** (`site_type=sector`) | **있음** | `facility_type` scope → `site_type` 컬럼인데 섹터 코드만 존재 |
| `direct_workers` | **미저장** (합산만) | **있음** | `employee_count`에 direct+subcon 합만 저장; direct 단독 임계 미반영 가능 |
| `has_tunnel_bridge`, `has_blasting`, `has_crane`, `has_high_work` | **미저장** | 없음 (현 FIELD_MAP) | 건설 위험공종 boolean binding 없음 |
| `employee_count` / `worker_count` / `floor_area` / `electric_capacity` 등 | **저장됨** | **있음** | `employee_count`, `area_size`, `power_capacity` DIRECT 비교 가능 |
| `contract_amount_eok` → `construction_amount` | **저장됨** | **있음** | `monetary_value` → `AMBIGUOUS`만 (MATCH 불가) |
| `ksic_major` → `ksic_code` | **저장됨** | **있음** | `process_type` scope → `POSSIBLE_CANDIDATE` (값 비교 없음) |
| `gas_capacity_m3` / `gas_capacity_kg` | **저장됨** | **있음** | `storage_capacity` → `AMBIGUOUS`; kg는 FIELD_MAP 미연결 |
| `transformer_capacity_kva` | **저장됨** | **있음** | `voltage_level` → `AMBIGUOUS` (전압≠kVA) |
| `construction_type` | **저장됨** | **간접** | FIELD_MAP 키 아님; 건설 summary만 |
| `subcontractor_worker_count` | **저장됨** | **간접** | 별도 binding 없음; `employee_count`와 분리 평가 불가 |

### 1.2.3 구조적 문제 (번호)

| ID | 심각도 | 문제 |
|----|--------|------|
| **P-1-01** | **CRITICAL** | Layer 2 평가(`evaluate_single_factory`)가 `facility_ctx`가 아닌 **15컬럼 `factories` row**만 사용 — ctx에만 있는 입력은 평가에 반영되지 않음 |
| **P-1-02** | **HIGH** | `site_type`에 `building_use_type` / `facility_type` 대신 **`sector` 코드** 저장 → `FIELD_MAP["facility_type"]` → `site_type` scope가 용도·시설유형과 무관 |
| **P-1-03** | **MEDIUM** | `input` dict 전체 미영속 — 익명 프리셋(`region`, `scale`)이 재평가·감사 추적 불가 |
| **P-1-04** | **MEDIUM** | boolean 위험요인(`has_*`) 다수 미저장 — 해당 조건을 쓰는 draft가 추가되면 소비자 입력과 평가 데이터 불일치 |

---

## [2→3] FIELD_MAP (10키) vs `draft_slot` 실제 `binding_field`

### 2.3.1 스키마 명칭 차이

조사 쿼리 문구: `field_name`, `slot_kind = 'IF_NUMERIC'`.  
**실제 DB/코드:** `draft_slot.binding_field`, `draft_slot.section IN ('IF_NUMERIC','IF_SCOPE')` (`_load_draft_slot_groups`).

### 2.3.2 DB 실측 (Supabase `vwlahtguyggrhvslabax`)

**동등 쿼리:**
```sql
SELECT section, binding_field, COUNT(*) AS cnt
FROM draft_slot
WHERE section IN ('IF_NUMERIC','IF_SCOPE')
GROUP BY section, binding_field
ORDER BY section, cnt DESC;
```

| section | binding_field | cnt | FIELD_MAP |
|---------|---------------|-----|-----------|
| IF_NUMERIC | *(null)* | **1,702** | — (로더 제외) |
| IF_NUMERIC | `distance_value` | 415 | ✓ (`fac_col=None`) |
| IF_NUMERIC | `employee_count` | 164 | ✓ DIRECT |
| IF_NUMERIC | `voltage_level` | 142 | ✓ AMBIGUOUS |
| IF_NUMERIC | `concentration_level` | 110 | ✓ (`fac_col=None`) |
| IF_NUMERIC | `storage_capacity` | 23 | ✓ AMBIGUOUS |
| IF_NUMERIC | `power_capacity` | 15 | ✓ DIRECT |
| IF_NUMERIC | `area_size` | 12 | ✓ DIRECT |
| IF_NUMERIC | `monetary_value` | 6 | ✓ AMBIGUOUS |
| IF_SCOPE | `equipment_type` | 260 | ✓ (`fac_col=None`) |
| IF_SCOPE | `facility_type` | 220 | ✓ AMBIGUOUS |
| IF_SCOPE | *(null)* | **215** | — (로더 제외) |
| IF_SCOPE | `process_type` | 33 | ✓ AMBIGUOUS |

- **IF_NUMERIC/IF_SCOPE 슬롯 합계:** 3,317  
- **`binding_field IS NULL`:** 1,917 (57.8%) — `_load_draft_slot_groups`에서 **`.not_.is_("binding_field", "null")`** 로 **평가 대상에서 제외**  
- **FIELD_MAP에 없는 non-null `binding_field`:** **0건** (DB 기준 “맵 밖 field_name” 없음)

### 2.3.3 FIELD_MAP 10키별 평가 가능성

| binding_field | fac_col | quality | 평가 결과 | MATCH/POSSIBLE persist |
|---------------|---------|---------|-----------|------------------------|
| `employee_count` | `employee_count` | DIRECT | `DIRECT_COMPARE` | 가능 |
| `area_size` | `building_area` | DIRECT | `DIRECT_COMPARE` | 가능 |
| `power_capacity` | `electrical_capacity_kw` | DIRECT | `DIRECT_COMPARE` | 가능 |
| `voltage_level` | `transformer_capacity_kva` | AMBIGUOUS | 항상 `AMBIGUOUS` | **불가** (`_PERSIST_STATUSES`에 없음) |
| `storage_capacity` | `gas_capacity_m3` | AMBIGUOUS | 항상 `AMBIGUOUS` | **불가** |
| `monetary_value` | `construction_amount` | AMBIGUOUS | 항상 `AMBIGUOUS` | **불가** |
| `facility_type` | `site_type` | AMBIGUOUS (scope) | 값 존재 시 `POSSIBLE_CANDIDATE` | 가능 (의미 왜곡 — P-1-02) |
| `process_type` | `ksic_code` | AMBIGUOUS (scope) | `POSSIBLE_CANDIDATE` | 가능 (코드 존재만 확인) |
| `concentration_level` | `None` | MISSING | `MISSING_DATA` / `NO_FACILITY_COLUMN` | **불가** |
| `distance_value` | `None` | MISSING | 동일 | **불가** |
| `equipment_type` | `None` | EQUIPMENT_JOIN | scope도 `NO_FACILITY_COLUMN` | **불가** |

**영향 큰 슬롯 수 (fac_col=None):** `distance_value` 415 + `concentration_level` 110 + `equipment_type` 260 = **785건** — 코드상 구조적으로 `MATCH_CANDIDATE`/`POSSIBLE_CANDIDATE` 도달 불가.

### 2.3.4 구조적 문제 (번호)

| ID | 심각도 | 문제 |
|----|--------|------|
| **P-2-01** | **HIGH** | 1,917개 슬롯(`binding_field` null)이 평가 파이프라인에 **진입하지 않음** — 해당 draft는 numeric/scope 체크 없이 후보에서 빠질 수 있음 |
| **P-2-02** | **HIGH** | FIELD_MAP에 있으나 `fac_col=None`인 3키(`concentration_level`, `distance_value`, `equipment_type`) — **785 슬롯**이 영구 `MISSING_DATA` |
| **P-2-03** | **HIGH** | `AMBIGUOUS` quality 4키는 numeric 비교 없음 → draft 전체가 `AMBIGUOUS`이면 persist 제외; `POSSIBLE_CANDIDATE`만 scope로 얻는 draft에 편향 |
| **P-2-04** | **LOW** | 문서/쿼리 `field_name`·`slot_kind` vs 실제 `binding_field`·`section` 불일치 — 운영 SQL 오류 위험 |

---

## [3→4] task 경로 vs applicability fallback 경로

### 3.4.1 경로 선택 로직

```python
rules_from_tasks = [_task_to_rule_row(t, sector_raw) for t in tasks]
if not rules_from_tasks and applicability:
    # applicability → generic rule rows
```

`tasks` = `fetch_compiler_candidates` → `task_candidate` WHERE `factory_id = fid`.

**DB:** `task_candidate` **3,388행**, **distinct factory_id = 29**. 익명 진단은 매 요청 **신규 UUID** 임시 factory → **`task_candidates` ≈ 항상 `[]`**.

→ 소비자 Compiler 경로는 사실상 **applicability fallback만** Layer 4 rule 생성에 사용.

### 3.4.2 출력 필드 차이표

| 필드 | Task 경로 `_task_to_rule_row` | Applicability fallback |
|------|------------------------------|------------------------|
| `rule_id` | `task.id` | `applicability.id` 또는 `draft_id` |
| `rule_type` | `task_type` (예: `INSPECTION_TASK_CANDIDATE`) | **없음** |
| `law_name` | `obligation_family` 또는 `"Compiler Candidate"` | **`"Applicability Candidate"`** (고정) |
| `law_article` | `""` | `""` |
| `obligation_summary` | `{task_type}: {source_action_family}` | **`"Applicability: {status}"`** |
| `remarks` / `description` | title 문자열 | **`draft={draft_id}`** |
| `category` | bucket label (선임/점검/…) | **`"조치"`** (고정) |
| `obligation_type` | `APPOINT`/`INSPECT`/… 또는 **`ACTION`** (아래 P-3-03) | **`ACTION`** |
| `sector` | `sector_raw` | `sector_raw` |
| `diagnosis_stage` | `1` | **없음** |
| `schedule_type` | `ON_DEMAND` | **없음** |
| `penalty_summary` | `""` | **없음** |
| `appointment_required` | bucket 기반 | **없음** |
| `inspection_required` | bucket 기반 | **없음** |
| `action_required` | bucket 기반 | **`True`만** |
| `report_required` | bucket 기반 | **없음** |
| `notify_required` | bucket 기반 | **없음** |
| 법령·조문·패널티 연결 | `obligation_family` 일부 | **없음** (status 문자열만) |

### 3.4.3 task_type 명명 불일치 (task 경로가 있어도)

**DB `task_type` 분포 (상위):** `REPORT_TASK_CANDIDATE`(988), `INSTALL_TASK_CANDIDATE`(769), `APPOINTMENT_TASK_CANDIDATE`(764), `INSPECTION_TASK_CANDIDATE`(144), …

**`_TASK_TYPE_TO_BUCKET` 키:** `APPOINTMENT`, `INSPECTION`, `REPORT`, … (**`_TASK_CANDIDATE` 접미사 없음**)

→ `task_type.upper()`가 맵에 없으면 **전부 `("action", "조치")` bucket**.

**`obligation_type` 허용 목록:** `APPOINT`, `INSPECT`, `REPORT`, `NOTIFY`, `ACTION` — DB 값 `*_TASK_CANDIDATE`와 **불일치** → **항상 `ACTION`**.

### 3.4.4 구조적 문제 (번호)

| ID | 심각도 | 문제 |
|----|--------|------|
| **P-3-01** | **CRITICAL** | 익명 임시 `factory_id`에 `task_candidate` 없음 → Layer 4 출력이 **applicability fallback 형태**로 고정 |
| **P-3-02** | **HIGH** | Fallback row는 법령명·의무 유형·bucket 플래그·일정 메타 **대부분 누락** — UI/Transform이 기대하는 rule row 스키마와 불일치 |
| **P-3-03** | **HIGH** | `_TASK_TYPE_TO_BUCKET` / `obligation_type`이 실제 DB `*_TASK_CANDIDATE` enum과 **미매칭** — task 경로 복구 시에도 bucket·`inspection_required` 오분류 |
| **P-3-04** | **MEDIUM** | `rules_from_tasks` 비어 있을 때만 applicability 사용 — task와 applicability **병합 없음**; 이중 정보 소실 |

---

## [4→5] `obligations` wrapper와 Transform 처리

### 4.5.1 Layer 4 `obligations` 구조

`_compiler_result_to_step1_format` (`anonymous_factory_service.py:332–339`):

```python
obligations.append({
    "category": key,      # "appointment" | "inspection" | ...
    "label": label,       # "선임" | "점검" | ...
    "items": triggered[key],  # List[rule_row dict]
})
```

동시에 `key_obligations`는 **`List[str]`** (요약 문자열 20개까지).

### 4.5.2 `_extract_obligations` 동작

1. 키 우선순위: `obligations` → `key_obligations` → … — **`obligations`가 non-empty이면 즉시 선택**  
2. `raw_list`의 각 원소를 **flat obligation**으로 1:1 변환  
3. wrapper dict에는 `title`/`name`/`item` 없음 → **`title = "의무사항"`**  
4. `evidence` = `obj.get("evidence")` or `legal_basis` — wrapper에 없음 → **`[]`**  
5. **`items[]` 전개 없음** — nested `rule_row`의 `obligation_summary`, `law_name`, flags 미사용  
6. `key_obligations`(문자열 리스트)는 `obligations` wrapper가 있으면 **도달하지 않음**

### 4.5.3 evidence / evidence_chain

- Layer 4 `rule_row`에도 `evidence` / `evidence_chain` 필드 **없음**  
- `compiler_core` 블록에 raw candidates는 있으나 Transform **미참조**  
- Transform 출력: 모든 obligation `evidence: []` 고정에 가까움

### 4.5.4 구조적 문제 (번호)

| ID | 심각도 | 문제 |
|----|--------|------|
| **P-4-01** | **HIGH** | Transform이 `obligations[].items[]` wrapper를 **범주 1건**으로 처리 — 실제 의무 건수·제목·법령명 소실 |
| **P-4-02** | **HIGH** | `key_obligations`(가독 문자열)가 wrapper 존재로 **우선순위에서 밀림** — 의도한 요약도 Transform에 반영 안 됨 |
| **P-4-03** | **HIGH** | `evidence` / `evidence_chain` **전 구간 미연결** — Layer 5 obligation evidence 항상 빈 배열 |
| **P-4-04** | **MEDIUM** | `rules_table` / `rules`에는 flat rule_row 있으나 Transform은 `obligations` 키만 사용 — **동일 full_result 내 데이터 이중 구조·불일치** |

---

## [5→6] `_partial_from_full` vs `_build_partial`

### 5.6.1 코드 위치

- 익명: `routers/anonymous_diagnosis.py` → `_partial_from_full`
- 통합: `services/diagnosis_helpers.py` → `_build_partial`

### 5.6.2 동일 `full_result` 기준 필드 비교

| 키 | `_partial_from_full` | `_build_partial` | 비고 |
|----|----------------------|------------------|------|
| `risk_level` | ✓ | ✓ | 동일 |
| `summary` | ✓ | ✓ | 동일 |
| `applicable_count` | ✓ | ✓ | 동일 |
| `sector` | ✓ | ✓ | 동일 |
| `key_obligations` | ✓ `[:6]` | ✓ `[:6]` | Compiler 경로에서 **문자열 리스트** |
| `law_badges` | ✓ `[:18]` | ✓ `[:18]` | 동일 |
| `evaluated_at` | ✓ | **없음** | 통합 partial에 시각 없음 |
| `rules_preview` | ✓ `rules[:12]` | **없음** | 익명만 rule 미리보기 |
| `construction_summary` | ✓ (CONSTRUCTION 시) | **없음** | 건설 섹터 partial 불균형 |
| `message` | ✓ (로그인 유도 문구) | **없음** | UX 메타만 익명 |

**공유되지 않는 full 필드 (양쪽 partial 모두 누락):** `obligations`, `rules_table`, `compiler_core`, `facility_context`, `risk_reason`, bucket arrays (`appointment_required` 등).

### 5.6.3 구조적 문제 (번호)

| ID | 심각도 | 문제 |
|----|--------|------|
| **P-5-01** | **MEDIUM** | 동일 diagnosis 엔진 출력인데 **진입 API별 partial 스키마 상이** — 클라이언트 공통 모델 불가 |
| **P-5-02** | **MEDIUM** | `rules_preview`·`construction_summary`·`evaluated_at` 익명 전용 — 통합 로그인 사용자는 동일 정보 partial에서 **접근 불가** |
| **P-5-03** | **LOW** | `key_obligations` 타입이 경로별로 `List[str]`(Compiler) vs legacy 구조 혼재 가능 — partial만으로 의미 해석 불명확 |

---

## Cross-Layer Problem Index

| ID | 구간 | 심각도 | 한 줄 요약 |
|----|------|--------|------------|
| P-1-01 | 1→2 | CRITICAL | 평가는 15컬럼 factory row만 사용 |
| P-1-02 | 1→2 | HIGH | `site_type`≠건물/시설 용도 |
| P-1-03 | 1→2 | MEDIUM | `input` dict 미영속 |
| P-1-04 | 1→2 | MEDIUM | `has_*` boolean 미저장 |
| P-2-01 | 2→3 | HIGH | null `binding_field` 1,917 슬롯 제외 |
| P-2-02 | 2→3 | HIGH | fac_col=None 3키 → 785 슬롯 영구 MISSING |
| P-2-03 | 2→3 | HIGH | AMBIGUOUS-only draft persist 불가 |
| P-2-04 | 2→3 | LOW | DB 컬럼명 문서 불일치 |
| P-3-01 | 3→4 | CRITICAL | 익명 경로 task_candidate 공백 → fallback only |
| P-3-02 | 3→4 | HIGH | Fallback rule row 메타 대량 누락 |
| P-3-03 | 3→4 | HIGH | `*_TASK_CANDIDATE` vs bucket 맵 불일치 |
| P-3-04 | 3→4 | MEDIUM | task·applicability 비병합 |
| P-4-01 | 4→5 | HIGH | obligations wrapper 미전개 |
| P-4-02 | 4→5 | HIGH | key_obligations 우선순위 차단 |
| P-4-03 | 4→5 | HIGH | evidence 전 구간 빈 배열 |
| P-4-04 | 4→5 | MEDIUM | rules vs obligations 이중 구조 |
| P-5-01 | 5→6 | MEDIUM | partial 스키마 API별 분기 |
| P-5-02 | 5→6 | MEDIUM | rules_preview 등 익명 편향 |
| P-5-03 | 5→6 | LOW | key_obligations 타입 혼재 |

---

## Source Files

| Layer | File |
|-------|------|
| 1 | `schemas/legal_engine.py` |
| 2 | `services/anonymous_factory_service.py`, `services/legal_context.py` |
| 3 | `services/facility_applicability_eval.py` |
| 4 | `services/compiler_core_svc.py`, `services/anonymous_factory_service.py` |
| 5 | `routers/diagnosis_transform.py`, `routers/anonymous_diagnosis.py` |
| 6 | `routers/anonymous_diagnosis.py`, `services/diagnosis_helpers.py` |

---

*Stage 2 complete. 수정·패치 없음. Stage 3(연결 설계)는 별도 워크오더.*
