# TAI 백엔드 긴급 작업지시서
## 법령진단 3단계 재구성

> 우선순위: 🔴 긴급  
> 작성일: 2026-03-29  
> 레포: taiengineering/tai-api

---

## 작업 순서 (반드시 이 순서대로)

```
STEP 1 → DB 컬럼 추가 (apply_migration)
STEP 2 → 신규 테이블 2개 생성 (apply_migration)
STEP 3 → 기존 룰 마이그레이션 (execute_sql)
STEP 4 → legal_engine.py 신규 API 구현
STEP 5 → main.py 라우터 등록
STEP 6 → Railway 배포 확인
```

---

## STEP 1. master_building_legal_rules 컬럼 추가

```sql
ALTER TABLE master_building_legal_rules
  ADD COLUMN IF NOT EXISTS sector            VARCHAR(30),
  ADD COLUMN IF NOT EXISTS diagnosis_stage   SMALLINT DEFAULT 1,
  ADD COLUMN IF NOT EXISTS obligation_summary TEXT,
  ADD COLUMN IF NOT EXISTS penalty_summary    TEXT,
  ADD COLUMN IF NOT EXISTS source_api         VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_mblr_sector ON master_building_legal_rules(sector);
CREATE INDEX IF NOT EXISTS idx_mblr_stage  ON master_building_legal_rules(diagnosis_stage);
```

---

## STEP 2. 신규 테이블 생성

```sql
-- 진단 결과 이력
CREATE TABLE IF NOT EXISTS factory_diagnosis_results (
  id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  factory_id      UUID REFERENCES factories(id) ON DELETE CASCADE,
  sector          VARCHAR(30) NOT NULL,
  diagnosis_stage SMALLINT NOT NULL,
  input_data      JSONB,
  result_data     JSONB,
  rule_count      INTEGER DEFAULT 0,
  is_latest       BOOLEAN DEFAULT true,
  created_by      UUID,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fdr_factory_id ON factory_diagnosis_results(factory_id);
CREATE INDEX IF NOT EXISTS idx_fdr_latest     ON factory_diagnosis_results(factory_id, is_latest);

-- 룰별 적용 결과
CREATE TABLE IF NOT EXISTS diagnosis_rule_results (
  id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  diagnosis_id  UUID REFERENCES factory_diagnosis_results(id) ON DELETE CASCADE,
  rule_code     VARCHAR(50),
  rule_name     TEXT,
  law_name      TEXT,
  law_article   TEXT,
  obligation    TEXT,
  due_date      DATE,
  status        VARCHAR(20) DEFAULT 'PENDING',
  form_code     VARCHAR(30),
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_drr_diagnosis_id ON diagnosis_rule_results(diagnosis_id);
```

---

## STEP 3. 기존 룰 마이그레이션 (396개 → sector/stage 설정)

```sql
-- 기존 396개 룰 전부 BUILDING / stage=1 로 설정
UPDATE master_building_legal_rules
SET
  sector          = 'BUILDING',
  diagnosis_stage = 1
WHERE sector IS NULL;

-- 확인
SELECT sector, diagnosis_stage, COUNT(*)
FROM master_building_legal_rules
GROUP BY sector, diagnosis_stage;
```

---

## STEP 4. legal_engine.py — 3단계 진단 API 추가

### 파일 위치: routers/legal_engine.py

기존 파일에 아래 엔드포인트를 **추가**합니다.
(기존 POST /legal-engine/apply/{factory_id} 는 유지)

---

### 4-1. 헬퍼 함수 추가

