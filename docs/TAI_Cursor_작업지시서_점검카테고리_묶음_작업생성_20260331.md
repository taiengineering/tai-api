# TAI Cursor 작업지시서 — 점검 카테고리 묶음 작업 생성

> 우선순위: 🔴 긴급  
> 작성일: 2026-03-31  
> 레포: taiengineering/tai-api  
> 대상 파일: `routers/legal_engine.py`, `routers/inspection_checklist.py`

---

## 배경

산업/건물 점검 작업 생성 단위를 **[유형] [주기] 점검** 1건으로 묶어서 생성합니다.

**미수정 시 문제:**
```
소방시설법 점검    2025-09-30  <- work_schedules 1건
소방시설공사업법 점검 2025-09-30  <- work_schedules 1건  <- 현재
화재예방법 점검    2025-09-30  <- work_schedules 1건
→ 안전관리자 화면에 동일날 점검 3개 표시 → 혼란
```

**수정 후:**
```
소방 반기점검 2025-09-30  <- work_schedules 1건
  └─ 소방시설법 제22조 체크리스트
  └─ 소방시설공사업법 제14조 체크리스트
  └─ 화재예방법 제41조 체크리스트
→ 안전관리자 화면에 가독성 높은 점검 1건
```

---

## DB 구조 (이미 완료됨 — DDL 불필요)

```sql
-- 새로 추가된 테이블
work_schedule_groups (이미 생성됨)
  id, factory_id, company_id, group_name,
  inspection_category, cycle_unit, cycle_value, cycle_base_type,
  planned_date, status_code, is_active

-- 기존 테이블 새 콼럼
inspection_sets.inspection_category  (FIRE/ELEC/GAS/SAFETY/ENV/...)
inspection_sets.schedule_group_id    FK -> work_schedule_groups.id
work_schedules.schedule_group_id     FK -> work_schedule_groups.id
work_schedules.source_type           LEGAL/MANUAL
work_schedules.obligation_type       INSPECT/REPORT/APPOINT/ACTION
```

**inspection_category 값:**
| 코드 | 의미 | 포함 법령 |
|------|------|----------|
| FIRE | 소방 | 소방시설법, 화재예방법, 소방기본법 |
| ELEC | 전기 | 전기안전관리법, 전기사업법 |
| GAS | 가스 | 고압가스법, 도시가스법, LPG법 |
| SAFETY | 산업안전 | 산안법, 엑사규칙, 중대재해법 |
| ENV | 환경 | 대기, 물환경, 소음진동, 악취, 토양, 폐기물 |
| BUILDING | 건축물 | 건축법, 건축물관리법 |
| MACHINERY | 기계설비 | 기계설비법, 승강기법, 에너지법 |
| HAZMAT | 위험물 | 위험물안전관리법 |
| WELFARE | 복지/의료 | 의료법, 노인복지법, 시설안전법 |
| INFRA | 상하수도 | 수도법, 하수도법 |

---

## 작업 1: create-inspection-sets에 구룹 생성 로직 추가

### 파일: `routers/legal_engine.py`
### 함수: `create_inspection_sets_from_legal(factory_id)`

**기존 코드에 아래 로직 추가 (기존 insert 로직 후에 이어서):**

