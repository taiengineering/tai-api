# Legal Diagnosis — 6-Layer Interface Survey

**Repo:** `taiengineering/tai-api`  
**Date:** 2026-06-08  
**Scope:** 소비자 법령진단 **Compiler Core 경로** (`run_anonymous_diagnosis`) — 코드에서 확인한 필드·타입·구조만 기록. 추측 없음.  
**Primary files:** `schemas/legal_engine.py`, `services/anonymous_factory_service.py`, `services/facility_applicability_eval.py`, `services/compiler_core_svc.py`, `services/legal_context.py`, `services/legal_rules.py`, `routers/diagnosis_transform.py`, `routers/anonymous_diagnosis.py`, `services/diagnosis_integrated_svc.py`

**Orchestration entry (공통):**
```
run_step1_via_compiler(supabase, DiagnoseStep1Body)
  → run_anonymous_diagnosis(supabase, body, allowed_sectors)
  → Dict[str, Any]   # step1 result_data
  → wrapped: {"status": "success", "data": result_data}
```

---

## Layer [1] 소비자 입력

### 1.1 `DiagnoseStep1Body` (`schemas/legal_engine.py`)

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `factory_id` | `Optional[str]` | `None` | Compiler 소비자 경로: 익명은 `None`; `/diagnosis/run`은 optional |
| `sector` | `str` | (required) | `.strip().upper()` 후 검증 |
| `input` | `Optional[Dict[str, Any]]` | `{}` | 자유 키·값 dict |
| `building_use_type` | `Optional[str]` | `None` | BUILDING |
| `employee_count` | `Optional[int]` | `None` | |
| `floor_area` | `Optional[float]` | `None` | |
| `worker_count` | `Optional[int]` | `None` | |
| `total_floor_area` | `Optional[float]` | `None` | |
| `electric_capacity` | `Optional[float]` | `None` | |
| `floor_count` | `Optional[int]` | `None` | |
| `contract_amount_eok` | `Optional[float]` | `None` | 억원 단위 (Field description) |
| `ksic_major` | `Optional[str]` | `None` | MANUFACTURING |
| `facility_type` | `Optional[str]` | `None` | SPECIAL_FACILITY |
| `elevator_count` | `Optional[int]` | `None` | |
| `gas_capacity_kg` | `Optional[float]` | `None` | |
| `gas_capacity_m3` | `Optional[float]` | `None` | |
| `boiler_capacity_kw` | `Optional[float]` | `None` | |
| `annual_energy_toe` | `Optional[float]` | `None` | |
| `has_high_pressure_gas` | `Optional[bool]` | `None` | |
| `has_boiler` | `Optional[bool]` | `None` | |
| `has_hazardous_material` | `Optional[bool]` | `None` | |
| `has_chemical_substance` | `Optional[bool]` | `None` | |
| `construction_type` | `Optional[str]` | `None` | CONSTRUCTION |
| `direct_workers` | `Optional[int]` | `None` | CONSTRUCTION |
| `subcon_workers` | `Optional[int]` | `None` | CONSTRUCTION |
| `electrical_capacity_kw` | `Optional[float]` | `None` | CONSTRUCTION |
| `has_tunnel_bridge` | `Optional[bool]` | `None` | CONSTRUCTION |
| `has_blasting` | `Optional[bool]` | `None` | CONSTRUCTION |
| `has_crane` | `Optional[bool]` | `None` | CONSTRUCTION |
| `has_high_work` | `Optional[bool]` | `None` | CONSTRUCTION |

### 1.2 섹터별 진입 (코드에서 조립되는 필드)

**Allowed sectors** (`anonymous_factory_service.run_anonymous_diagnosis`, `anonymous_diagnosis.py`):
`BUILDING`, `MANUFACTURING`, `CONSTRUCTION`, `SPECIAL_FACILITY`, `SPECIAL`

#### A) `POST /anonymous-diagnosis` — `AnonymousDiagnosisCreate` → `DiagnoseStep1Body`

`AnonymousDiagnosisCreate` (`routers/anonymous_diagnosis.py`):

| Field | Type | Constraint |
|-------|------|------------|
| `site_kind` | `str` | `construction \| manufacturing \| building \| other` |
| `scale` | `str` | `small \| medium \| large` |
| `workers` | `int` | `ge=1, le=50000` |
| `region` | `str` | default `""` |

