# TAI Cursor 작업지시서 — 점검항목 수동 입력 (백엔드)

> 우선순위: 🔴 긴급  
> 작성일: 2026-03-31  
> 레포: taiengineering/tai-api  
> 대상 파일: `routers/safety_template.py` (신규), `routers/inspection_sets.py` (수정)

---

## 배경

SaaS 고객이 법령엔진 외에 자체적으로 점검항목을 정의해서 작업을 생성하고 싶습니다.
예: 우리 회사만의 일일 안전점검 체크리스트, 특정 설비 전용 점검표

**현재 상태:**
- `safety_templates` + `safety_template_items` 테이블 있음 ✅
- `inspection_sets.source` = 'LEGAL_ENGINE'만 있음 ❌
- `safety_templates` 관련 CRUD API 없음 ❌
- `inspection_sets` MANUAL 등록 API 없음 ❌

**DDL 완료 사항 (Cursor 불필요):**
```sql
-- safety_template_items에 추가된 컬럼
sort_order, is_required, standard_value, check_method,
cycle, risk_level, is_active

-- safety_templates에 추가된 컬럼
factory_id, company_id, source, description, is_active, created_at, created_by

-- inspection_sets에 추가된 컬럼
custom_cycle_value, custom_cycle_unit, custom_description
```

---

## 작업 1: 점검 템플릿 CRUD API 신규 생성

### 파일: `routers/safety_template.py` (새 파일 생성)

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from db.supabase_client import get_supabase

router = APIRouter(prefix='/safety-templates', tags=['safety-templates'])

# ── 모델 ──────────────────────────────────
class TemplateItemBody(BaseModel):
    item_name:      str
    item_type:      str = 'text'   # text/boolean/numeric/photo/select
    sort_order:     int = 0
    is_required:    bool = False
    standard_value: Optional[str] = None  # 기준값 (예: '0.5MPa 이하')
    check_method:   Optional[str] = None  # 육안/계측/작동테스트
    cycle:          Optional[str] = None  # daily/weekly/monthly/quarterly/yearly
    risk_level:     Optional[str] = None  # HIGH/MEDIUM/LOW

class TemplateCreateBody(BaseModel):
    factory_id:  str
    template_name: str
    description: Optional[str] = None
    items:       List[TemplateItemBody] = []

class TemplateUpdateBody(BaseModel):
    template_name: Optional[str] = None
    description:   Optional[str] = None

# ── 목록 조회 ──────────────────────────────
@router.get('/{factory_id}')
async def list_templates(factory_id: str):
    supabase = get_supabase()
    res = supabase.table('safety_templates').select(
        'id, template_name, description, source, is_active, created_at'
    ).eq('factory_id', factory_id).eq('is_active', True).execute()

    templates = res.data or []
    # 각 템플릿의 항목 수 병합
    for t in templates:
        items_res = supabase.table('safety_template_items') \
            .select('id', count='exact').eq('template_id', t['id']).execute()
        t['item_count'] = items_res.count or 0

    return {'status': 'success', 'data': templates}

# ── 상세 조회 (항목 포함) ──────────────────
@router.get('/detail/{template_id}')
async def get_template(template_id: str):
    supabase = get_supabase()
    t = supabase.table('safety_templates').select('*') \
        .eq('id', template_id).single().execute().data
    if not t:
        raise HTTPException(status_code=404, detail='템플릿을 찾을 수 없습니다.')

    items = supabase.table('safety_template_items').select('*') \
        .eq('template_id', template_id) \
        .order('sort_order').execute().data or []

    t['items'] = items
    return {'status': 'success', 'data': t}

# ── 생성 ───────────────────────────────────
@router.post('')
async def create_template(body: TemplateCreateBody):
    supabase = get_supabase()
    if not body.template_name.strip():
        raise HTTPException(status_code=422, detail='템플릿명은 필수입니다.')

    # 시설의 company_id 조회
    fac = supabase.table('factories').select('company_id') \
        .eq('id', body.factory_id).single().execute().data or {}

    # 템플릿 INSERT
    tpl_res = supabase.table('safety_templates').insert({
        'factory_id':    body.factory_id,
        'company_id':    fac.get('company_id'),
        'template_name': body.template_name.strip(),
        'description':   body.description,
        'source':        'MANUAL',
        'is_active':     True,
    }).execute()
    if not tpl_res.data:
        raise HTTPException(status_code=500, detail='템플릿 생성 실패')

    template_id = tpl_res.data[0]['id']

    # 항목 INSERT
    if body.items:
        item_rows = [
            {
                'template_id':    template_id,
                'item_name':      item.item_name,
                'item_type':      item.item_type,
                'sort_order':     item.sort_order,
                'is_required':    item.is_required,
                'standard_value': item.standard_value,
                'check_method':   item.check_method,
                'cycle':          item.cycle,
                'risk_level':     item.risk_level,
                'is_active':      True,
            }
            for item in body.items
        ]
        supabase.table('safety_template_items').insert(item_rows).execute()

    return {
        'status':      'success',
        'message':     f'템플릿 "{body.template_name}" 생성 완료',
        'data':        {'template_id': template_id, 'item_count': len(body.items)}
    }