```python
# legal_engine.py 상단 import에 추가
from datetime import date, timedelta

def _evaluate_condition(rule: dict, input_data: dict) -> bool:
    """
    룰의 조건을 평가하여 True/False 반환.
    condition_1 은 필수, condition_2 는 있을 경우에만 평가.
    """
    def check(field, operator, value, data):
        if not field or field not in data:
            return True  # 해당 필드 없으면 조건 스킵
        actual = data[field]
        if actual is None:
            return False
        try:
            if operator == '>=':
                return float(actual) >= float(value)
            elif operator == '<=':
                return float(actual) <= float(value)
            elif operator == '>':
                return float(actual) > float(value)
            elif operator == '<':
                return float(actual) < float(value)
            elif operator == '==':
                return str(actual) == str(value)
            elif operator == 'IN':
                vals = [v.strip() for v in str(value).split(',')]
                return str(actual) in vals
            elif operator == 'NOT_IN':
                vals = [v.strip() for v in str(value).split(',')]
                return str(actual) not in vals
            elif operator == '==true':
                return actual is True or str(actual).lower() == 'true'
            elif operator == '==false':
                return actual is False or str(actual).lower() == 'false'
        except Exception:
            return False
        return True

    # condition_1
    c1_ok = check(
        rule.get('condition_1_field'),
        rule.get('condition_1_operator'),
        rule.get('condition_1_value'),
        input_data
    )
    if not c1_ok:
        return False

    # condition_2 (있을 경우만)
    c2_field = rule.get('condition_2_field')
    if c2_field:
        c2_ok = check(
            c2_field,
            rule.get('condition_2_operator'),
            rule.get('condition_2_value'),
            input_data
        )
        mode = rule.get('condition_mode', 'AND')
        if mode == 'AND' and not c2_ok:
            return False
        if mode == 'OR' and not (c1_ok or c2_ok):
            return False

    return True


def _determine_risk_level(rule_count: int) -> str:
    if rule_count >= 10:
        return 'HIGH'
    elif rule_count >= 5:
        return 'MEDIUM'
    return 'LOW'


def _save_diagnosis_result(
    supabase, factory_id: str, sector: str, stage: int,
    input_data: dict, matched_rules: list
) -> dict:
    """진단 결과 저장. 이전 최신 결과는 is_latest=False 로 변경."""
    # 기존 최신 결과 무효화
    supabase.table('factory_diagnosis_results').update(
        {'is_latest': False}
    ).eq('factory_id', factory_id).eq('is_latest', True).execute()

    # 결과 요약 생성
    law_categories = list(dict.fromkeys(
        r['law_name'] for r in matched_rules if r.get('law_name')
    ))
    key_obligations = [
        r.get('obligation_summary') or r.get('rule_name', '')
        for r in matched_rules[:5]
    ]
    has_appointment = any(
        r.get('rule_type') == 'APPOINTMENT' for r in matched_rules
    )

    result_data = {
        'applicable_law_categories': law_categories,
        'appointment_required': has_appointment,
        'key_obligations': key_obligations,
        'risk_level': _determine_risk_level(len(matched_rules)),
        'rules': [
            {
                'rule_code': r.get('rule_code'),
                'rule_name': r.get('rule_name'),
                'law_name':  r.get('law_name'),
                'law_article': r.get('law_article'),
                'obligation': r.get('obligation_summary') or r.get('rule_name'),
                'rule_type': r.get('rule_type'),
                'stage': r.get('diagnosis_stage', 1),
            }
            for r in matched_rules
        ]
    }

    res = supabase.table('factory_diagnosis_results').insert({
        'factory_id':      factory_id,
        'sector':          sector,
        'diagnosis_stage': stage,
        'input_data':      input_data,
        'result_data':     result_data,
        'rule_count':      len(matched_rules),
        'is_latest':       True,
    }).execute()

    return res.data[0] if res.data else {}


def _create_report_events_from_rules(
    supabase, factory_id: str, matched_rules: list
):
    """REPORT / APPOINTMENT 타입 룰에서 report_events 자동 생성."""
    event_types = {'REPORT', 'APPOINTMENT', 'NOTIFICATION'}
    for rule in matched_rules:
        if rule.get('rule_type') not in event_types:
            continue
        form_code = rule.get('form_code')
        if not form_code:
            continue
        due_days = rule.get('due_days') or 14
        due_date = (date.today() + timedelta(days=due_days)).isoformat()
        # 중복 방지: 같은 factory+form_code+PENDING 있으면 스킵
        existing = supabase.table('report_events').select('id') \
            .eq('factory_id', factory_id) \
            .eq('form_code', form_code) \
            .eq('status', 'PENDING').execute()
        if existing.data:
            continue
        supabase.table('report_events').insert({
            'factory_id':   factory_id,
            'rule_code':    rule.get('rule_code'),
            'form_code':    form_code,
            'trigger_date': date.today().isoformat(),
            'due_date':     due_date,
            'status':       'PENDING',
        }).execute()
```

