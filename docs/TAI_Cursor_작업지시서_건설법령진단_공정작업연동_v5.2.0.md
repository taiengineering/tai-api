# Cursor 작업지시서 — 건설 법령진단 공정·작업 연계 (legal_engine.py v5.2.0)

> 파일: `routers/legal_engine.py`  
> 목표: 건설 섹터 2단계(공정), 3단계(작업+설비) KCSC 연동

---

## 배경

시설 섹터와 동일하게 건설 섹터도 공정·작업 선택 → 법령 자동 판정 필요.

**현재 구조 (v5.1.0)**
- step2: construction_work_types 배열 직접 입력 → 공종 필터
- step3: equipments 배열 직접 입력 → 설비 필터

**변경 (v5.2.0)**
- step2: KCSC kcsc_process_ids 배열 입력 → DB에서 work_type_code 자동 조회 → 법령 필터
- step3: construction_work_ids (PTW 작업 ID) → DB에서 equipment_type_codes 자동 조회 → 법령 필터
- 기존 직접 입력 방식도 하위 호환 유지

---

## DB 구조 (이미 완료됨)

```sql
-- kcsc_process_master
work_type_code  TEXT  -- EXCAVATION / FORMWORK / ... / NULL(미매핑)
work_type_label TEXT
risk_level      TEXT  -- LOW / MEDIUM / HIGH

-- kcsc_work_master  
equipment_type_codes TEXT[]  -- ['TCR','MCR'] 등
work_type_code       TEXT    -- 오버라이드용
```

---

## 수정 1. diagnose/step2 — KCSC 공정 ID → work_type 자동 조회

`diagnose_step2` 함수에서 아래 로직 추가:

```python
@router.post("/diagnose/step2")
def diagnose_step2(body: dict):
    supabase = get_supabase()
    factory_id = body.get('factory_id')
    diagnosis_id = body.get('diagnosis_id')
    processes = body.get('processes', [])
    construction_types = body.get('construction_types', [])
    
    # v5.2.0: KCSC 공정 ID 배열 → work_type_code 자동 조회
    kcsc_process_ids: List[str] = body.get('kcsc_process_ids') or []
    work_types: List[str] = body.get('construction_work_types') or []  # 기존 방식 하위호환
    
    # KCSC process_id → work_type_code 변환
    if kcsc_process_ids:
        kcsc_res = supabase.table('kcsc_process_master') \
            .select('id, process_name, work_type_code, work_type_label, risk_level') \
            .in_('id', kcsc_process_ids) \
            .eq('is_active', True) \
            .execute()
        kcsc_processes = kcsc_res.data or []
        
        # work_type_code 추출 (NULL 제외, 중복 제거)
        kcsc_work_types = list(set(
            p['work_type_code'] for p in kcsc_processes 
            if p.get('work_type_code')
        ))
        # 기존 직접 입력 + KCSC 조회 합산
        work_types = list(set(work_types + kcsc_work_types))
        
        # 응답에 포함할 공정 정보 저장
        input_data['kcsc_processes'] = kcsc_processes
        input_data['kcsc_process_ids'] = kcsc_process_ids
    
    # 기존 쿼리 로직 그대로 유지
    # ... (work_types 기반 필터링)
    
    # 응답에 kcsc_process_summary 추가
    kcsc_summary = []
    if kcsc_process_ids and kcsc_processes:
        for p in kcsc_processes:
            kcsc_summary.append({
                'process_id': p['id'],
                'process_name': p['process_name'],
                'work_type_code': p.get('work_type_code'),
                'work_type_label': p.get('work_type_label'),
                'risk_level': p.get('risk_level', 'MEDIUM'),
                'has_legal_rules': p.get('work_type_code') is not None,
            })
    
    return {
        'status': 'success',
        'diagnosis_id': diagnosis.get('id'),
        'stage': 2,
        'engine_version': ENGINE_VERSION,
        'sector': sector,
        'rule_count': len(matched),
        'added_rule_count': len(added),
        'kcsc_process_ids': kcsc_process_ids,
        'kcsc_process_summary': kcsc_summary,   # 신규
        'filtered_by_work_types': work_types if work_types else None,
        'work_type_summary': work_type_summary if work_types else None,
        'summary': { ... },
        'rules': result.get('rules', []),
        'added_rules': [...],
    }
```

---

## 수정 2. diagnose/step3 — PTW 작업 ID → 설비 코드 자동 조회

