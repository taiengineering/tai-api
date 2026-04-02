# 작업지시서 — 건설 섹터 입력값 정비 v5.4.0

생성일: 2026-04-02  
대상 파일: `routers/legal_engine.py`  
현재 버전: v5.3.1  
목표 버전: v5.4.0

---

## 수정 1: ENGINE_VERSION

```python
# 변경 전
ENGINE_VERSION = "5.3.1"  # v5.3.1: WORK_ORDER_20260402

# 변경 후
ENGINE_VERSION = "5.4.0"  # v5.4.0: 건설 섹터 입력값 정비
```

---

## 수정 2: DiagnoseStep1Body — 건설 전용 필드 추가

현재 `DiagnoseStep1Body`에 건설 전용 필드가 없어 `input` dict에 숨겨서만 전달 가능.  
Pydantic 명시적 필드로 추가하여 API 스펙을 명확히 한다.

```python
# 변경 전
class DiagnoseStep1Body(BaseModel):
    factory_id: Optional[str] = Field(None, description="factories.id (없으면 익명 진단)")
    sector: str = Field(..., description="BUILDING | MANUFACTURING | CONSTRUCTION | SPECIAL_FACILITY")
    input: Optional[Dict[str, Any]] = Field(default_factory=dict)

    building_use_type: Optional[str] = None
    employee_count: Optional[int] = None
    floor_area: Optional[float] = None
    worker_count: Optional[int] = None
    total_floor_area: Optional[float] = None
    electric_capacity: Optional[float] = None
    floor_count: Optional[int] = None
    contract_amount_eok: Optional[float] = None
    ksic_major: Optional[str] = None
    facility_type: Optional[str] = None

# 변경 후
class DiagnoseStep1Body(BaseModel):
    factory_id: Optional[str] = Field(None, description="factories.id (없으면 익명 진단)")
    sector: str = Field(..., description="BUILDING | MANUFACTURING | CONSTRUCTION | SPECIAL_FACILITY")
    input: Optional[Dict[str, Any]] = Field(default_factory=dict)

    # 공통
    building_use_type: Optional[str] = None
    employee_count: Optional[int] = None
    floor_area: Optional[float] = None
    worker_count: Optional[int] = None
    total_floor_area: Optional[float] = None
    electric_capacity: Optional[float] = None
    floor_count: Optional[int] = None
    contract_amount_eok: Optional[float] = None
    ksic_major: Optional[str] = None
    facility_type: Optional[str] = None

    # v5.4.0: CONSTRUCTION 전용 명시적 필드
    construction_type: Optional[str] = Field(None, description="건축 | 토목 | 공통 | 기타")
    direct_workers: Optional[int] = Field(None, description="직영 근로자 수")
    subcon_workers: Optional[int] = Field(None, description="하도급 근로자 수 (산안법 시행령 제16조③ 포함)")
    electrical_capacity_kw: Optional[float] = Field(None, description="임시전기 설비 용량(kW) — 75kW 이상 시 전기안전관리자 선임")
    has_tunnel_bridge: Optional[bool] = Field(None, description="터널·교량 공사 포함 여부")
    has_blasting: Optional[bool] = Field(None, description="발파 작업 포함 여부")
    has_crane: Optional[bool] = Field(None, description="크레인 사용 여부")
```

---

## 수정 3: diagnose_step1 내 flat_fields 딕셔너리에 건설 전용 필드 추가

`diagnose_step1` 함수 안에서 `flat_fields` 딕셔너리를 만드는 곳:

