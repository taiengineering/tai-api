# TAI Cursor 작업지시서 — 설비 점검 매핑 테이블 추가 (방법 C)

> 우선순위: 🟡 중간  
> 작성일: 2026-03-31  
> 레포: taiengineering/tai-api  
> 대상 파일: DDL(Supabase) + `routers/engine_equipment.py`

---

## 배경

현재 설비(`equipment_assets`)를 등록해도 점검항목/주기가 자동 연결되지 않습니다.

**원인: 코드 체계 불일치**
```
equipment_assets.equipment_type_code = '014' (숫자 코드)
inspection_master.equipment_std = 'boiler'   (영문)
```
두 테이블을 연결하는 매핑 테이블이 없어서 JOIN 불가.

**현재 매핑 가능한 설비 (40종 중 9종):**
| equipment_type_code | 한글명 | inspection_master.equipment_std |
|---|---|---|
| 011 | 펌프 | pump |
| 012 | 압축기 | compressor |
| 014 | 보일러 | boiler |
| 018 | 팬 | fan |
| 021 | 크레인 | crane |
| 023 | 프레스 | press |
| 024 | 컨베이어 | conveyor |
| 025 | 승강기 | elevator |
| 038 | 압력용기 | pressure_vessel |

나머지 31종은 유사 설비 fallback 처리.

---

## STEP 1. DB 매핑 테이블 생성 (Supabase apply_migration)

```sql
-- 설비 type_code → inspection_master.equipment_std 매핑
CREATE TABLE IF NOT EXISTS equipment_type_inspection_map (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type_code       TEXT NOT NULL,          -- system_codes equipment_type code (예: '014')
  type_name_ko    TEXT NOT NULL,          -- 한글명 (예: '보일러')
  equipment_std   TEXT,                   -- inspection_master.equipment_std (예: 'boiler')
  fallback_std    TEXT,                   -- 직접 매핑 없을 때 유사 설비 std
  map_quality     TEXT DEFAULT 'EXACT',   -- EXACT=정확/SIMILAR=유사/NONE=없음
  note            TEXT,
  is_active       BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE equipment_type_inspection_map IS
  '설비 type_code(숫자) ↔ inspection_master.equipment_std(영문) 매핑. A방법 데이터 수집 후 교체 예정';

-- 9종 정확 매핑
INSERT INTO equipment_type_inspection_map
  (type_code, type_name_ko, equipment_std, map_quality) VALUES
  ('011', '펌프',    'pump',            'EXACT'),
  ('012', '압축기',  'compressor',      'EXACT'),
  ('014', '보일러',  'boiler',          'EXACT'),
  ('018', '팬',      'fan',             'EXACT'),
  ('021', '크레인',  'crane',           'EXACT'),
  ('023', '프레스',  'press',           'EXACT'),
  ('024', '컨베이어','conveyor',        'EXACT'),
  ('025', '승강기',  'elevator',        'EXACT'),
  ('038', '압력용기','pressure_vessel', 'EXACT');

-- 유사 fallback 매핑 (31종)
INSERT INTO equipment_type_inspection_map
  (type_code, type_name_ko, equipment_std, fallback_std, map_quality, note) VALUES
  ('001', '변압기',       NULL, 'pump',            'SIMILAR', '전기설비 — 임시 pump fallback'),
  ('002', '기중차단기',   NULL, 'pump',            'SIMILAR', '전기설비 — 임시 pump fallback'),
  ('003', '진공차단기',   NULL, 'pump',            'SIMILAR', '전기설비 — 임시 pump fallback'),
  ('004', '배선용차단기', NULL, 'pump',            'SIMILAR', '전기설비 — 임시 pump fallback'),
  ('005', '누전차단기',   NULL, 'pump',            'SIMILAR', '전기설비 — 임시 pump fallback'),
  ('006', '배전반',       NULL, 'pump',            'SIMILAR', '전기설비 — 임시 pump fallback'),
  ('007', '분전반',       NULL, 'pump',            'SIMILAR', '전기설비 — 임시 pump fallback'),
  ('008', '전동기',       NULL, 'pump',            'SIMILAR', '회전기계 — pump fallback'),
  ('009', 'UPS',          NULL, 'pump',            'SIMILAR', '전기설비 — 임시 pump fallback'),
  ('010', '비상발전기',   NULL, 'pump',            'SIMILAR', '회전기계 — pump fallback'),
  ('013', '열교환기',     NULL, 'pressure_vessel', 'SIMILAR', '압력용기 유사'),
  ('015', '탱크',         NULL, 'pressure_vessel', 'SIMILAR', '압력용기 유사'),
  ('016', '밸브',         NULL, 'pump',            'SIMILAR', '배관계통 — pump fallback'),
  ('017', '배관',         NULL, 'pump',            'SIMILAR', '배관계통 — pump fallback'),
  ('019', '냉동기',       NULL, 'compressor',      'SIMILAR', '압축기계 유사'),
  ('020', '칠러',         NULL, 'compressor',      'SIMILAR', '압축기계 유사'),
  ('022', '호이스트',     NULL, 'crane',           'SIMILAR', '양중기계 유사'),
  ('026', '에스컬레이터', NULL, 'elevator',        'SIMILAR', '승강설비 유사'),
  ('027', '가스탱크',     NULL, 'pressure_vessel', 'SIMILAR', '압력용기 유사'),
  ('028', 'LPG탱크',      NULL, 'pressure_vessel', 'SIMILAR', '압력용기 유사'),
  ('029', '화학물질탱크', NULL, 'pressure_vessel', 'SIMILAR', '압력용기 유사'),
  ('030', '유류탱크',     NULL, 'pressure_vessel', 'SIMILAR', '압력용기 유사'),
  ('031', '스프링클러',   NULL, 'pump',            'SIMILAR', '소방설비 — pump fallback'),
  ('032', '자동화재탐지', NULL, 'pump',            'SIMILAR', '소방설비 — pump fallback'),
  ('033', '소화기',       NULL, 'pump',            'NONE',    'A방법 수집 후 교체 필요'),
  ('034', '소화전',       NULL, 'pump',            'SIMILAR', '소방설비 — pump fallback'),
  ('035', '배기시설',     NULL, 'fan',             'SIMILAR', '팬/송풍 유사'),
  ('036', '집진기',       NULL, 'fan',             'SIMILAR', '팬/송풍 유사'),
  ('037', '오수처리시설', NULL, 'pump',            'SIMILAR', '펌프계통 유사'),
  ('039', '냉동기(냉각)', NULL, 'compressor',      'SIMILAR', '압축기계 유사'),
  ('040', '기타',         NULL, NULL,              'NONE',    '매핑 불가 — 점검항목 없음');
```

