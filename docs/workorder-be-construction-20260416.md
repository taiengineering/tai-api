# 건설 모듈 백엔드 작업지시서

**작성일:** 2026-04-16  
**우선순위:** BE-1 → BE-3 → BE-4 순서  
**파일:** `routers/construction.py` (dev 브랜치)  
**BE-2는 불필요** — 점검 결과 mismatch 0건 확인됨

---

## BE-Step1: inspection_sets 자동생성 로직 추가 (🔴 P0)

### 문제
`_auto_diagnose_and_schedule()`이 `work_schedules`만 생성하고 `inspection_sets`는 생성하지 않음.  
산업 모듈은 LEGAL_ENGINE이 303건 자동 생성했지만, 건설은 0건.

### 작업 내용

#### 1) 새 함수 추가: `_create_inspection_sets_from_diagnosis()`

```python
async def _create_inspection_sets_from_diagnosis(
    supabase, factory_id: str, company_id: str, diagnosis_rules: list
) -> dict:
    """
    법령진단 결과에서 inspection_sets를 자동 생성.
    Returns: {created: N, skipped: N}
    """
    # 1. 기존 inspection_sets 조회 (중복 방지)
    existing = supabase.table('inspection_sets').select('legal_rule_code').eq(
        'factory_id', factory_id
    ).execute()
    existing_codes = {r['legal_rule_code'] for r in (existing.data or []) if r.get('legal_rule_code')}
    
    created = 0
    skipped = 0
    
    # 2. obligation_type별 기본 주기 매핑
    DEFAULT_CYCLE = {
        'BEFORE_WORK': ('day', 1),
        'INSPECT': ('month', 1),
        'REPORT': ('quarter', 1),
        'NOTIFY': ('year', 1),
        'APPOINT': ('year', 1),
        'ACTION': ('month', 1),
        'DOCUMENT': ('year', 1),
        'OTHER': ('month', 1),
    }
    
    # 3. 각 rule → inspection_set 레코드 생성
    for rule in diagnosis_rules:
        rule_id = rule.get('rule_id', '')
        if not rule_id or rule_id in existing_codes:
            skipped += 1
            continue
        
        obl_type = rule.get('obligation_type', 'OTHER')
        cycle_unit, cycle_value = DEFAULT_CYCLE.get(obl_type, ('month', 1))
        summary = rule.get('obligation_summary', '')
        set_name = summary[:30] if summary else rule_id
        
        record = {
            'company_id': company_id,
            'factory_id': factory_id,
            'inspection_set_name': set_name,
            'inspection_set_code': rule_id,
            'legal_rule_code': rule_id,
            'law_name': rule.get('law_name', ''),
            'law_article': rule.get('law_article', ''),
            'obligation_type': obl_type,
            'obligation_summary': summary,
            'inspection_category': _map_category(obl_type),
            'cycle_unit': cycle_unit,
            'cycle_value': cycle_value,
            'cycle_base_type': 'LAST_INSPECTION',
            'source': 'LEGAL_ENGINE',
            'status_code': 'PENDING_ANCHOR',
            'anchor_confirmed': False,
            'is_active': True,
        }
        
        try:
            supabase.table('inspection_sets').insert(record).execute()
            created += 1
        except Exception as e:
            logger.warning(f"inspection_set 생성 실패: {rule_id} - {e}")
            skipped += 1
    
    return {'created': created, 'skipped': skipped}


def _map_category(obl_type: str) -> str:
    """obligation_type → inspection_category 매핑"""
    mapping = {
        'INSPECT': '정기점검',
        'BEFORE_WORK': '작업전점검',
        'REPORT': '보고',
        'NOTIFY': '신고',
        'APPOINT': '선임',
        'ACTION': '조치',
        'DOCUMENT': '문서',
    }
    return mapping.get(obl_type, '기타')
```

#### 2) 호출 위치 2곳

**위치 A:** `_auto_diagnose_and_schedule()` 내부
```python
# 기존: work_schedules 생성 후
# 추가:
insp_result = await _create_inspection_sets_from_diagnosis(
    supabase, factory_id, company_id, applicable_rules
)
logger.info(f"inspection_sets 자동생성: {insp_result}")
```

**위치 B:** `POST /construction/sites/{site_id}/diagnose` 엔드포인트
```python
# 수동 재진단 시에도 동일하게 호출
insp_result = await _create_inspection_sets_from_diagnosis(
    supabase, factory_id, company_id, applicable_rules
)
```

#### 3) 진단 결과에서 rules 추출
`_run_diagnosis()` 또는 기존 진단 함수의 반환값에서 `applicable_rules` 리스트를 추출.  
각 rule에 최소 `rule_id`, `obligation_type`, `obligation_summary`, `law_name`, `law_article` 포함 필요.

### 완료 조건
- [ ] POST /construction/sites 호출 시 inspection_sets 자동 생성
- [ ] POST /construction/sites/{id}/diagnose 호출 시 동일하게 생성
- [ ] 중복 호출해도 기존 건 skip
- [ ] DB에서 `SELECT count(*) FROM inspection_sets WHERE factory_id='{건설factory}' AND source='LEGAL_ENGINE'` > 0 확인

### 테스트 데이터
```
construction_sites: 42941f8d-0247-45ee-bb16-2899213137ec
factories mirror:   b692bc36-6199-426b-9d4c-b39080b5947e
company_id:         f49f05da-2b52-4ebf-b117-11a06b2ffbf1
```
기존 수동 생성 8건이 있으므로, 자동생성 시 이 8건은 skip되고 나머지만 추가되어야 함.

---

## BE-Step3: contract_amount 단위 명확화

### 작업 내용
1. `SiteCreate` Pydantic 모델에 description 추가:
   ```python
   contract_amount: Optional[Decimal] = Field(None, description="도급금액 (억원 단위, 예: 200 = 200억원)", ge=0, le=99999)
   ```
2. DB 컬럼 comment:
   ```sql
   COMMENT ON COLUMN construction_sites.contract_amount IS '도급금액 (억원 단위, 예: 200 = 200억원)';
   ```

### 완료 조건
- [ ] API 문서(/docs)에 단위 표시
- [ ] 음수/소수점 입력 시 validation error

---

## BE-Step4: KCSC 공정 검색 API 확인

### 작업 내용
`GET /construction/kcsc/processes?search=골조&size=10` 엔드포인트가 존재하는지 확인.  
없으면 추가:
```python
@router.get("/kcsc/processes")
async def search_kcsc_processes(search: str = "", size: int = 10):
    query = supabase.table('construction_kcsc_processes').select('*')
    if search:
        query = query.ilike('process_name', f'%{search}%')
    result = query.limit(size).execute()
    return {"data": {"items": result.data or []}}
```

### 완료 조건
- [ ] KCSC 마스터 검색 API 정상 응답
- [ ] 프론트에서 공정등록 시 호출 가능