```python
# 변경 전
    flat_fields = {
        "building_use_type": body.building_use_type,
        "employee_count":    body.employee_count,
        "floor_area":        body.floor_area,
        "worker_count":      body.worker_count,
        "total_floor_area":  body.total_floor_area,
        "electric_capacity": body.electric_capacity,
        "floor_count":       body.floor_count,
        "contract_amount_eok": body.contract_amount_eok,
        "ksic_major":        body.ksic_major,
        "facility_type":     body.facility_type,
    }

# 변경 후
    flat_fields = {
        "building_use_type":     body.building_use_type,
        "employee_count":        body.employee_count,
        "floor_area":            body.floor_area,
        "worker_count":          body.worker_count,
        "total_floor_area":      body.total_floor_area,
        "electric_capacity":     body.electric_capacity,
        "floor_count":           body.floor_count,
        "contract_amount_eok":   body.contract_amount_eok,
        "ksic_major":            body.ksic_major,
        "facility_type":         body.facility_type,
        # v5.4.0: CONSTRUCTION 전용
        "construction_type":     body.construction_type,
        "direct_workers":        body.direct_workers,
        "subcon_workers":        body.subcon_workers,
        "electrical_capacity_kw": body.electrical_capacity_kw,
        "has_tunnel_bridge":     body.has_tunnel_bridge,
        "has_blasting":          body.has_blasting,
        "has_crane":             body.has_crane,
    }
```

---

## 수정 4: _input_to_facility_context — CONSTRUCTION 분기에 전기·작업 추가

`_input_to_facility_context` 함수의 `elif sec == "CONSTRUCTION":` 분기 내부.

현재 `has_tunnel_bridge` 바로 아래, `fake_factory = ...` 바로 위에 추가:

```python
# 변경 전 (기존 코드 발췌)
        ctx["has_tunnel_bridge"] = 1 if _truthy(inp.get("has_tunnel_bridge")) else 0

        fake_factory = {"construction_type": site_type}

# 변경 후
        ctx["has_tunnel_bridge"] = 1 if _truthy(inp.get("has_tunnel_bridge")) else 0
        ctx["has_blasting"]      = 1 if _truthy(inp.get("has_blasting"))      else 0  # v5.4.0
        ctx["has_crane"]         = 1 if _truthy(inp.get("has_crane"))          else 0  # v5.4.0

        # v5.4.0: 건설현장 임시전기 용량 파싱
        # condition_code=electrical_capacity_kw, value=75 룰 (CONST-007) 트리거용
        elec_kw = float(
            inp.get("electrical_capacity_kw")
            or inp.get("electric_capacity")
            or 0
        )
        ctx["electric_capacity"]        = elec_kw
        ctx["electrical_capacity_kw"]   = elec_kw
        ctx["transformer_capacity_kva"] = elec_kw

        fake_factory = {"construction_type": site_type}
```

---

## 수정 5: _get_construction_summary — 억 단위 표기 버그 수정

```python
# 변경 전
    basis_parts = [f"{site_label} {int(threshold/100_000_000)}억원 {_cmp_label}"]
    # 결과: 1_500_000_000 / 100_000_000 = 15 → "건축 15억원" (오류)

# 변경 후
    _threshold_eok = int(threshold / 10_000_000)
    basis_parts = [f"{site_label} {_threshold_eok}억원 {_cmp_label}"]
    # 결과: 1_500_000_000 / 10_000_000 = 150 → "건축 150억원" (정확)
```

---

## 수정 6: diagnose_step2 — factory_id 없어도 동작 (익명 진단 지원)

step1은 factory_id 없는 익명 진단 가능한데 step2는 factory_id 필수여서 흐름이 끊김.

```python
# 변경 전
    if not factory_id:
        raise HTTPException(status_code=400, detail='factory_id 필수')

# 변경 후 (세 줄 제거, 이후 factory_id 있을 때만 저장하도록)
    # factory_id 없으면 저장 스킵 (익명 진단 지원)
    # 아래 _save_diagnosis_result 호출 부분 조건부 처리:

    # 기존:
    diagnosis = _save_diagnosis_result(supabase, factory_id, sector, 2, input_data, matched)
    _create_report_events_from_rules(supabase, factory_id, matched)

    # 변경:
    diagnosis = {}
    if factory_id:
        diagnosis = _save_diagnosis_result(supabase, factory_id, sector, 2, input_data, matched)
        _create_report_events_from_rules(supabase, factory_id, matched)
```

또한 `sector` 기본값도 수정:
```python
# 변경 전
    sector = (prev or {}).get('sector', 'MANUFACTURING')

# 변경 후
    sector = (prev or {}).get('sector', body.get('sector', 'CONSTRUCTION'))
```

---

## 수정 7: diagnose_step3 — inspection_schedules 하드코딩 2년 제거