```python
@router.post("/diagnose/step3")
def diagnose_step3(body: dict):
    supabase = get_supabase()
    factory_id = body.get('factory_id')
    diagnosis_id = body.get('diagnosis_id')
    equipments = body.get('equipments', [])  # 기존 방식 하위호환
    
    # v5.2.0: construction_work_ids (PTW 작업) → equipment_type_codes 자동 조회
    construction_work_ids: List[str] = body.get('construction_work_ids') or []
    kcsc_work_ids: List[str] = body.get('kcsc_work_ids') or []  # KCSC 작업 마스터 ID
    
    extra_equipment_codes: List[str] = []
    work_legal_summary = []
    
    # PTW 등록 작업 → 설비 코드 조회
    if construction_work_ids:
        # construction_works 테이블에서 kcsc_work_id 조회
        ptw_res = supabase.table('construction_works') \
            .select('id, work_name, kcsc_work_id') \
            .in_('id', construction_work_ids) \
            .execute()
        ptw_works = ptw_res.data or []
        kcsc_work_ids_from_ptw = [
            w['kcsc_work_id'] for w in ptw_works if w.get('kcsc_work_id')
        ]
        kcsc_work_ids = list(set(kcsc_work_ids + kcsc_work_ids_from_ptw))
    
    # KCSC 작업 마스터 → equipment_type_codes + work_type_code 조회
    if kcsc_work_ids:
        kcsc_work_res = supabase.table('kcsc_work_master') \
            .select('id, title, is_hazardous, hazard_type, equipment_type_codes, work_type_code') \
            .in_('id', kcsc_work_ids) \
            .execute()
        kcsc_works = kcsc_work_res.data or []
        
        for w in kcsc_works:
            eq_codes = w.get('equipment_type_codes') or []
            extra_equipment_codes.extend(eq_codes)
            work_legal_summary.append({
                'work_id': w['id'],
                'title': w['title'],
                'is_hazardous': w.get('is_hazardous', False),
                'hazard_type': w.get('hazard_type'),
                'equipment_codes': eq_codes,
                'work_type_code': w.get('work_type_code'),
            })
        
        extra_equipment_codes = list(set(extra_equipment_codes))
    
    # 기존 equipments 배열에 KCSC 조회 결과 합산
    # equipments = [{'equipment_code': 'TCR', ...}, ...]
    for code in extra_equipment_codes:
        if not any(e.get('equipment_code') == code for e in equipments):
            equipments.append({'equipment_code': code})
    
    # 기존 step3 로직 그대로 실행
    # construction_work_type 기반으로 3단계 룰 필터
    work_type_codes = list(set(
        w.get('work_type_code') for w in work_legal_summary 
        if w.get('work_type_code')
    ))
    
    # 3단계 룰 조회: sector + diagnosis_stage=3 + construction_work_type IN (설비코드 or work_type)
    q = supabase.table('master_building_legal_rules').select('*') \
        .eq('sector', sector) \
        .eq('diagnosis_stage', 3) \
        .eq('is_active', True)
    
    if extra_equipment_codes:
        # 설비 코드로 필터
        eq_csv = ','.join(extra_equipment_codes)
        q = q.or_(f"construction_work_type.is.null,construction_work_type.in.({eq_csv})")
    
    res = q.execute()
    rules = res.data or []
    matched = [r for r in rules if _evaluate_condition(r, input_data)]
    
    # ... 기존 저장 로직
    
    return {
        'status': 'success',
        'diagnosis_id': diagnosis.get('id'),
        'stage': 3,
        'sector': sector,
        'engine_version': ENGINE_VERSION,
        'rule_count': len(matched),
        'equipment_codes_applied': extra_equipment_codes,   # 신규
        'kcsc_work_summary': work_legal_summary,            # 신규
        'inspection_schedules': inspection_schedules,
        'overdue_count': overdue_count,
        'upcoming_count': upcoming_count,
    }
```

---

## 수정 3. ENGINE_VERSION 업데이트

```python
ENGINE_VERSION = "5.2.0"
# v5.2.0: 건설 법령진단 공정·작업 KCSC 연동
#   - diagnose/step2: kcsc_process_ids → work_type_code 자동 조회
#   - diagnose/step3: construction_work_ids / kcsc_work_ids → equipment_type_codes 자동 조회
#   - 기존 직접 입력 방식 하위 호환 유지
```

---

## API 호출 예시 (완성 후)

### step2 — KCSC 공정 선택 방식
```json
POST /legal-engine/diagnose/step2
{
  "factory_id": "...",
  "diagnosis_id": "...(step1 결과)",
  "kcsc_process_ids": [
    "uuid-거푸집및동바리",
    "uuid-철근조립",
    "uuid-콘크리트타설"
  ]
}
```

**응답 예시:**
```json
{
  "rule_count": 19,
  "filtered_by_work_types": ["FORMWORK", "REINFORCEMENT", "CONCRETE_POUR"],
  "kcsc_process_summary": [
    { "process_name": "거푸집 및 동바리", "work_type_code": "FORMWORK", "risk_level": "HIGH", "has_legal_rules": true },
    { "process_name": "철근조립", "work_type_code": "REINFORCEMENT", "risk_level": "MEDIUM", "has_legal_rules": true }
  ]
}
```

### step3 — PTW 작업 기반
```json
POST /legal-engine/diagnose/step3
{
  "factory_id": "...",
  "diagnosis_id": "...(step2 결과)",
  "construction_work_ids": ["ptw-uuid-1", "ptw-uuid-2"],
  "kcsc_work_ids": ["kcsc-work-uuid-타워크레인", "kcsc-work-uuid-용접"]
}
```

**응답 예시:**
```json
{
  "rule_count": 8,
  "equipment_codes_applied": ["TCR", "WMC"],
  "kcsc_work_summary": [
    { "title": "타워크레인 설치", "is_hazardous": true, "hazard_type": "추락", "equipment_codes": ["TCR"] },
    { "title": "아크 용접", "is_hazardous": true, "hazard_type": "폭발/화재", "equipment_codes": ["WMC"] }
  ]
}
```

---

## 완료 체크

```
□ diagnose/step2 kcsc_process_ids 파라미터 추가
□ kcsc_process_master에서 work_type_code 자동 조회
□ kcsc_process_summary 응답 포함
□ diagnose/step3 construction_work_ids / kcsc_work_ids 파라미터 추가
□ kcsc_work_master에서 equipment_type_codes 자동 조회
□ kcsc_work_summary 응답 포함
□ 기존 방식 하위 호환 (construction_work_types, equipments 직접 입력)
□ ENGINE_VERSION = "5.2.0"
□ Railway 배포 후 버전 확인
```
