# TAI 백엔드 작업지시서 — 이벤트 기반 신고·보고 일정 자동 생성

> 우선순위: 🟡  
> 작성일: 2026-03-31  
> 레포: taiengineering/tai-api

---

## 배경

DB의 `master_building_legal_rules`에 신고·보고 의무 198건이 있으며,
`cycle_base_type` 컬럼에 이벤트 트리거 유형이 구조화 완료됐습니다.

```
현재 점검(INSPECT) → Rolling 방식으로 일정 자동 생성 ✅
신고·보고(REPORT/NOTIFY) → 이벤트 발생 시 일정 생성 ❌ (미구현)
```

---

## base_event 코드별 처리 방식

| cycle_base_type | 트리거 조건 | 처리 방식 |
|----------------|-----------|---------|
| `APPOINTMENT` | 안전관리자 선임/해임 저장 시 | 14일 후 마감 work_schedule 생성 |
| `INCIDENT` | 사고 등록 시 | 즉시 work_schedule 생성 (기한은 룰별 due_days) |
| `CHANGE` | 시설정보 PATCH 시 | 변경신고 알림 work_schedule 생성 |
| `INSTALL` | equipment_assets POST 시 | 설치신고 체크리스트 work_schedule 생성 |
| `CLOSURE` | 시설 status → INACTIVE 시 | 폐업신고 work_schedule 생성 |
| `PERIODIC_YEAR` | Rolling — 매년 1회 | inspection_sets와 동일 방식으로 annual set 생성 |
| `APPLICATION` | 최초 1회 — 온보딩 체크리스트 | factories POST 시 1회성 체크리스트 항목 생성 |
| `ACCIDENT_REPORT` | 사고 등록 시 | 30일 후 마감 work_schedule 생성 |
| `OTHER` | 수동 등록 | 시스템 자동 생성 안 함 (사용자 직접 등록) |

---

## 작업 1: `event_trigger.py` 신규 — 이벤트 트리거 엔진

**파일 경로:** `routers/event_trigger.py`

```python
"""
이벤트 기반 신고·보고 일정 자동 생성 모듈
각 이벤트(선임, 사고, 변경, 설치, 폐업) 발생 시 호출됩니다.
"""
from datetime import date, timedelta
from typing import Optional
from supabase import Client

async def trigger_event_schedules(
    db: Client,
    factory_id: str,
    event_type: str,          # APPOINTMENT / INCIDENT / CHANGE / INSTALL / CLOSURE
    event_date: Optional[date] = None,
    context: dict = {}        # 추가 컨텍스트 (설비 ID, 담당자 ID 등)
) -> dict:
    """
    이벤트 발생 시 해당 factory의 관련 신고·보고 룰을 조회하고
    work_schedules에 마감 일정을 생성합니다.

    Returns:
        {"created": int, "skipped": int, "schedules": [...]}
    """
    event_date = event_date or date.today()

    # 1. 해당 factory의 진단 결과에서 REPORT/NOTIFY + 해당 base_event 룰 조회
    rules = db.table('diagnosis_rule_results') \
        .select('*, master_building_legal_rules(*)') \
        .eq('factory_id', factory_id) \
        .in_('obligation_type', ['REPORT', 'NOTIFY']) \
        .execute()

    # master 룰에서 cycle_base_type 매칭
    matched = []
    for r in rules.data:
        master = r.get('master_building_legal_rules') or {}
        base_type = master.get('cycle_base_type', '')
        if base_type == event_type:
            matched.append({**r, **master})

    created = 0
    skipped = 0
    schedules = []

    for rule in matched:
        # 마감일 계산
        due_days = rule.get('due_days') or 14  # 기본 14일
        deadline = event_date + timedelta(days=due_days)

        # 중복 체크 — 같은 rule_code + factory + 30일 이내 이미 있으면 스킵
        existing = db.table('work_schedules') \
            .select('id') \
            .eq('factory_id', factory_id) \
            .eq('rule_code', rule.get('rule_code', '')) \
            .eq('obligation_type', rule.get('obligation_type', '')) \
            .gte('planned_date', str(event_date - timedelta(days=30))) \
            .execute()

        if existing.data:
            skipped += 1
            continue

        # work_schedules INSERT
        schedule = db.table('work_schedules').insert({
            'factory_id':       factory_id,
            'rule_code':        rule.get('rule_code', ''),
            'law_name':         rule.get('law_name', ''),
            'law_article':      rule.get('law_article', ''),
            'obligation_type':  rule.get('obligation_type', ''),
            'summary':          rule.get('obligation_summary', rule.get('rule_name', '')),
            'source_type':      'EVENT',
            'status_code':      'SCHEDULED',
            'planned_date':     str(deadline),
            'event_type':       event_type,
            'event_date':       str(event_date),
            'form_code':        rule.get('form_code'),
            'cycle_base_guide': rule.get('cycle_base_guide', ''),
            'assigned_user_id': context.get('assigned_user_id'),
        }).execute()

        if schedule.data:
            created += 1
            schedules.append(schedule.data[0])

    return {
        "created": created,
        "skipped": skipped,
        "event_type": event_type,
        "event_date": str(event_date),
        "schedules": schedules
    }
```

