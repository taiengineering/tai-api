# TAI Cursor 작업지시서 — 설비 코드 → 점검항목 매핑 테이블 구축 (방법 C)

> 우선순위: 🟡 중간  
> 작성일: 2026-03-31  
> 레포: taiengineering/tai-api  
> 대상 파일: `routers/engine_equipment.py` (또는 신규 `routers/equipment_inspection.py`)

---

## 배경

현재 `equipment_assets.equipment_type_code`(숫자 코드)와
`inspection_master.equipment_std`(영문 텍스트)이 연결되지 않아
설비 등록 후 점검항목이 자동 연결되지 않는 상태입니다.

**이 작업의 목표:**  
`equipment_type_code` → `inspection_master.equipment_std` 매핑 테이블 생성 후,
설비 등록 시 점검항목 + 주기를 자동 연결하는 API 엔드포인트 추가.

---

## DB 작업 (apply_migration으로 실행)

### STEP 1. 매핑 테이블 생성

```sql
CREATE TABLE IF NOT EXISTS equipment_type_inspection_map (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  equipment_type_code TEXT NOT NULL,        -- system_codes.equipment_type 코드 (예: '014')
  equipment_type_name TEXT NOT NULL,        -- 한글명 (예: '보일러')
  inspection_std      TEXT,                 -- inspection_master.equipment_std (예: 'boiler')
  fallback_std        TEXT,                 -- inspection_std 없을 때 fallback
  has_direct_map      BOOLEAN DEFAULT FALSE,-- 직접 매핑 여부
  inspection_category TEXT,                 -- 점검 카테고리 (ELEC/MECH/FIRE/...)
  priority_level      TEXT DEFAULT 'NORMAL',-- HIGH/NORMAL/LOW (다음 데이터 교체 시 우선순위)
  is_active           BOOLEAN DEFAULT TRUE,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE equipment_type_inspection_map IS
  'equipment_type_code(40종) → inspection_master.equipment_std 매핑.
   has_direct_map=true: 직접 매핑, false: 유사설비 fallback 또는 기본값 사용';
```

### STEP 2. 매핑 데이터 삽입

```sql
INSERT INTO equipment_type_inspection_map
  (equipment_type_code, equipment_type_name, inspection_std, fallback_std, has_direct_map, inspection_category)
VALUES
-- ── 직접 매핑 9종 (inspection_master에 정확히 있음) ──
('011', '펜프',       'pump',            NULL,      TRUE,  'MECH'),
('012', '압축기',      'compressor',      NULL,      TRUE,  'MECH'),
('014', '보일러',      'boiler',          NULL,      TRUE,  'MECH'),
('018', '팬',           'fan',             NULL,      TRUE,  'MECH'),
('021', '크레인',      'crane',           NULL,      TRUE,  'MECH'),
('023', '프레스',      'press',           NULL,      TRUE,  'MECH'),
('024', '컨베이어',    'conveyor',        NULL,      TRUE,  'MECH'),
('025', '승강기',      'elevator',        NULL,      TRUE,  'MECH'),
('038', '압력용기',    'pressure_vessel', NULL,      TRUE,  'MECH'),

-- ── fallback 매핑 31종 (A방법 데이터 수집 후 교체 예정) ──
-- 전기 계열 → compressor 유사
('001', '변압기',      NULL, 'compressor', FALSE, 'ELEC'),
('002', '기중차단기',   NULL, 'compressor', FALSE, 'ELEC'),
('003', '진공차단기',   NULL, 'compressor', FALSE, 'ELEC'),
('004', '배선용차단기', NULL, 'compressor', FALSE, 'ELEC'),
('005', '누전차단기',   NULL, 'compressor', FALSE, 'ELEC'),
('006', '배전반',      NULL, 'compressor', FALSE, 'ELEC'),
('007', '분전반',      NULL, 'compressor', FALSE, 'ELEC'),
('008', '전동기',      NULL, 'pump',       FALSE, 'ELEC'),
('009', 'UPS',        NULL, 'compressor', FALSE, 'ELEC'),
('010', '비상발전기',   NULL, 'compressor', FALSE, 'ELEC'),
-- 메카니컈 계열
('013', '열교환기',    NULL, 'pressure_vessel', FALSE, 'MECH'),
('015', '탱크',        NULL, 'pressure_vessel', FALSE, 'MECH'),
('016', '밸브',        NULL, 'pump',       FALSE, 'MECH'),
('017', '배관',        NULL, 'pump',       FALSE, 'MECH'),
('019', '냉동기',      NULL, 'compressor', FALSE, 'MECH'),
('020', '칠러',        NULL, 'compressor', FALSE, 'MECH'),
('022', '호이스트',     NULL, 'crane',      FALSE, 'MECH'),
('026', '에스컈레이터', NULL, 'elevator',   FALSE, 'MECH'),
-- 가스/탱크 계열
('027', '가스탱크',    NULL, 'pressure_vessel', FALSE, 'GAS'),
('028', 'LPG탱크',    NULL, 'pressure_vessel', FALSE, 'GAS'),
('029', '화학물질탱크', NULL, 'pressure_vessel', FALSE, 'GAS'),
('030', '유류탱크',    NULL, 'pressure_vessel', FALSE, 'GAS'),
-- 소방 계열
('031', '스프링클러',  NULL, 'pump',       FALSE, 'FIRE'),
('032', '자동화재탐지', NULL, 'compressor', FALSE, 'FIRE'),
('033', '소화기',      NULL, 'pressure_vessel', FALSE, 'FIRE'),
('034', '소화전',      NULL, 'pump',       FALSE, 'FIRE'),
-- 환경 계열
('035', '배기시설',    NULL, 'fan',        FALSE, 'ENV'),
('036', '집진기',      NULL, 'fan',        FALSE, 'ENV'),
('037', '오수처리시설', NULL, 'pump',       FALSE, 'ENV'),
('039', '냉동기(냉각)',  NULL, 'compressor', FALSE, 'MECH'),
('040', '기타',        NULL, 'pump',       FALSE, 'MECH')
ON CONFLICT DO NOTHING;
```