`SECTOR_BY_KIND`: `construction→CONSTRUCTION`, `manufacturing→MANUFACTURING`, `building→BUILDING`, `other→SPECIAL_FACILITY`

`SCALE_PRESETS` keys: `small`, `medium`, `large` — each has `floor_area`, `total_floor_area`, `contract_amount_eok`, `employee_hint` (float/int)

| Sector | `DiagnoseStep1Body` fields set | `input` dict keys |
|--------|-------------------------------|-------------------|
| `CONSTRUCTION` | `factory_id=None`, `construction_type="건축"`, `contract_amount_eok=preset`, `direct_workers=workers`, `subcon_workers=0` | `region`, `site_kind`, `scale`, `anonymous_flow=True` |
| `MANUFACTURING` | `worker_count`, `employee_count`, `floor_area`, `total_floor_area`, `ksic_major=""` | same + above |
| `BUILDING` | `building_use_type="사무실"`, `floor_area`, `total_floor_area`, `worker_count`, `employee_count`, `floor_count=5` | same |
| `SPECIAL_FACILITY` | `facility_type="기타시설"`, `floor_area`, `total_floor_area`, `worker_count`, `employee_count` | same |

#### B) `POST /diagnosis/run` — `DiagnosisRunBody` → `DiagnoseStep1Body`

`DiagnosisRunBody` (`schemas/diagnosis_integrated.py`) — Nexas 필드. `nexas_run_body_from_request()`가 `form_data` 병합.

`diagnosis_integrated_svc.run_diagnosis`가 `normalize_sector_db(body.sector)` 후 `engine_sector`:
- `INDUSTRIAL` → `MANUFACTURING`
- else → `sector` 그대로

| `engine_sector` | `DiagnoseStep1Body` 조립 필드 |
|-----------------|------------------------------|
| `CONSTRUCTION` | `factory_id`, `construction_type`, `contract_amount_eok`, `direct_workers`, `subcon_workers`, `input` |
| `BUILDING` | `factory_id`, `building_use_type`, `floor_area`, `total_floor_area`, `worker_count`, `employee_count`, `floor_count`, `electric_capacity`, `elevator_count`, `has_high_pressure_gas`←`has_gas`, `has_hazardous_material`←`has_chemical` |
| else (MANUFACTURING 등) | `factory_id`, `worker_count`, `employee_count`, `floor_area`, `total_floor_area`, `ksic_major`, `electric_capacity`, `has_boiler`, `has_hazardous_material`, `has_high_pressure_gas`, `has_chemical_substance` |

공통 `input` dict: `region`, `anonymous_flow=True`, `tier_code`, optional `factory_id`, `company_id`

### 1.3 `_merge_body_input(body)` 출력

`Dict[str, Any]`: `body.input` 복사 후, top-level `DiagnoseStep1Body` 필드 중 `input`에 없고 `not None`인 값을 아래 키로 주입:

`building_use_type`, `employee_count`, `floor_area`, `worker_count`, `total_floor_area`, `electric_capacity`, `floor_count`, `contract_amount_eok`, `ksic_major`, `facility_type`, `elevator_count`, `gas_capacity_kg`, `gas_capacity_m3`, `boiler_capacity_kw`, `annual_energy_toe`, `has_high_pressure_gas`, `has_boiler`, `has_hazardous_material`, `has_chemical_substance`, `construction_type`, `direct_workers`, `subcon_workers`, `electrical_capacity_kw`, `has_tunnel_bridge`, `has_blasting`, `has_crane`, `has_high_work`

---

## Layer [2] 엔진 입력부

### 2.1 `create_temp_factory(supabase, body: DiagnoseStep1Body) -> str`

**Returns:** `factories.id` (str)

**Pipeline inside:**
1. `sector_raw = body.sector.strip().upper()`
2. `inp = _merge_body_input(body)`
3. `ctx = _input_to_facility_context(sector_raw, inp)` — Layer 1→2 facility context (아래 § Interface 1→2)
4. `factories` INSERT row:

| `factories` column | Source expression | Python cast |
|--------------------|-------------------|-------------|
| `name` | `f"[ANON]{sector_raw}-{ts}"[:200]` | `str` |
| `sector` | `sector_raw` | `str` |
| `site_type` | `sector_raw` | `str` |
| `is_active` | `False` | `bool` |
| `status_code` | `"ANON_TEMP"` | `str` |
| `employee_count` | `ctx.worker_count or ctx.employee_count or 0` | `int` |
| `building_area` | `ctx.building_area or ctx.total_floor_area or 0` | `float` |
| `electrical_capacity_kw` | `ctx.electrical_capacity_kw or ctx.electric_capacity or 0` | `float` |
| `transformer_capacity_kva` | `ctx.transformer_capacity_kva or 0` | `float` |
| `gas_capacity_m3` | `ctx.gas_capacity_m3 or 0` | `float` |
| `gas_capacity_kg` | `ctx.gas_capacity_kg or 0` | `float` |
| `construction_amount` | `ctx.construction_amount or 0` | `float` |
| `ksic_code` | `ctx.ksic_code or ""` | `str` |
| `construction_type` | `ctx.construction_type or ""` | `str` |
| `subcontractor_worker_count` | `ctx.subcontractor_worker_count or ctx.subcon_workers or 0` | `int` |
| `created_at` | `datetime.now(timezone.utc).isoformat()` | `str` (ISO) |
| `updated_at` | same | `str` (ISO) |

**Not written to `factories` from ctx:** `floor_count`, boolean flags (`has_*`), `elevator_count`, `building_use_code`, etc. — `FIELD_MAP` 비연결 컬럼은 applicability 평가 시 `FACILITY_VALUE_NULL` / `MISSING_DATA` 가능.

### 2.2 `evaluate_single_factory(supabase, factory_id: str) -> Dict[str, int]`

**인자:** `factory_id: str` only (추가 kwargs 없음)

**Returns:**
```python
{"drafts_evaluated": int, "applicability_inserted": int}
```

**Reads:**
- `factories` SELECT `*` WHERE `id = factory_id`
- `draft_slot` SELECT (`draft_id`, `part_id`, `section`, `binding_field`, `operator`, `value`, `unit`, `family_name`) WHERE `binding_field IS NOT NULL` AND `section IN ('IF_NUMERIC','IF_SCOPE')` — paginated 1000/page

**Writes (`facility_applicability` INSERT), per draft where overall ∈ `MATCH_CANDIDATE`, `POSSIBLE_CANDIDATE`:**

| Column | Value |
|--------|-------|
| `factory_id` | `factory_id` |
| `draft_id` | `draft_id` |
| `part_id` | `part_id` (str) |
| `applicability_status` | `overall` (str) |
| `match_details` | `{"checks": len(check_results)}` |

**Calls:** `evaluate_draft_for_facility(facility, draft_id, numeric_slots, scope_slots)` per draft.

### 2.3 `fetch_compiler_candidates(supabase, factory_id)` (Layer 2 후속 read)

**인자:** `factory_id: str`, optional `applicability_statuses` default `("MATCH_CANDIDATE", "POSSIBLE_CANDIDATE")`

**Reads (factory_id scoped unless noted):**

| Table | SELECT columns |
|-------|----------------|
| `facility_applicability` | `id, draft_id, applicability_status, part_id, match_details` |
| `task_candidate` | `id, task_type, source_action_family, obligation_family, applicability_status, status` |
| `schedule_candidate` | `id, schedule_type, source_family, source_relation_type, task_type, status` |
| `penalty_obligation_relation` | `id, penalty_candidate_id, rule_candidate_id, obligation_family, via_reference, status` (limit 200, **not** factory-filtered) |
| `compliance_review_queue` | `id, issue_type, detail, status` |
| `compliance_package` | `*` |

### 2.4 Cleanup

`cleanup_temp_factory(supabase, factory_id)`:
- DELETE `facility_applicability` WHERE `factory_id`
- DELETE `factories` WHERE `id`

---

## Layer [3] 법령엔진 내부 (Applicability + Compiler read)

소비자 경로의 “내부 엔진”은 `services/facility_applicability_eval.py` + pre-materialized Compiler 테이블 read.

### 3.1 `FIELD_MAP`

`Dict[str, Tuple[Optional[str], str]]` — `binding_field → (factories column, match quality)`