---

### 4-2. 1단계 진단 API

```python
@router.post("/diagnose/step1")
def diagnose_step1(body: dict):
    """
    1단계 기초 진단.
    섹터 선택 + 기초 정보 입력 → 주요 법령 카테고리 + 선임 의무 판정.
    무료 제공.
    """
    supabase = get_supabase()

    factory_id = body.get('factory_id')
    sector     = body.get('sector', 'BUILDING')  # BUILDING/MANUFACTURING/CONSTRUCTION/SPECIAL_FACILITY
    input_data = body.get('input', {})

    if not factory_id:
        raise HTTPException(status_code=400, detail='factory_id 필수')
    if sector not in ('BUILDING', 'MANUFACTURING', 'CONSTRUCTION', 'SPECIAL_FACILITY'):
        raise HTTPException(status_code=400, detail='유효하지 않은 sector 값')

    # input_data에 sector 추가 (조건 평가용)
    input_data['sector'] = sector

    # 1단계(stage=1) 룰 조회
    res = supabase.table('master_building_legal_rules').select('*') \
        .eq('sector', sector) \
        .eq('diagnosis_stage', 1) \
        .eq('is_active', True) \
        .execute()

    rules = res.data or []

    # 조건 평가
    matched = [r for r in rules if _evaluate_condition(r, input_data)]

    # 결과 저장
    diagnosis = _save_diagnosis_result(
        supabase, factory_id, sector, 1, input_data, matched
    )

    # report_events 생성 (신고 의무 룰만)
    _create_report_events_from_rules(supabase, factory_id, matched)

    result = diagnosis.get('result_data', {})
    return {
        'status':       'success',
        'diagnosis_id': diagnosis.get('id'),
        'stage':        1,
        'sector':       sector,
        'rule_count':   len(matched),
        'summary': {
            'applicable_law_categories': result.get('applicable_law_categories', []),
            'appointment_required':      result.get('appointment_required', False),
            'key_obligations':           result.get('key_obligations', []),
            'risk_level':                result.get('risk_level', 'LOW'),
        },
        'rules': result.get('rules', []),
    }
```

---

### 4-3. 2단계 진단 API

```python
@router.post("/diagnose/step2")
def diagnose_step2(body: dict):
    """
    2단계 공정 진단.
    1단계 결과 + 공정 선택 → 법령별 의무 목록 + 신고 일정.
    유료.
    """
    supabase = get_supabase()

    factory_id   = body.get('factory_id')
    diagnosis_id = body.get('diagnosis_id')  # 1단계 diagnosis_id
    processes    = body.get('processes', [])  # 공정 코드 목록
    construction_types = body.get('construction_types', [])

    if not factory_id:
        raise HTTPException(status_code=400, detail='factory_id 필수')

    # 기존 1단계 결과 조회 (sector, input_data 가져오기)
    prev = None
    if diagnosis_id:
        prev_res = supabase.table('factory_diagnosis_results').select('*') \
            .eq('id', diagnosis_id).single().execute()
        prev = prev_res.data

    sector     = (prev or {}).get('sector', 'MANUFACTURING')
    input_data = (prev or {}).get('input_data', {})
    input_data['processes']         = processes
    input_data['construction_types'] = construction_types

    # 2단계(stage<=2) 룰 조회 (1단계 포함)
    res = supabase.table('master_building_legal_rules').select('*') \
        .eq('sector', sector) \
        .lte('diagnosis_stage', 2) \
        .eq('is_active', True) \
        .execute()

    rules   = res.data or []
    matched = [r for r in rules if _evaluate_condition(r, input_data)]

    diagnosis = _save_diagnosis_result(
        supabase, factory_id, sector, 2, input_data, matched
    )
    _create_report_events_from_rules(supabase, factory_id, matched)

    # 1단계 대비 추가된 룰
    prev_codes = set()
    if prev:
        prev_rules = (prev.get('result_data') or {}).get('rules', [])
        prev_codes = {r.get('rule_code') for r in prev_rules}
    added = [r for r in matched if r.get('rule_code') not in prev_codes]

    result = diagnosis.get('result_data', {})
    return {
        'status':       'success',
        'diagnosis_id': diagnosis.get('id'),
        'stage':        2,
        'sector':       sector,
        'rule_count':   len(matched),
        'added_rule_count': len(added),
        'summary': {
            'applicable_law_categories': result.get('applicable_law_categories', []),
            'appointment_required':      result.get('appointment_required', False),
            'key_obligations':           result.get('key_obligations', []),
            'risk_level':                result.get('risk_level', 'LOW'),
        },
        'rules':       result.get('rules', []),
        'added_rules': [
            {'rule_code': r.get('rule_code'), 'rule_name': r.get('rule_name'),
             'law_article': r.get('law_article')}
            for r in added
        ],
    }
```