---

## API 엔드포인트 추가

### 파일 위치
기존 `routers/engine_equipment.py`에 이어서 작성 (또는 신규 `routers/equipment_inspection.py`)

### 엔드포인트 1: 설비별 점검항목 조회

```
GET /equipment-inspection/items/{asset_id}
```

**동작:**
1. `equipment_assets.equipment_type_code` 조회
2. `equipment_type_inspection_map`에서 `inspection_std` 또는 `fallback_std` 조회
3. `inspection_master`에서 해당 std의 점검항목 반환
4. 주기별 그룹화 (daily/weekly/monthly)

```python
@router.get("/items/{asset_id}")
async def get_inspection_items(asset_id: str):
    supabase = get_supabase()

    # 1. 설비 조회
    asset = supabase.table('equipment_assets') \
        .select('id, asset_name, equipment_type_code, equipment_model_id') \
        .eq('id', asset_id).single().execute().data
    if not asset:
        raise HTTPException(status_code=404, detail='설비를 찾을 수 없습니다.')

    type_code = asset.get('equipment_type_code')

    # 2. 매핑 테이블에서 inspection_std 조회
    mapping = None
    if type_code:
        mapping = supabase.table('equipment_type_inspection_map') \
            .select('*').eq('equipment_type_code', type_code) \
            .eq('is_active', True).single().execute().data

    inspection_std = None
    if mapping:
        inspection_std = mapping.get('inspection_std') or mapping.get('fallback_std')
        has_direct_map = mapping.get('has_direct_map', False)
    else:
        inspection_std = None
        has_direct_map = False

    items = []
    if inspection_std:
        result = supabase.table('inspection_master') \
            .select('inspection_item, cycle, rule_type, risk_level') \
            .eq('equipment_std', inspection_std) \
            .eq('is_active', True) \
            .execute()
        items = result.data or []

    # 주기별 그룹화
    from collections import defaultdict
    grouped = defaultdict(list)
    for item in items:
        grouped[item['cycle']].append(item)

    CYCLE_ORDER = ['daily', 'weekly', 'monthly']
    CYCLE_LABEL = {'daily': '일상점검', 'weekly': '주간점검', 'monthly': '월간점검'}

    return {
        'status': 'success',
        'data': {
            'asset_id':        asset_id,
            'asset_name':      asset.get('asset_name'),
            'equipment_type_code': type_code,
            'inspection_std':  inspection_std,
            'has_direct_map':  has_direct_map,
            'data_quality':    'DIRECT' if has_direct_map else ('FALLBACK' if inspection_std else 'NONE'),
            'total_items':     len(items),
            'inspection_by_cycle': [
                {
                    'cycle':       c,
                    'cycle_label': CYCLE_LABEL.get(c, c),
                    'items':       grouped[c]
                }
                for c in CYCLE_ORDER if c in grouped
            ]
        }
    }
```

### 엔드포인트 2: 설비 등록 시 점검세트 자동 구성

```
POST /equipment-inspection/setup/{asset_id}
```

**동작:** 위의 items 조회 후 `inspection_sets` + `inspection_set_items`에 저장