| `binding_field` | factories column | quality |
|-----------------|------------------|---------|
| `employee_count` | `employee_count` | `DIRECT` |
| `area_size` | `building_area` | `DIRECT` |
| `power_capacity` | `electrical_capacity_kw` | `DIRECT` |
| `voltage_level` | `transformer_capacity_kva` | `AMBIGUOUS` |
| `storage_capacity` | `gas_capacity_m3` | `AMBIGUOUS` |
| `equipment_type` | `None` | `EQUIPMENT_JOIN` |
| `facility_type` | `site_type` | `AMBIGUOUS` |
| `process_type` | `ksic_code` | `AMBIGUOUS` |
| `monetary_value` | `construction_amount` | `AMBIGUOUS` |
| `concentration_level` | `None` | `MISSING` |
| `distance_value` | `None` | `MISSING` |

### 3.2 `compare_numeric(operator, draft_val, facility_val) -> str`

| Condition | Return token |
|-----------|--------------|
| `draft_val is None` or `facility_val is None` | `MISSING_DATA` |
| non-numeric cast | `MISSING_DATA` |
| `op == ">="` and `fv >= dv` | `MATCH_CANDIDATE` |
| `op == ">="` and else | `NOT_MATCHED` |
| `op == "<="` and `fv <= dv` | `MATCH_CANDIDATE` |
| `op == "<="` and else | `NOT_MATCHED` |
| `op == ">"` and `fv > dv` | `MATCH_CANDIDATE` |
| `op == ">"` and else | `NOT_MATCHED` |
| `op == "<"` and `fv < dv` | `MATCH_CANDIDATE` |
| `op == "<"` and else | `NOT_MATCHED` |
| other operator | `AMBIGUOUS` |

### 3.3 `aggregate_applicability_status(results: Set[str]) -> str`

| `results` set condition | `applicability_status` |
|-------------------------|------------------------|
| empty | `MISSING_DATA` |
| has `MATCH_CANDIDATE`, no `NOT_MATCHED` | `MATCH_CANDIDATE` |
| has both `MATCH_CANDIDATE` and `NOT_MATCHED` | `AMBIGUOUS` |
| has `POSSIBLE_CANDIDATE` | `POSSIBLE_CANDIDATE` |
| has `AMBIGUOUS` | `AMBIGUOUS` |
| exactly `{"NOT_MATCHED"}` | `NOT_MATCHED` |
| else | `MISSING_DATA` |

**Persist filter** (`anonymous_factory_service._PERSIST_STATUSES`): only `MATCH_CANDIDATE`, `POSSIBLE_CANDIDATE` inserted.

### 3.4 `CheckResult` tuple (8 elements)

```python
CheckResult = Tuple[str, str, Optional[str], Optional[str], Any, Any, str, str]
# (check_type, binding_field, fac_col, operator, draft_value, fac_val, result_token, reason_code)
```

`result_token` (index 6): `MATCH_CANDIDATE`, `NOT_MATCHED`, `MISSING_DATA`, `AMBIGUOUS`, `POSSIBLE_CANDIDATE`

### 3.5 `evaluate_draft_for_facility` return

```python
Optional[Tuple[str, str, List[CheckResult]]]
# (overall_status, part_id, check_results)
```

Returns `None` if `not check_results` or `part_id is None`.

### 3.6 `fetch_compiler_candidates` return dict

```python
{
    "factory_id": str,
    "compiler_version": "v3.0-deterministic",
    "warning": "All results are CANDIDATES. Not legal conclusions.",
    "applicability_candidates": list[dict],  # facility_applicability rows
    "task_candidates": list[dict],
    "schedule_candidates": list[dict],
    "penalty_relations": list[dict],
    "penalty_candidates": list[dict],  # same slice as penalty_relations
    "review_queue": list[dict],
    "residuals": list[dict],  # same as review_queue.data
    "compliance_package": dict | None,
}
```

---

## Layer [4] 검증엔진 — `_compiler_result_to_step1_format`

**Input:** `compiler: Dict` (Layer 3 output), `sector_raw: str`, `facility_ctx: Dict`, `evaluated_at: str` (ISO)

### 4.1 `_TASK_TYPE_TO_BUCKET`

`task_type.upper()` → `(bucket_key, category_label)`:

| `task_type` | bucket | label |
|-------------|--------|-------|
| `APPOINTMENT`, `DESIGNATE` | `appointment` | `선임` |
| `REPORT`, `SUBMIT` | `report` | `신고` |
| `NOTIFY` | `notify` | `보고` |
| `INSPECTION`, `INSPECT`, `MEASURE` | `inspection` | `점검` |
| `INSTALL`, `MAINTAIN`, `EDUCATION`, `RECORD`, `PRESERVATION` | `action` | `조치` |
| (other) | `action` | `조치` |