---

## 작업 2: 기존 API 엔드포인트에 트리거 훅 추가

### 2-1. `users.py` — 안전관리자 선임 시

```python
# POST /users 또는 PATCH /users/{id} 에서
# role_code == '002'이고 factory_id가 있는 경우

from routers.event_trigger import trigger_event_schedules

# 저장 완료 후:
if user.role_code == '002' and user.factory_id:
    await trigger_event_schedules(
        db=db,
        factory_id=user.factory_id,
        event_type='APPOINTMENT',
        event_date=date.today(),
        context={'assigned_user_id': user.id}
    )
```

### 2-2. `factories.py` — 시설 정보 변경 시

```python
# PATCH /factories/{id} 에서
# 실제 변경이 발생한 경우

from routers.event_trigger import trigger_event_schedules

# PATCH 완료 후:
await trigger_event_schedules(
    db=db,
    factory_id=factory_id,
    event_type='CHANGE',
    event_date=date.today()
)
```

### 2-3. `equipment_assets.py` — 설비 신규 등록 시

```python
# POST /equipment-assets 에서

from routers.event_trigger import trigger_event_schedules

# INSERT 완료 후:
await trigger_event_schedules(
    db=db,
    factory_id=body.factory_id,
    event_type='INSTALL',
    event_date=date.today(),
    context={'equipment_id': new_asset.id, 'equipment_name': body.asset_name}
)
```

### 2-4. 사고 발생 API (신규 or 기존) — 사고 등록 시

```python
# POST /accidents 또는 POST /incidents 에서

from routers.event_trigger import trigger_event_schedules

# 저장 완료 후:
# INCIDENT (즉시 신고)
await trigger_event_schedules(
    db=db, factory_id=body.factory_id,
    event_type='INCIDENT', event_date=date.today()
)
# ACCIDENT_REPORT (산재조사표 30일)
await trigger_event_schedules(
    db=db, factory_id=body.factory_id,
    event_type='ACCIDENT_REPORT', event_date=date.today()
)
```

### 2-5. 시설 폐업 처리 시

```python
# PATCH /factories/{id} 에서 status_code → 'INACTIVE' 감지

if body.status_code == 'INACTIVE':
    await trigger_event_schedules(
        db=db, factory_id=factory_id,
        event_type='CLOSURE', event_date=date.today()
    )
```

---

## 작업 3: `GET /event-schedules/factory/{factory_id}` 신규 API

