# TAI Cursor 작업지시서 — 법정점검 기준일 설정 API

> 우선순위: 🔴 긴급  
> 작성일: 2026-03-31  
> 레포: taiengineering/tai-api  
> 대상 파일: `routers/inspection_sets.py` (수정)

---

## 개요

`inspection_sets` 테이블에 기준일(`schedule_anchor_date`)을 저장하는 PATCH 엔드포인트 2개를 추가합니다.

**배경:**
- 법령진단 완료 후 `inspection_sets`가 자동 생성되지만 `schedule_anchor_date`가 NULL
- NULL 상태에서는 `next_planned_date` 계산 불가 → 실제 일정 생성 불가
- SaaS 사용자가 tadmin에서 기준일을 직접 입력하면 이 API로 저장

**DB 현황 (이미 완료됨 — DDL 작업 불필요):**
```sql
-- inspection_sets 테이블에 이미 존재하는 컬럼들
schedule_anchor_date  DATE     -- 기준일 (사용자 입력)
last_inspection_date  DATE     -- 직전 점검 완료일 (선택)
next_planned_date     DATE     -- 다음 점검 예정일 (자동 계산)
anchor_confirmed      BOOLEAN  -- 기준일 확정 여부
cycle_base_type       TEXT     -- 기준점 유형 (LAST_INSPECTION 등)
cycle_base_guide      TEXT     -- 안내 문구
cycle_value           INTEGER  -- 주기 숫자
cycle_unit            TEXT     -- 주기 단위 (year/month/half_year/quarter)
```

---

## 작업 1: 단건 기준일 저장

### 엔드포인트
```
PATCH /inspection-sets/{inspection_set_id}/anchor
```

### Request Body
```python
class AnchorUpdateBody(BaseModel):
    schedule_anchor_date: str           # 필수. 형식: YYYY-MM-DD
    last_inspection_date: Optional[str] = None  # 선택. 형식: YYYY-MM-DD
```

### 처리 로직
```python
@router.patch("/{inspection_set_id}/anchor")
async def update_inspection_anchor(inspection_set_id: str, body: AnchorUpdateBody):
    supabase = get_supabase()

    # 1. 대상 inspection_set 조회
    res = supabase.table('inspection_sets').select(
        'id, cycle_value, cycle_unit, factory_id'
    ).eq('id', inspection_set_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail='점검 세트를 찾을 수 없습니다.')

    iset = res.data
    cycle_value = iset.get('cycle_value') or 1
    cycle_unit  = iset.get('cycle_unit') or 'year'

    # 2. next_planned_date 계산
    from datetime import date
    from dateutil.relativedelta import relativedelta

    anchor = date.fromisoformat(body.schedule_anchor_date)

    UNIT_MAP = {
        'year':      relativedelta(years=cycle_value),
        'month':     relativedelta(months=cycle_value),
        'half_year': relativedelta(months=6),
        'quarter':   relativedelta(months=3),
    }
    delta = UNIT_MAP.get(cycle_unit, relativedelta(years=1))
    next_date = anchor + delta

    # 3. DB 업데이트
    update_data = {
        'schedule_anchor_date': body.schedule_anchor_date,
        'next_planned_date':    next_date.isoformat(),
        'anchor_confirmed':     True,
    }
    if body.last_inspection_date:
        update_data['last_inspection_date'] = body.last_inspection_date

    supabase.table('inspection_sets').update(update_data).eq('id', inspection_set_id).execute()

    return {
        'status': 'success',
        'data': {
            'id': inspection_set_id,
            'schedule_anchor_date': body.schedule_anchor_date,
            'next_planned_date':    next_date.isoformat(),
            'anchor_confirmed':     True,
        }
    }
```

---

## 작업 2: 일괄 기준일 저장

### 엔드포인트
```
PATCH /inspection-sets/anchor/bulk
```

### Request Body
```python
class AnchorBulkItem(BaseModel):
    id: str
    schedule_anchor_date: str
    last_inspection_date: Optional[str] = None

class AnchorBulkBody(BaseModel):
    items: List[AnchorBulkItem]
```

### 처리 로직
- items를 순회하며 각각 단건 저장 로직 동일하게 적용
- 실패한 건은 `errors` 리스트에 담아 응답
- 성공/실패 카운트 반환

```python
return {
    'status': 'success',
    'data': {
        'updated': updated_count,
        'failed':  len(errors),
        'errors':  errors  # [{id, reason}, ...]
    }
}
```

---

## 작업 3: inspection_sets 목록 조회 엔드포인트 확인/수정

`GET /inspection-sets` 에서 아래 컬럼이 **반드시 포함**되도록 select 쿼리 확인:

```python
# 반환 필드에 아래 항목 포함 여부 확인 (없으면 추가)
'cycle_base_type, cycle_base_guide, schedule_anchor_date, last_inspection_date, next_planned_date, anchor_confirmed'
```

필터 파라미터도 지원해야 함:
```
GET /inspection-sets?factory_id={uuid}&source=LEGAL_ENGINE&anchor_confirmed=false
```

---

## 의존 패키지 확인

`requirements.txt`에 `python-dateutil` 있는지 확인. 없으면 추가:
```
python-dateutil>=2.8.2
```

---

## 완료 체크리스트

```
□ PATCH /inspection-sets/{id}/anchor 구현
  □ schedule_anchor_date 저장
  □ next_planned_date 자동 계산 (cycle_unit 기반)
  □ anchor_confirmed = True 저장
  □ last_inspection_date 선택 저장
□ PATCH /inspection-sets/anchor/bulk 구현
  □ 배치 처리
  □ 실패 건 errors 리스트 반환
□ GET /inspection-sets 응답에 기준일 관련 컬럼 포함
□ python-dateutil 의존성 확인
□ Railway 배포 후 버전 확인
```

---

## 참고 파일

```
routers/inspection_sets.py   ← 수정 대상
routers/legal_engine.py      ← cycle_unit 처리 패턴 참고
db/supabase_client.py        ← get_supabase() 임포트
```