### 4.2 `_task_to_rule_row(task, sector_raw) -> dict`

**Input `task` keys read:** `task_type`, `source_action_family`, `obligation_family`, `id`

**Output dict keys (before `_bucket` pop):**

| Key | Source |
|-----|--------|
| `rule_id` | `str(task["id"] or "")` |
| `rule_type` | `task_type` upper, default `ACTION` |
| `law_name` | `obligation_family` or `"Compiler Candidate"` |
| `law_article` | `""` |
| `obligation_summary`, `remarks`, `description` | title string |
| `category` | bucket label (한글) |
| `obligation_type` | `task_type` if in `APPOINT,INSPECT,REPORT,NOTIFY,ACTION` else `ACTION` |
| `sector` | `sector_raw` |
| `diagnosis_stage` | `1` |
| `schedule_type` | `"ON_DEMAND"` |
| `penalty_summary` | `""` |
| `appointment_required` | `bool` |
| `inspection_required` | `bool` |
| `action_required` | `bool` |
| `report_required` | `bool` |
| `notify_required` | `bool` |
| `_bucket` | internal bucket key |

### 4.3 Applicability fallback rows

If `rules_from_tasks` empty and `applicability` non-empty, per applicability row `a`:

| Key | Value |
|-----|-------|
| `rule_id` | `str(a["id"] or a["draft_id"] or "")` |
| `law_name` | `"Applicability Candidate"` |
| `obligation_summary` | `f"Applicability: {a['applicability_status']}"` |
| `obligation_type` | `"ACTION"` |
| `action_required` | `True` |
| `_bucket` | `"action"` |

### 4.4 `rules_table` item shape

```python
{"category": "<한글 label>", **rule_row}  # rule_row without _bucket
```

Labels order: `appointment→선임`, `inspection→점검`, `action→조치`, `report→신고`, `notify→보고`

### 4.5 `risk_level(applicable_count: int, appointment_n: int) -> str`

| Condition | Return |
|-----------|--------|
| `applicable_count >= 12` or `appointment_n >= 4` | `"HIGH"` |
| `applicable_count >= 5` or `appointment_n >= 1` | `"MEDIUM"` |
| else | `"LOW"` |

Where:
- `applicable_count = sum(len(triggered[k]) for k in appointment, inspection, notify, report, action)`
- `appointment_n = len(triggered["appointment"])`

### 4.6 `obligations` (group wrapper)

```python
[
  {"category": "appointment"|"inspection"|"action"|"report"|"notify",
   "label": "<한글>",
   "items": [<rule_row dict>, ...]},
  ...
]
```

### 4.7 `key_obligations`

`List[str]` — first 20 unique `obligation_summary` or `remarks` strings from `rules_from_tasks`.

### 4.8 Full `result_data` top-level keys (`_compiler_result_to_step1_format` return)

| Key | Type / shape |
|-----|----------------|
| `sector` | `str` |
| `sector_groups` | `List[str]` from `get_sector_groups(normalize_sector_db(sector_raw))` |
| `step` | `int` `1` |
| `engine_version` | `"v3.0-compiler-core-anonymous"` |
| `rule_version` | `"compiler_core:facility_applicability:v1"` |
| `evaluated_at` | `str` ISO |
| `facility_context` | `Dict` (Layer 1→2 ctx) |
| `risk_level` | `"HIGH"\|"MEDIUM"\|"LOW"` |
| `risk_reason` | `str` |
| `applicable_law_categories` | `List[str]` sorted unique `law_name` |
| `appointment_required_flag` | `bool` |
| `key_obligations` | `List[str]` |
| `law_badges` | `List[str]` (= law_names) |
| `obligations` | group wrapper list (§4.6) |
| `rules_table` | `List[dict]` |
| `rules` | same as `rules_table` |
| `appointment_required` | `List[dict]` |
| `inspection_required` | `List[dict]` |
| `action_required` | `List[dict]` |
| `report_required` | `List[dict]` (report + notify combined) |
| `not_applicable` | `[]` |
| `not_applicable_total` | `0` |
| `total_rules_checked` | `int` |
| `applicable_count` | `int` |
| `article_mapping_stats` | `{total_rules, mapped_rules:0, coverage_pct:0.0}` |
| `inspection_schedule_ready` | `{periodic_count:0, before_work_count:0, on_demand_count, periodic:[], before_work:[]}` |
| `summary` | `{total, appointment, inspection, action, report, notify, form_linked:0}` |
| `compiler_core` | `{compiler_version, warning, applicability_count, task_count, schedule_count, applicability_candidates, task_candidates, schedule_candidates}` |
| `construction_summary` | `Dict` — **only if** `sector_raw == "CONSTRUCTION"` (`get_construction_summary(facility_ctx)`) |