---

### 4-4. 3단계 진단 API (설비 법정검사 일정)

```python
@router.post("/diagnose/step3")
def diagnose_step3(body: dict):
    """
    3단계 설비 진단.
    2단계 결과 + 설비 등록 → 설비별 법정검사 일정 생성.
    유료.
    """
    supabase    = get_supabase()
    factory_id  = body.get('factory_id')
    diagnosis_id = body.get('diagnosis_id')
    equipments  = body.get('equipments', [])  # [{equipment_code, capacity, unit, installed_date, last_inspection_date}]

    if not factory_id:
        raise HTTPException(status_code=400, detail='factory_id 필수')

    # 이전 결과
    prev = None
    if diagnosis_id:
        prev_res = supabase.table('factory_diagnosis_results').select('*') \
            .eq('id', diagnosis_id).single().execute()
        prev = prev_res.data

    sector     = (prev or {}).get('sector', 'MANUFACTURING')
    input_data = (prev or {}).get('input_data', {})
    input_data['equipments'] = equipments

    # 3단계 룰 (stage<=3 전체)
    res = supabase.table('master_building_legal_rules').select('*') \
        .eq('sector', sector) \
        .lte('diagnosis_stage', 3) \
        .eq('is_active', True) \
        .execute()

    rules   = res.data or []
    matched = [r for r in rules if _evaluate_condition(r, input_data)]
    diagnosis = _save_diagnosis_result(
        supabase, factory_id, sector, 3, input_data, matched
    )

    # 설비별 법정검사 일정 계산
    inspection_schedules = []
    today = date.today()
    for equip in equipments:
        eq_code = equip.get('equipment_code', '')
        last_dt = equip.get('last_inspection_date')
        cycle_years = 2  # 기본값 2년 (추후 DB에서 조회)
        if last_dt:
            last = date.fromisoformat(last_dt)
            next_due = date(last.year + cycle_years, last.month, last.day)
            days_left = (next_due - today).days
            inspection_schedules.append({
                'equipment_code':      eq_code,
                'capacity':            equip.get('capacity'),
                'unit':                equip.get('unit'),
                'last_inspection_date': last_dt,
                'next_due_date':       next_due.isoformat(),
                'cycle_years':         cycle_years,
                'days_left':           days_left,
                'status': 'OVERDUE' if days_left < 0
                          else ('URGENT' if days_left <= 30 else 'NORMAL'),
            })

    overdue_count  = sum(1 for s in inspection_schedules if s['status'] == 'OVERDUE')
    upcoming_count = sum(1 for s in inspection_schedules if s['status'] == 'URGENT')

    return {
        'status':               'success',
        'diagnosis_id':         diagnosis.get('id'),
        'stage':                3,
        'sector':               sector,
        'rule_count':           len(matched),
        'inspection_schedules': inspection_schedules,
        'overdue_count':        overdue_count,
        'upcoming_count':       upcoming_count,
    }
```