---

## STEP 2. 설비 등록 시 점검항목 자동 조회 API

### 파일: `routers/engine_equipment.py`
### 엔드포인트: `GET /equipment-assets/{asset_id}/inspection-items`

```python
@router.get("/{asset_id}/inspection-items")
async def get_equipment_inspection_items(asset_id: str):
    """
    설비 ID → type_code → equipment_std 조회 → inspection_master 점검항목 반환
    """
    supabase = get_supabase()

    # 1. 설비 조회
    asset = supabase.table('equipment_assets') \
        .select('id, asset_name, equipment_type_code') \
        .eq('id', asset_id).single().execute().data
    if not asset:
        raise HTTPException(status_code=404, detail='설비를 찾을 수 없습니다.')

    type_code = asset.get('equipment_type_code')
    if not type_code:
        return {'status': 'success', 'data': {'items': [], 'reason': 'type_code 없음'}}

    # 2. 매핑 테이블 조회
    mapping = supabase.table('equipment_type_inspection_map') \
        .select('equipment_std, fallback_std, map_quality') \
        .eq('type_code', type_code) \
        .eq('is_active', True) \
        .single().execute().data

    if not mapping:
        return {'status': 'success', 'data': {'items': [], 'reason': '매핑 없음'}}

    # 3. equipment_std 결정 (EXACT 우선, fallback 차선)
    std = mapping.get('equipment_std') or mapping.get('fallback_std')
    quality = mapping.get('map_quality', 'NONE')
    if not std:
        return {'status': 'success', 'data': {'items': [], 'reason': 'std 없음 (A방법 수집 필요)'}}

    # 4. inspection_master 조회
    items = supabase.table('inspection_master') \
        .select('inspection_item, cycle, rule_type, risk_level') \
        .eq('equipment_std', std) \
        .eq('is_active', True) \
        .order('cycle').execute().data or []

    # 5. 주기 분류
    CYCLE_ORDER = {'daily': 1, 'weekly': 2, 'monthly': 3, 'quarterly': 4, 'yearly': 5}
    items.sort(key=lambda x: CYCLE_ORDER.get(x.get('cycle', ''), 99))

    return {
        'status': 'success',
        'data': {
            'asset_id':      asset_id,
            'asset_name':    asset.get('asset_name'),
            'type_code':     type_code,
            'equipment_std': std,
            'map_quality':   quality,  # EXACT/SIMILAR/NONE
            'item_count':    len(items),
            'items':         items,
            'note': '⚠️ SIMILAR 매핑 — 실제 설비와 다를 수 있음. A방법 데이터 수집 후 교체 예정.' if quality == 'SIMILAR' else ''
        }
    }
```