```python
# 이벤트 기반 일정 목록 조회
# tadmin 점검 캘린더에서 REPORT/NOTIFY 일정을 별도 탭으로 표시

@router.get('/event-schedules/factory/{factory_id}')
async def get_event_schedules(
    factory_id: str,
    obligation_type: Optional[str] = None,  # REPORT | NOTIFY
    status_code: Optional[str] = None,       # SCHEDULED | COMPLETED
    event_type: Optional[str] = None,        # APPOINTMENT | INCIDENT | CHANGE ...
    planned_date_from: Optional[str] = None,
    planned_date_to: Optional[str] = None,
    page: int = 1,
    size: int = 20
):
    """
    factory의 이벤트 기반 신고·보고 일정 목록
    work_schedules 테이블에서 source_type='EVENT'인 항목
    """
    query = db.table('work_schedules') \
        .select('*') \
        .eq('factory_id', factory_id) \
        .eq('source_type', 'EVENT')

    if obligation_type: query = query.eq('obligation_type', obligation_type)
    if status_code:     query = query.eq('status_code', status_code)
    if event_type:      query = query.eq('event_type', event_type)
    if planned_date_from: query = query.gte('planned_date', planned_date_from)
    if planned_date_to:   query = query.lte('planned_date', planned_date_to)

    # ... 페이지네이션 처리
```

---

## 작업 4: `work_schedules` 테이블 컬럼 추가 (migration)

```sql
ALTER TABLE work_schedules
  ADD COLUMN IF NOT EXISTS source_type    TEXT DEFAULT 'INSPECT',
  ADD COLUMN IF NOT EXISTS event_type     TEXT,
  ADD COLUMN IF NOT EXISTS event_date     DATE,
  ADD COLUMN IF NOT EXISTS cycle_base_guide TEXT;

-- 기존 데이터 백필
UPDATE work_schedules SET source_type = 'INSPECT'
WHERE source_type IS NULL;

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_ws_source_type ON work_schedules(source_type);
CREATE INDEX IF NOT EXISTS idx_ws_event_type  ON work_schedules(event_type);
```

---

## 작업 5: PERIODIC_YEAR 처리 — Annual Inspection Set 생성

에너지사용량 신고 등 매년 반복 신고의 경우:

```python
# inspection_sets.py 또는 별도 annual_sets.py

async def create_annual_report_sets(factory_id: str, db: Client):
    """
    obligation_type=REPORT/NOTIFY + cycle_base_type=PERIODIC_YEAR 룰을
    inspection_sets에 ANNUAL 타입으로 생성 (Rolling 방식과 동일)
    """
    rules = db.table('diagnosis_rule_results') \
        .select('*, master_building_legal_rules(cycle_base_type, due_days)') \
        .eq('factory_id', factory_id) \
        .in_('obligation_type', ['REPORT', 'NOTIFY']) \
        .execute()

    for rule in rules.data:
        master = rule.get('master_building_legal_rules') or {}
        if master.get('cycle_base_type') == 'PERIODIC_YEAR':
            # inspection_sets에 cycle_unit=YEAR, cycle_value=1 으로 생성
            # → 기존 Rolling 엔진이 처리
            pass
```

---

## 완료 체크리스트

```
백엔드
□ work_schedules — source_type, event_type, event_date, cycle_base_guide 컬럼 추가 (migration)
□ event_trigger.py 신규 (trigger_event_schedules 함수)
□ users.py — 안전관리자 선임 시 APPOINTMENT 트리거
□ factories.py — 정보 변경 시 CHANGE 트리거
□ factories.py — 폐업(INACTIVE) 시 CLOSURE 트리거
□ equipment_assets.py — 신규 설비 등록 시 INSTALL 트리거
□ GET /event-schedules/factory/{id} 신규 API
□ Railway 배포 확인
```

---

## 캘린더 연동 (프론트)

이 작업 완료 후 `inspection-calendar.html`에서:

```javascript
// 기존: INSPECT 일정만 조회
GET /work-schedules?factory_id=...&source_type=INSPECT

// 추가: REPORT/NOTIFY 일정도 표시
GET /event-schedules/factory/{id}?status_code=SCHEDULED

// 캘린더 점 색상 구분
source_type='INSPECT'  → 파란 점 (법정점검)
source_type='EVENT'
  obligation_type='REPORT'  → 주황 점 (신고)
  obligation_type='NOTIFY'  → 보라 점 (보고)
```