---

### 4-5. 결과 조회 API

```python
@router.get("/diagnose/{factory_id}/latest")
def get_latest_diagnosis(factory_id: str):
    """최신 진단 결과 조회"""
    supabase = get_supabase()
    res = supabase.table('factory_diagnosis_results').select('*') \
        .eq('factory_id', factory_id) \
        .eq('is_latest', True) \
        .single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail='진단 결과 없음')
    return {'status': 'success', 'data': res.data}


@router.get("/diagnose/{factory_id}/history")
def get_diagnosis_history(
    factory_id: str,
    page: int = 1, page_size: int = 10
):
    """진단 이력 목록"""
    supabase = get_supabase()
    offset = (page - 1) * page_size
    res = supabase.table('factory_diagnosis_results').select(
        'id, sector, diagnosis_stage, rule_count, is_latest, created_at',
        count='exact'
    ).eq('factory_id', factory_id) \
     .order('created_at', desc=True) \
     .range(offset, offset + page_size - 1).execute()
    return {
        'status': 'success',
        'data': {
            'items':     res.data or [],
            'total':     res.count or 0,
            'page':      page,
            'page_size': page_size,
        }
    }
```

---

## STEP 5. main.py 라우터 접두사 확인

기존 legal_engine 라우터에 접두사 `/legal-engine` 이 있는지 확인.
없으면 아래처럼 등록:

```python
from routers import legal_engine
app.include_router(legal_engine.router, prefix="/legal-engine")
```

> legal_engine.router 내부에 `prefix="/legal-engine"` 이 있다면 main.py에서 prefix 중복 금지.

---

## STEP 6. 테스트

```bash
# DB 확인
SELECT column_name FROM information_schema.columns
WHERE table_name = 'master_building_legal_rules'
AND column_name IN ('sector','diagnosis_stage','obligation_summary','penalty_summary');

# 마이그레이션 확인
SELECT sector, diagnosis_stage, COUNT(*)
FROM master_building_legal_rules GROUP BY 1,2;

# API 확인 (Railway 배포 후)
curl -X POST https://api.taieng.co.kr/legal-engine/diagnose/step1 \
  -H 'Content-Type: application/json' \
  -d '{
    "factory_id": "<실제 factory UUID>",
    "sector": "BUILDING",
    "input": {
      "building_use_category": "업무시설",
      "gross_floor_area": 5000,
      "above_ground_floors": 8,
      "worker_count": 50,
      "electric_capacity_kw": 200
    }
  }'
```

---

## 완료 체크리스트

```
□ STEP 1: master_building_legal_rules 컬럼 4개 추가 확인
□ STEP 2: factory_diagnosis_results 테이블 생성
□ STEP 2: diagnosis_rule_results 테이블 생성
□ STEP 3: 기존 396개 룰 sector=BUILDING, stage=1 업데이트 확인
□ STEP 4: legal_engine.py 헬퍼 함수 추가
□ STEP 4: POST /diagnose/step1 구현
□ STEP 4: POST /diagnose/step2 구현
□ STEP 4: POST /diagnose/step3 구현
□ STEP 4: GET /diagnose/{id}/latest 구현
□ STEP 4: GET /diagnose/{id}/history 구현
□ STEP 5: main.py 라우터 확인
□ STEP 6: Railway 배포 완료
□ STEP 6: step1 API 200 응답 확인
```

---

## 참고: sector별 핵심 입력 변수

| sector | 입력 변수 (input 객체 키) |
|--------|------------------------|
| BUILDING | building_use_category, gross_floor_area, above_ground_floors, worker_count, electric_capacity_kw, has_hazardous_material, has_high_pressure_gas |
| MANUFACTURING | ksic_lv1_code, worker_count, gross_floor_area, has_hazardous_material, has_high_pressure_gas, has_chemical_substance, has_boiler, electric_capacity_kw |
| CONSTRUCTION | contract_amount, worker_count, construction_type, has_tunnel_bridge |
| SPECIAL_FACILITY | facility_type, gross_floor_area, hospital_beds, student_count, worker_count |