```python
# ── STEP N: 카테고리+주기 묶음 작업 그룹 생성 ──
# inspection_sets가 insert된 후 실행

try:
    # 새로 생성된 inspection_sets 조회
    new_sets = supabase.table('inspection_sets') \
        .select('id, inspection_category, cycle_unit, cycle_value, cycle_base_type') \
        .eq('factory_id', factory_id) \
        .eq('source', 'LEGAL_ENGINE') \
        .eq('anchor_confirmed', False) \
        .execute().data or []

    # 콴로니: inspection_category + cycle_unit + cycle_value 동일한 것끌리 묶기
    from collections import defaultdict
    group_map = defaultdict(list)  # key=(category, unit, value) -> [set_ids]
    for s in new_sets:
        cat = s.get('inspection_category') or 'GENERAL'
        unit = s.get('cycle_unit') or 'year'
        val  = s.get('cycle_value') or 1
        group_map[(cat, unit, val)].append(s['id'])

    CATEGORY_NAMES = {
        'FIRE': '소방', 'ELEC': '전기', 'GAS': '가스',
        'SAFETY': '산업안전', 'ENV': '환경', 'BUILDING': '건축물',
        'MACHINERY': '기계설비', 'HAZMAT': '위험물',
        'WELFARE': '복지의료', 'INFRA': '상하수도', 'GENERAL': '기타',
    }
    UNIT_NAMES = {
        'month': '월간', 'quarter': '분기', 'half_year': '반기', 'year': '연간'
    }

    # 중복 방지: 기존 그룹 삭제
    supabase.table('work_schedule_groups') \
        .delete().eq('factory_id', factory_id).execute()

    fac_company = supabase.table('factories') \
        .select('company_id').eq('id', factory_id).single().execute().data or {}
    company_id = fac_company.get('company_id')

    for (cat, unit, val), set_ids in group_map.items():
        cat_name  = CATEGORY_NAMES.get(cat, cat)
        unit_name = UNIT_NAMES.get(unit, unit)
        group_name = f'{cat_name} {unit_name}점검'
        if val > 1:
            group_name = f'{cat_name} {val}{unit_name}점검'

        # work_schedule_groups INSERT
        grp_res = supabase.table('work_schedule_groups').insert({
            'factory_id':         factory_id,
            'company_id':         company_id,
            'group_name':         group_name,
            'inspection_category': cat,
            'cycle_unit':         unit,
            'cycle_value':        val,
            'status_code':        'SCHEDULED',
        }).execute()

        if not grp_res.data:
            continue

        group_id = grp_res.data[0]['id']

        # inspection_sets에 schedule_group_id 링크
        for sid in set_ids:
            supabase.table('inspection_sets') \
                .update({'schedule_group_id': group_id}) \
                .eq('id', sid).execute()

except Exception as e:
    print(f'[CREATE_ISET] 그룹 생성 실패 (응답에는 영향 없음): {e}')
```

---

## 작업 2: generate-schedules에 그룹 단위 작업 생성 로직

### 파일: `routers/inspection_checklist.py` (또는 generate-schedules 있는 파일)
### 엔드포인트: `POST /inspection/generate-schedules/{factory_id}`

**기존 로직에서 inspection_sets 단력 대신 work_schedule_groups 단력으로 변경:**

```python
# 수정 전: inspection_sets 리스트 순환 → 각각 work_schedules INSERT
# 수정 후: work_schedule_groups 순환 → 그룹당 work_schedules 1건 INSERT

# 그룹 조회
groups_res = supabase.table('work_schedule_groups') \
    .select('*') \
    .eq('factory_id', factory_id) \
    .eq('is_active', True) \
    .execute()
groups = groups_res.data or []

created = 0
skipped_anchor = 0

for grp in groups:
    grp_id = grp['id']

    # 그룹내 inspection_sets 중 anchor_confirmed=true인 것이 1개라도 있는지 확인
    sets_in_group = supabase.table('inspection_sets') \
        .select('schedule_anchor_date, next_planned_date, anchor_confirmed') \
        .eq('schedule_group_id', grp_id) \
        .execute().data or []

    confirmed = [s for s in sets_in_group if s.get('anchor_confirmed')]
    if not confirmed:
        skipped_anchor += 1
        continue

    # 가장 빠른 next_planned_date 사용
    next_dates = [s['next_planned_date'] for s in confirmed if s.get('next_planned_date')]
    if not next_dates:
        skipped_anchor += 1
        continue

    planned_date = min(next_dates)  # 가장 빠른 날짜

    # 중복 스케줄 방지
    exists = supabase.table('work_schedules') \
        .select('id').eq('schedule_group_id', grp_id) \
        .eq('planned_date', planned_date).execute().data
    if exists:
        continue

    # work_schedules INSERT (그룹 1건)
    result = supabase.table('work_schedules').insert({
        'factory_id':       factory_id,
        'company_id':       grp.get('company_id'),
        'schedule_group_id': grp_id,
        'planned_date':     planned_date,
        'start_date':       planned_date,
        'description':      grp['group_name'],
        'repeat_type':      grp['cycle_unit'],
        'repeat_interval':  grp['cycle_value'],
        'status_code':      'SCHEDULED',
        'source_type':      'LEGAL',
        'obligation_type':  'INSPECT',
        'active_yn':        True,
    }).execute()
    created += len(result.data or [])

    # work_schedule_groups.planned_date 업데이트
    supabase.table('work_schedule_groups') \
        .update({'planned_date': planned_date}) \
        .eq('id', grp_id).execute()

return {
    'status': 'success',
    'message': f'{created}개 스케줄이 생성됐습니다.',
    'data': {
        'factory_id':     factory_id,
        'groups_total':   len(groups),
        'created':        created,
        'skipped_anchor': skipped_anchor,
    }
}
```