```python
@router.post("/setup/{asset_id}")
async def setup_inspection_for_asset(asset_id: str):
    """
    설비 등록 시 자동 호출: inspection_set + items 구성
    """
    supabase = get_supabase()

    # items 조회 (위의 함수 재사용)
    asset = supabase.table('equipment_assets') \
        .select('id, asset_name, equipment_type_code, factory_id') \
        .eq('id', asset_id).single().execute().data
    if not asset:
        raise HTTPException(status_code=404, detail='설비를 찾을 수 없습니다.')

    # 이미 설정된 inspection_set이 있으면 skip
    existing = supabase.table('inspection_set_items') \
        .select('id').eq('equipment_asset_id', asset_id).limit(1).execute().data
    if existing:
        return {'status': 'success', 'message': '이미 점검세트가 설정되어 있습니다.',
                'data': {'created': 0}}

    # 주기별로 inspection_set 생성 (일상/주간/월간)
    type_code = asset.get('equipment_type_code')
    mapping = supabase.table('equipment_type_inspection_map') \
        .select('*').eq('equipment_type_code', type_code) \
        .eq('is_active', True).single().execute().data
    if not mapping:
        return {'status': 'success', 'message': '매핑된 점검항목이 없습니다.',
                'data': {'created': 0, 'data_quality': 'NONE'}}

    inspection_std = mapping.get('inspection_std') or mapping.get('fallback_std')
    items = supabase.table('inspection_master') \
        .select('id, inspection_item, cycle, risk_level') \
        .eq('equipment_std', inspection_std).eq('is_active', True).execute().data or []

    if not items:
        return {'status': 'success', 'message': '점검항목이 없습니다.',
                'data': {'created': 0}}

    # 주기별 inspection_set INSERT
    CYCLE_TO_UNIT = {'daily': 'day', 'weekly': 'week', 'monthly': 'month'}
    CYCLE_LABEL = {'daily': '일상점검', 'weekly': '주간점검', 'monthly': '월간점검'}
    factory_id = asset.get('factory_id')
    created = 0

    from collections import defaultdict
    grouped = defaultdict(list)
    for item in items:
        grouped[item['cycle']].append(item)

    for cycle, cycle_items in grouped.items():
        # inspection_set 생성
        iset = supabase.table('inspection_sets').insert({
            'factory_id':           factory_id,
            'inspection_set_name':  f"{asset['asset_name']} {CYCLE_LABEL.get(cycle, cycle)}",
            'cycle_unit':           CYCLE_TO_UNIT.get(cycle, 'month'),
            'cycle_value':          1,
            'source':               'EQUIPMENT',
            'status_code':          'PENDING_ANCHOR',
            'is_active':            True,
        }).execute().data
        if not iset:
            continue
        iset_id = iset[0]['id']

        # inspection_set_items INSERT
        for item in cycle_items:
            supabase.table('inspection_set_items').insert({
                'inspection_set_id':  iset_id,
                'equipment_asset_id': asset_id,
                'item_name':          item['inspection_item'],
                'risk_level':         item.get('risk_level'),
            }).execute()
        created += 1

    return {
        'status': 'success',
        'message': f'{len(items)}개 점검항목이 {created}개 주기 구룹으로 설정됐습니다.',
        'data': {
            'asset_id':      asset_id,
            'inspection_std': inspection_std,
            'data_quality':  'DIRECT' if mapping.get('has_direct_map') else 'FALLBACK',
            'total_items':   len(items),
            'sets_created':  created,
        }
    }
```

### 엔드포인트 3: 매핑 테이블 조회

```
GET /equipment-inspection/mapping
매핑 전체 목록 반환 (관리자 확인용)
```

---

## main.py 등록

```python
from routers import equipment_inspection
app.include_router(equipment_inspection.router, prefix="/equipment-inspection", tags=["설비점검"])
```

---

## 완료 체크리스트

```
□ equipment_type_inspection_map 테이블 생성 (apply_migration)
□ 40종 매핑 데이터 삽입
□ GET /equipment-inspection/items/{asset_id} 구현
□ POST /equipment-inspection/setup/{asset_id} 구현
□ GET /equipment-inspection/mapping 구현
□ main.py 등록
□ Railway 배포 후 테스트 (014=보일러, 025=승강기, 031=스프링클러)
```

---

## 검증 방법

```bash
# 1. 직접 매핑 설비 (boiler)
curl https://api.taieng.co.kr/equipment-inspection/items/{boiler_asset_id}
# -> data_quality: DIRECT, items 10개, daily/weekly/monthly 그룹 확인

# 2. fallback 설비 (변압기 -> compressor)
curl https://api.taieng.co.kr/equipment-inspection/items/{transformer_asset_id}
# -> data_quality: FALLBACK, inspection_std: compressor 확인

# 3. setup 테스트
curl -X POST https://api.taieng.co.kr/equipment-inspection/setup/{asset_id}
# -> sets_created: 3 (일상/주간/월간 각 1개) 확인
```

---

## 쬸고: 다음 단계 (A방법 완료 후)

`equipment_type_inspection_map.priority_level = 'HIGH'`인 항목은 A방법 데이터로 교체 예정.  
`inspection_master`에 새 데이터 적재 후 `inspection_std` 업데이트 및 `has_direct_map = TRUE`로 변경하면  
API 코드 변경 없이 자동으로 품질 향상됨.