### 4.9 `construction_summary` keys (`get_construction_summary`)

`site_type`, `contract_amount`, `contract_amount_eok`, `total_workers`, `direct_workers`, `subcon_workers`, `safety_manager_required`, `safety_manager_basis`, `threshold_used`, `key_thresholds_met` (dict of bool thresholds)

---

## Layer [5] 정제 (Transform + 저장)

### 5.1 저장 — `anonymous_diagnosis_results` INSERT

#### 무료 `POST /anonymous-diagnosis`

| Column | Value |
|--------|-------|
| `public_token` | `uuid4` str |
| `input_data` | `{site_kind, scale, workers, region, sector}` |
| `partial_result` | `_partial_from_full(full_result)` |
| `full_result` | Layer 4 `result_data` |
| `created_at` | ISO |
| `expires_at` | now + 7 days ISO |
| `claimed_user_id` | `None` |
| `status` | `"ACTIVE"` |
| `source_type` | `"site_free"` |
| `engine_version` | `ANONYMOUS_COMPILER_ENGINE_VERSION` |
| `rule_version` | `RULE_VERSION_COMPILER` |

#### 유료 `diagnosis_integrated_svc.run_diagnosis`

| Column | Value |
|--------|-------|
| `public_token` | `uuid4` |
| `input_data` | `{sector, tier_code, floor_area, contract_amount_eok, workers, factory_id?, company_id?}` |
| `partial_result` | `_build_partial(full_result)` |
| `full_result` | Layer 4 `result_data` |
| `expires_at` | 7 days if free else `None` |
| `status` | `"ACTIVE"` |
| `source_type` | `"free_diag"` or `"paid_diag"` |
| `engine_version` | param `engine_version` |
| `ci_hash`, `auth_log_id`, `disclaimer_log_id`, `tier_code`, `paid_amount`, `payment_ref` | from auth flow |

### 5.2 `_partial_from_full` vs `_build_partial`

| Key | `_partial_from_full` (anonymous) | `_build_partial` (integrated) |
|-----|----------------------------------|-------------------------------|
| `risk_level` | ✓ | ✓ |
| `summary` | ✓ | ✓ |
| `applicable_count` | ✓ | ✓ |
| `sector` | ✓ | ✓ |
| `key_obligations` | `[:6]` | `[:6]` |
| `law_badges` | `[:18]` | `[:18]` |
| `evaluated_at` | ✓ | — |
| `rules_preview` | `rules[:12]` | — |
| `construction_summary` | ✓ | — |
| `message` | fixed str | — |

### 5.3 Transform (`routers/diagnosis_transform.py`)

Read-only on `full_result` JSONB. No DB write.

#### `_extract_obligations(rd) -> list[dict]`

**Input scan order:** `obligations` → `key_obligations` → `mandatory_obligations` → `critical_obligations` (first non-empty list wins)

Fallback: `{cat_key}_items` or `{cat_label}_항목` for `CATEGORY_MAP` keys.

**Output item:**
```python
{
  "id": str,
  "category": str,           # normalized via CATEGORY_MAP
  "title": str,
  "risk_level": str,         # upper, default "MEDIUM"
  "description": str,
  "evidence": list,          # from obj["evidence"] or obj["legal_basis"]; str→[str]
  "action_url": Optional,
  "auto_schedulable": bool,
}
```

**Compiler `obligations` group wrapper:** first matching key is `obligations` (list of `{category, label, items}`). Transform iterates wrapper dicts — `title` defaults to `"의무사항"`, `evidence` → `[]` unless wrapper dict has `evidence` key.

**Compiler `key_obligations`:** `List[str]` — if `obligations` empty, strings become `{category:"서류", title:str, evidence:[]}`.