---

## 작업 3: 완료 후 다음 회차 자동 생성

### 파일: `routers/inspection_checklist.py`
### 엔드포인트: `POST /inspection/complete/{work_schedule_id}`

**완료 처리 시 다음 회차 자동 INSERT:**

```python
# 현재 상태를 DONE으로 업데이트
supabase.table('work_schedules') \
    .update({'status_code': 'DONE', 'completed_at': today}) \
    .eq('id', work_schedule_id).execute()

# 다음 회차 자동 생성
if ws.get('schedule_group_id'):
    grp = supabase.table('work_schedule_groups') \
        .select('*').eq('id', ws['schedule_group_id']).single().execute().data

    if grp:
        from dateutil.relativedelta import relativedelta
        from datetime import date

        completed = date.fromisoformat(today)
        cycle_unit  = grp.get('cycle_unit') or 'year'
        cycle_value = grp.get('cycle_value') or 1
        DELTA = {
            'year':      relativedelta(years=cycle_value),
            'month':     relativedelta(months=cycle_value),
            'half_year': relativedelta(months=6),
            'quarter':   relativedelta(months=3),
        }
        next_date = (completed + DELTA.get(cycle_unit, relativedelta(years=1))).isoformat()

        # 다음 회차 work_schedules INSERT
        supabase.table('work_schedules').insert({
            'factory_id':       ws.get('factory_id'),
            'company_id':       ws.get('company_id'),
            'schedule_group_id': grp['id'],
            'planned_date':     next_date,
            'start_date':       next_date,
            'description':      grp['group_name'],
            'repeat_type':      cycle_unit,
            'repeat_interval':  cycle_value,
            'status_code':      'SCHEDULED',
            'source_type':      'LEGAL',
            'obligation_type':  'INSPECT',
            'active_yn':        True,
        }).execute()

        # inspection_sets의 last_inspection_date + next_planned_date 업데이트
        supabase.table('inspection_sets') \
            .update({
                'last_inspection_date': today,
                'next_planned_date':    next_date,
                'schedule_anchor_date': today,
            }) \
            .eq('schedule_group_id', grp['id']).execute()
```

---

## 완료 체크리스트

```
□ create-inspection-sets: 영문 샀 엄 버그 1·2 수정 병행 적용
□ create-inspection-sets: 그룹 생성 로직 추가
□ create-inspection-sets: inspection_sets.schedule_group_id 링크
□ generate-schedules: groups 단위 작업 생성 로직
□ generate-schedules: skipped_anchor 고려
□ inspection/complete: 다음 회차 자동 INSERT
□ inspection/complete: inspection_sets 날짜 업데이트
□ Railway 배포 후 테스트
```

---

## 검증 방법

```bash
# 1. 진단 → 점검세트+그룹 생성 테스트
curl -X POST https://api.taieng.co.kr/legal-engine/diagnose/step1 \
  -d '{"sector":"BUILDING","factory_id":"9ec1ac44...","input":{"worker_count":85,"total_floor_area":3000,"electric_capacity":500}}'

curl -X POST https://api.taieng.co.kr/legal-engine/create-inspection-sets/9ec1ac44...
# → created > 0, 그룹 목록 확인 ("data.groups" 포함)

# 2. anchor 설정 후 generate-schedules
curl -X PATCH https://api.taieng.co.kr/inspection-sets/{id}/anchor \
  -d '{"schedule_anchor_date":"2025-03-31"}'

curl -X POST https://api.taieng.co.kr/inspection/generate-schedules/9ec1ac44...
# → created 건수, 그룹명 확인 ("소방 반기점검", "전기 연간점검" 등)

# 3. 완료 처리 후 다음 회차 확인
curl -X POST https://api.taieng.co.kr/inspection/complete/{work_schedule_id}
# → 다음 스케줄 자동 생성 확인
```