```python
# 변경 전
    for equip in equipments:
        eq_code = equip.get('equipment_code', '')
        last_dt = equip.get('last_inspection_date')
        cycle_years = 2
        if last_dt:
            try:
                last      = date.fromisoformat(last_dt)
                next_due  = date(last.year + cycle_years, last.month, last.day)
                days_left = (next_due - today).days
                inspection_schedules.append({
                    ...
                    'next_due_date':        next_due.isoformat(),
                    'cycle_years':          cycle_years,
                    ...
                })

# 변경 후: extra_equipment_codes에서 실제 DB 점검주기 조회 후 사용
    # inspection_schedules 생성 루프 바로 앞에 추가:
    eq_cycle_map: Dict[str, Dict] = {}
    if extra_equipment_codes:
        try:
            cycle_res = supabase.table('master_building_legal_rules') \
                .select('construction_work_type, inspection_cycle_value, inspection_cycle_unit_code') \
                .eq('sector', sector) \
                .eq('diagnosis_stage', 3) \
                .eq('obligation_type', 'INSPECT') \
                .in_('construction_work_type', extra_equipment_codes) \
                .eq('is_active', True) \
                .execute()
            for r in (cycle_res.data or []):
                ec = r.get('construction_work_type')
                if ec and ec not in eq_cycle_map:
                    unit_code = str(r.get('inspection_cycle_unit_code') or '')
                    if unit_code in CYCLE_CODE_MAP:
                        cycle_unit, cycle_val = CYCLE_CODE_MAP[unit_code]
                    else:
                        cycle_unit, cycle_val = 'year', int(r.get('inspection_cycle_value') or 2)
                    eq_cycle_map[ec] = {'unit': cycle_unit, 'value': cycle_val}
        except Exception as e:
            print(f"[STEP3] 장비 점검주기 조회 실패: {e}")

    # 루프 안에서:
    for equip in equipments:
        eq_code = equip.get('equipment_code', '')
        last_dt = equip.get('last_inspection_date')

        # DB에서 조회한 실제 주기 사용, 없으면 2년 기본값
        cycle_info = eq_cycle_map.get(eq_code, {'unit': 'year', 'value': 2})
        cycle_unit  = cycle_info['unit']
        cycle_value = cycle_info['value']

        if last_dt:
            try:
                last = date.fromisoformat(last_dt)
                if cycle_unit == 'year':
                    next_due = date(last.year + cycle_value, last.month, last.day)
                elif cycle_unit == 'month':
                    total_months = last.month + cycle_value
                    y = last.year + (total_months - 1) // 12
                    m = (total_months - 1) % 12 + 1
                    next_due = date(y, m, last.day)
                elif cycle_unit == 'day':
                    next_due = last + timedelta(days=cycle_value)
                else:
                    next_due = date(last.year + 2, last.month, last.day)

                days_left = (next_due - today).days
                inspection_schedules.append({
                    'equipment_code':       eq_code,
                    'capacity':             equip.get('capacity'),
                    'unit':                 equip.get('unit'),
                    'last_inspection_date': last_dt,
                    'next_due_date':        next_due.isoformat(),
                    'cycle_unit':           cycle_unit,
                    'cycle_value':          cycle_value,
                    'days_left':            days_left,
                    'status': 'OVERDUE' if days_left < 0 else ('URGENT' if days_left <= 30 else 'NORMAL'),
                })
            except Exception:
                pass
```

---

## 완료 후 확인

Railway 배포 완료 후 버전 확인:
```
GET https://api.taieng.co.kr/ → version: 5.4.0
```

테스트 — 임시전기 75kW 추가 시 전기안전관리자 선임 확인:
```json
POST /legal-engine/diagnose/step1
{
  "sector": "CONSTRUCTION",
  "input": {
    "construction_type": "건축",
    "contract_amount_eok": 150,
    "direct_workers": 30,
    "subcon_workers": 30,
    "electrical_capacity_kw": 75
  }
}
→ appointment에 전기안전관리자 포함 확인
```

테스트 — 억 단위 표기 확인:
```json
→ construction_summary.safety_manager_basis: "건축 150억원 이상" (기존: 15억원)
```