#### `_extract_headline(rd, rule_count) -> dict`

```python
{"summary": str, "severity": str}  # severity: CRITICAL|HIGH|MEDIUM|LOW
```

#### `_extract_exposure(rd, rule_count) -> dict`

```python
{"penalty_max_krw": int, "rule_count": int}
```

#### `_extract_roi(rd) -> Optional[dict]`

```python
{"penalty_max_krw": int, "subscription_annual_krw": int, "roi_ratio": float, "breakeven_days": int}
```
or `None` if `penalty == 0`

#### `_extract_inspection_schedule(rd) -> list[dict]`

```python
[{"month": int 1-12, "count": int, "items": list[str]}, ...]  # 12 months, missing filled count=0
```

Reads keys: `inspection_schedule`, `inspection_schedule_ready`, `inspection_schedule_summary` — Compiler `inspection_schedule_ready` is **object not list** → Transform returns 12 empty months.

#### `_extract_warnings(rd) -> list[dict]`

```python
[{"level": str, "message": str}, ...]
```

### 5.4 Nexas 정제 `build_nexas_run_response` (`/diagnosis/run` only)

`rules_table_to_obligations(full)` → flat list:
```python
{"title", "name", "obligation_name", "law_reference", "law", "category", "who", "what", "when"}
```

Response wrapper adds `data.obligations`, `data.results`, `data.items`, `data.paid_preview` (obligations[5:]), top-level `result` = full `result_data`.

---

## Layer [6] 출력 — GET 응답 JSON

### 6.1 `POST /anonymous-diagnosis` (즉시)

```python
{
  "status": "success",
  "publicToken": str,
  "partialResult": dict,      # _partial_from_full
  "hasFullResult": True,
  "expiresAt": str,
}
```

### 6.2 `GET /anonymous-diagnosis/{token}`

```python
{
  "status": "success",
  "data": {
    "publicToken": str,
    "partialResult": dict,
    "fullResult": dict | None,   # None unless canViewFull
    "canViewFull": bool,
    "claimed": bool,
    "expiresAt": str | None,
  }
}
```

`canViewFull`: `tai_legacy_public=1` OR (Bearer + `claimed_user_id == user.id`)

### 6.3 `GET /anonymous-diagnosis/{token}/transform`

```python
{
  "status": "success",
  "transform_version": str,      # TRANSFORM_VERSION "1.0.1"
  "source": "anonymous_token",
  "token": str,
  "sector": str,                 # normalize_sector_db applied
  "schema_version": "2026.04",
  "expires_at": str | None,
  "rule_count": int,
  "headline": {"summary": str, "severity": str},
  "obligations": [ObligationModel-shaped dicts],
  "warnings": [{"level", "message"}],
  "exposure": {"penalty_max_krw", "rule_count"},
  "inspection_schedule": [{"month", "count", "items"}],
  "roi": dict | None,
  "risk_summary": dict,
  "applicable_laws": list,
  "next_actions": list,
  "key_obligations": list[:10],
  "law_badges": list[:20],
  "input_data": {"site_kind", "scale", "workers", "region"},
}
```

### 6.4 `GET /anonymous-diagnosis/{token}/recommend-plan`

```python
{
  "status": "success",
  "version": str,
  "source": "anonymous_token",
  "token": str,
  "sector": str,
  "input_summary": {"severity", "obl_count", "workers"},
  "recommended": {
    "plan_code", "plan_name", "monthly_krw", "is_custom", "pricing_note"
  },
  "reasons": list,
  "alternatives": list,
  "comparison": dict,
  "cta": {"primary", "secondary", "signup"},
}
```

### 6.5 `POST /diagnosis/run` (Nexas)

`build_nexas_run_response` → §5.4 + top-level `public_token`, `diagnosis_id`, `tier_code`, `is_free`, `result`.

---

## Layer 간 인터페이스

### Layer 1 → Layer 2

```
DiagnoseStep1Body
  → _merge_body_input() → inp: Dict[str, Any]
  → _input_to_facility_context(sector_raw, inp) → facility_ctx: Dict[str, Any]
  → create_temp_factory: facility_ctx → factories row (subset, §2.1)
```

**`_input_to_facility_context` sector branches** (`services/legal_context.py`):