---

## STEP 3. equipment_model_master ↔ inspection_master 한글 매핑 보완

`equipment_model_master.equipment_std` (한글 479종)과 
`inspection_master.equipment_std` (영문 15종) 연결을 위한 컬럼 추가:

```sql
-- equipment_model_master에 영문 std 컬럼 추가
ALTER TABLE equipment_model_master
  ADD COLUMN IF NOT EXISTS equipment_std_eng TEXT;

COMMENT ON COLUMN equipment_model_master.equipment_std_eng IS
  'inspection_master.equipment_std과 JOIN용 영문 표준명. A방법 수집 후 전체 보완 예정';

-- 한글명 → 영문 매핑 가능한 것만 우선 적용
UPDATE equipment_model_master SET equipment_std_eng = 'boiler'
  WHERE equipment_std ILIKE '%보일러%';
UPDATE equipment_model_master SET equipment_std_eng = 'pump'
  WHERE equipment_std ILIKE '%펌프%';
UPDATE equipment_model_master SET equipment_std_eng = 'compressor'
  WHERE equipment_std ILIKE '%압축기%' OR equipment_std ILIKE '%컴프레서%';
UPDATE equipment_model_master SET equipment_std_eng = 'crane'
  WHERE equipment_std ILIKE '%크레인%';
UPDATE equipment_model_master SET equipment_std_eng = 'elevator'
  WHERE equipment_std ILIKE '%승강기%' OR equipment_std ILIKE '%엘리베이터%';
UPDATE equipment_model_master SET equipment_std_eng = 'conveyor'
  WHERE equipment_std ILIKE '%컨베이어%';
UPDATE equipment_model_master SET equipment_std_eng = 'fan'
  WHERE equipment_std ILIKE '%팬%' OR equipment_std ILIKE '%송풍%';
UPDATE equipment_model_master SET equipment_std_eng = 'pressure_vessel'
  WHERE equipment_std ILIKE '%압력용기%' OR equipment_std ILIKE '%탱크%'
    OR equipment_std ILIKE '%저장조%';
UPDATE equipment_model_master SET equipment_std_eng = 'press'
  WHERE equipment_std ILIKE '%프레스%';
```

---

## 완료 체크리스트

```
□ equipment_type_inspection_map 테이블 생성
□ 40종 매핑 데이터 INSERT (9 EXACT + 30 SIMILAR/NONE)
□ GET /equipment-assets/{id}/inspection-items 엔드포인트 구현
□ equipment_model_master.equipment_std_eng 컬럼 추가 + 한글→영문 매핑 UPDATE
□ Railway 배포 후 버전 확인
```

## 검증 방법

```bash
# 보일러 설비 점검항목 조회 테스트
curl https://api.taieng.co.kr/equipment-assets/{보일러_asset_id}/inspection-items
# → items: 10개 (daily 4 / weekly 2 / monthly 4), map_quality: EXACT

# 변압기 조회 (SIMILAR fallback)
curl https://api.taieng.co.kr/equipment-assets/{변압기_asset_id}/inspection-items
# → map_quality: SIMILAR, note 경고 포함
```