# ── 항목 추가 (기존 템플릿에 항목만 추가) ──
@router.post('/{template_id}/items')
async def add_template_items(template_id: str, items: List[TemplateItemBody]):
    supabase = get_supabase()
    if not items:
        raise HTTPException(status_code=422, detail='항목이 없습니다.')

    rows = [
        {
            'template_id':    template_id,
            'item_name':      i.item_name,
            'item_type':      i.item_type,
            'sort_order':     i.sort_order,
            'is_required':    i.is_required,
            'standard_value': i.standard_value,
            'check_method':   i.check_method,
            'cycle':          i.cycle,
            'risk_level':     i.risk_level,
            'is_active':      True,
        }
        for i in items
    ]
    res = supabase.table('safety_template_items').insert(rows).execute()
    return {'status': 'success', 'data': {'added': len(res.data or [])}}

# ── 항목 삭제 ─────────────────────────────
@router.delete('/{template_id}/items/{item_id}')
async def delete_template_item(template_id: str, item_id: str):
    supabase = get_supabase()
    supabase.table('safety_template_items').update({'is_active': False}) \
        .eq('id', item_id).eq('template_id', template_id).execute()
    return {'status': 'success', 'message': '항목이 삭제되었습니다.'}

# ── 템플릿 삭제 ────────────────────────────
@router.delete('/{template_id}')
async def delete_template(template_id: str):
    supabase = get_supabase()
    supabase.table('safety_templates').update({'is_active': False}) \
        .eq('id', template_id).execute()
    return {'status': 'success', 'message': '템플릿이 삭제되었습니다.'}
```

### main.py에 라우터 등록
```python
from routers import safety_template
app.include_router(safety_template.router)
```

---

## 작업 2: inspection_sets MANUAL 등록 API

### 파일: `routers/inspection_sets.py` 수정
### 엔드포인트: `POST /inspection-sets/manual`

```python
class ManualInspectionSetBody(BaseModel):
    factory_id:       str
    inspection_set_name: str          # 점검 세트명 (예: 소화기 월간 점검)
    inspection_category: str = 'GENERAL'  # FIRE/ELEC/SAFETY/...
    template_id:      Optional[str] = None  # safety_templates.id
    cycle_value:      int = 1
    cycle_unit:       str = 'month'   # year/month/quarter/half_year
    cycle_base_type:  str = 'LAST_INSPECTION'
    description:      Optional[str] = None

@router.post('/manual')
async def create_manual_inspection_set(body: ManualInspectionSetBody):
    supabase = get_supabase()

    # 시설 company_id 조회
    fac = supabase.table('factories').select('company_id') \
        .eq('id', body.factory_id).single().execute().data or {}

    # cycle_base_guide 자동 생성
    UNIT_KO = {'year': '년', 'month': '개월', 'quarter': '분기', 'half_year': '반기'}
    guide = f'마지막 점검일로부터 {body.cycle_value}{UNIT_KO.get(body.cycle_unit, body.cycle_unit)}마다'

    res = supabase.table('inspection_sets').insert({
        'factory_id':          body.factory_id,
        'company_id':          fac.get('company_id'),
        'inspection_set_name': body.inspection_set_name,
        'inspection_category': body.inspection_category,
        'template_id':         body.template_id,
        'cycle_value':         body.cycle_value,
        'cycle_unit':          body.cycle_unit,
        'cycle_base_type':     body.cycle_base_type,
        'cycle_base_guide':    guide,
        'custom_description':  body.description,
        'source':              'MANUAL',
        'status_code':         'PENDING_ANCHOR',
        'anchor_confirmed':    False,
        'is_active':           True,
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail='점검 세트 생성 실패')

    return {
        'status':  'success',
        'message': f'"{body.inspection_set_name}" 점검 세트 생성 완료',
        'data':    {'inspection_set_id': res.data[0]['id']}
    }
```

---

## 완료 체크리스트

```
□ routers/safety_template.py 신규 생성
  □ GET  /safety-templates/{factory_id}          목록
  □ GET  /safety-templates/detail/{template_id}  상세+항목
  □ POST /safety-templates                       템플릿+항목 일괄 생성
  □ POST /safety-templates/{id}/items            항목 추가
  □ DELETE /safety-templates/{id}/items/{item_id} 항목 삭제
  □ DELETE /safety-templates/{id}                템플릿 삭제
□ main.py에 safety_template 라우터 등록
□ POST /inspection-sets/manual 엔드포인트 추가
□ Railway 배포 후 버전 확인
```

## 검증

```bash
# 템플릿 생성
curl -X POST https://api.taieng.co.kr/safety-templates \
  -d '{"factory_id":"xxx","template_name":"소화기 월간점검",
       "items":[{"item_name":"압력계 정상 여부","item_type":"boolean",
                 "cycle":"monthly","risk_level":"HIGH"}]}'

# MANUAL 점검세트 등록
curl -X POST https://api.taieng.co.kr/inspection-sets/manual \
  -d '{"factory_id":"xxx","inspection_set_name":"소화기 월간점검",
       "cycle_value":1,"cycle_unit":"month","inspection_category":"FIRE"}'
```