| Sector | Notable `ctx` keys populated |
|--------|------------------------------|
| `BUILDING` | `building_use_code`, `total_floor_area`, `building_area`, `floor_count`, `worker_count`, `electric_capacity`, `electrical_capacity_kw`, `has_high_pressure_gas`, `gas_capacity_*`, `has_hazardous_material`, `elevator_count`, `annual_energy_toe`, `has_boiler`, `boiler_capacity_kw` |
| `MANUFACTURING` | `ksic_code`, `worker_count`, `electric_capacity`, `electrical_capacity_kw`, `has_*` flags, `gas_*`, `building_area`, `total_floor_area`, `is_factory_registered` |
| `CONSTRUCTION` | `construction_amount`, `contract_amount` (= eok×1e8), `construction_type`, `worker_count`, `employee_count`, `direct_workers`, `subcon_workers`, `subcontractor_worker_count`, `has_tunnel_bridge`, `has_blasting`, `has_crane`, `has_high_work`, `electrical_capacity_kw`, `transformer_capacity_kva`, `safety_manager_threshold` |
| `SPECIAL_FACILITY` / `SPECIAL` | `building_use_code`←`facility_type`, `total_floor_area`, `building_area`, `hospital_beds`, `student_count`, `worker_count` |

`INDUSTRIAL` input sector → internally treated as `MANUFACTURING` in `_input_to_facility_context`.

**Gap:** `facility_ctx` keys not mapped to `factories` columns (§2.1) are unavailable to `FIELD_MAP` during `evaluate_single_factory`.

### Layer 2 → Layer 3

```
factories row (dict) + draft_slot groups
  → evaluate_draft_for_facility(facility, draft_id, numeric_slots, scope_slots)
  → (overall_status, part_id, check_results) | None
  → facility_applicability INSERT (filtered statuses)

factory_id
  → fetch_compiler_candidates
  → compiler dict (§3.6)
```

**`task_candidate` row** (as returned by SELECT): keys `id`, `task_type`, `source_action_family`, `obligation_family`, `applicability_status`, `status` — **no `factory_id` filter mismatch in code**; query uses `.eq("factory_id", fid)`.

### Layer 3 → Layer 4

```
compiler: Dict
  + sector_raw: str
  + facility_ctx: Dict
  + evaluated_at: str
  → _compiler_result_to_step1_format
  → result_data: Dict (§4.8)
```

Primary list driving rules: `compiler["task_candidates"]`; fallback: `compiler["applicability_candidates"]`.

### Layer 4 → Layer 5

```
result_data (Dict)
  → _partial_from_full / _build_partial → partial_result
  → anonymous_diagnosis_results.full_result (JSONB)

result_data
  → diagnosis_transform._extract_* (read full_result)
  → UI-facing sections (no schema mutation of stored JSON)
```

### Layer 5 → Layer 6

```
anonymous_diagnosis_results row
  → GET handlers read partial_result / full_result
  → optional transform/recommend-plan projection
```

---

## 부록: `_input_to_facility_context` 기본 `ctx` 초기값

All sectors start with zeros/empty for:

`worker_count`, `total_floor_area`, `electric_capacity`, `building_use_code`, `ksic_code`, `floor_count`, `construction_amount`, `contract_amount`, `is_hazardous_material`, `is_multi_use`, `is_factory_registered`, `has_high_pressure_gas`, `has_hazardous_material`, `has_chemical_substance`, `has_boiler`, `has_tunnel_bridge`, `hospital_beds`, `student_count`, `gas_capacity_kg`, `gas_capacity_m3`, `boiler_capacity_kw`, `elevator_count`, `annual_energy_toe`

---

## 부록: 별도 진입 경로 (본 6-Layer Orchestration 아님)

코드에 존재하나 `run_anonymous_diagnosis` 체인에 **포함되지 않음**:

| Entry | Service | Output storage |
|-------|---------|----------------|
| `POST /legal-engine/diagnose/step1` | `legal_v510_svc.run_diagnose_step1_v510` | `factory_diagnosis_results` |
| `POST /api/v1/diagnosis-engine/evaluate` | `DiagnosisService.evaluate` | `diagnosis_session`, `diagnosis_candidate`, … |

본 문서 Layer [1]–[6]는 **`run_anonymous_diagnosis` / `run_step1_via_compiler`** 기준.

---

*Analysis only. No code changes.*
