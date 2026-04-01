# 백엔드 작업지시서 — B-FEAT-001
# 섹터 × 플랜 Feature Flag 시스템

> 작성일: 2026-04-01  
> 우선순위: 🟡 중요  
> 작업 대상: Supabase migration + FastAPI router

---

## 배경

현재 tadmin은 INDUSTRY 기반으로만 구성됨.
건물/산업/건설/특수 섹터별로 다른 메뉴·기능이 필요하고,
같은 섹터라도 플랜(STARTER/BUSINESS/ENTERPRISE/CUSTOM)에 따라 제공 기능이 다름.

**핵심 개념:** 틀은 하나, 블록을 섹터+플랜 조합으로 열거나 잠근다.

---

## 작업 1 — DB Migration

### 1-1. system_codes에 plan_code 4개 추가

```sql
INSERT INTO system_codes (category, category_name, code, code_name, sort_order, is_active, is_system)
VALUES
  ('plan_code', '서비스 플랜', '001', 'STARTER',    1, true, true),
  ('plan_code', '서비스 플랜', '002', 'BUSINESS',   2, true, true),
  ('plan_code', '서비스 플랜', '003', 'ENTERPRISE', 3, true, true),
  ('plan_code', '서비스 플랜', '004', 'CUSTOM',     4, true, true)
ON CONFLICT DO NOTHING;
```

### 1-2. system_codes에 sector 4개 추가

```sql
INSERT INTO system_codes (category, category_name, code, code_name, sort_order, is_active, is_system)
VALUES
  ('sector', '사업장 섹터', '001', 'BUILDING',      1, true, true),
  ('sector', '사업장 섹터', '002', 'INDUSTRY',      2, true, true),
  ('sector', '사업장 섹터', '003', 'CONSTRUCTION',  3, true, true),
  ('sector', '사업장 섹터', '004', 'SPECIAL',       4, true, true)
ON CONFLICT DO NOTHING;
```

### 1-3. factories.sector 컬럼 추가 + site_type 기반 자동 매핑

```sql
ALTER TABLE factories
  ADD COLUMN IF NOT EXISTS sector VARCHAR(20)
    CHECK (sector IN ('BUILDING','INDUSTRY','CONSTRUCTION','SPECIAL'))
    DEFAULT 'INDUSTRY';

-- site_type → sector 자동 매핑
UPDATE factories SET sector =
  CASE site_type
    WHEN '001' THEN 'INDUSTRY'       -- 공장
    WHEN '002' THEN 'BUILDING'       -- 사무소
    WHEN '003' THEN 'CONSTRUCTION'   -- 건설현장
    WHEN '004' THEN 'INDUSTRY'       -- 물류센터
    WHEN '005' THEN 'BUILDING'       -- 의료기관
    WHEN '006' THEN 'BUILDING'       -- 교육기관
    ELSE 'INDUSTRY'
  END
WHERE sector IS NULL OR sector = 'INDUSTRY';
```

### 1-4. factory_features 테이블 신규 생성

```sql
CREATE TABLE IF NOT EXISTS factory_features (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  feature_code     VARCHAR(50) UNIQUE NOT NULL,
  feature_name     VARCHAR(100) NOT NULL,
  feature_desc     TEXT,
  sector           VARCHAR(20) NOT NULL DEFAULT 'ALL',  -- ALL / INDUSTRY / BUILDING / CONSTRUCTION / SPECIAL
  min_plan_order   SMALLINT NOT NULL DEFAULT 1,          -- 1=STARTER, 2=BUSINESS, 3=ENTERPRISE, 4=CUSTOM
  menu_path        VARCHAR(200),                          -- 연결 HTML 경로 (예: facility/process-list.html)
  menu_group       VARCHAR(50),                           -- 메뉴 그룹 (예: FACILITY, WORK, CONSTRUCTION)
  is_active        BOOLEAN DEFAULT true,
  sort_order       SMALLINT DEFAULT 0,
  created_at       TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE factory_features IS '섹터×플랜 기반 기능 블록 제어 마스터';
```

### 1-5. factory_features 기초 데이터 INSERT

```sql
INSERT INTO factory_features
  (feature_code, feature_name, sector, min_plan_order, menu_path, menu_group, sort_order)
VALUES
  -- 공통 (ALL)
  ('DASHBOARD',              '대시보드',           'ALL',          1, 'dashboard.html',                   'COMMON',       1),
  ('LEGAL_DIAGNOSIS_BASIC',  '기초 법령진단',       'ALL',          1, 'diagnosis-step1.html',              'LEGAL',        2),
  ('LEGAL_DIAGNOSIS_PROCESS','공정·공종 법령진단',  'ALL',          2, 'diagnosis-step2.html',              'LEGAL',        3),
  ('LEGAL_DIAGNOSIS_FULL',   '종합 리포트',         'ALL',          3, 'diagnosis-result.html',             'LEGAL',        4),
  ('WORK_ASSIGN',            '업무 할당·분산',      'ALL',          1, 'work/work-assign.html',             'WORK',         5),
  ('EDUCATION_BASIC',        '교육관리',            'ALL',          1, 'education/education-list.html',     'EDUCATION',    6),
  ('REPORT_FORM',            '신고서식 자동화',      'ALL',          2, 'report/report-form.html',           'REPORT',       7),
  ('REPORT_AUTO',            '전자제출 자동화',      'ALL',          3, 'report/report-auto.html',           'REPORT',       8),
  ('HISTORY_6M',             '이력 6개월',          'ALL',          1, NULL,                                'HISTORY',      9),
  ('HISTORY_UNLIMITED',      '이력 무제한',         'ALL',          2, NULL,                                'HISTORY',      10),
  ('ALERT_BASIC',            '알림 기본',           'ALL',          1, NULL,                                'ALERT',        11),
  ('API_CONNECT',            'API 연동',            'ALL',          2, NULL,                                'INTEGRATION',  12),
  -- INDUSTRY 전용
  ('FACILITY_BASIC',         '시설 기본관리',       'INDUSTRY',     1, 'facility/factory-list.html',        'FACILITY',     20),
  ('FACILITY_PROCESS',       '공정관리',            'INDUSTRY',     2, 'facility/process-list.html',        'FACILITY',     21),
  ('FACILITY_EQUIPMENT',     '설비관리',            'INDUSTRY',     2, 'facility/equipment-list.html',      'FACILITY',     22),
  ('FACILITY_CALENDAR',      '점검 캘린더',         'INDUSTRY',     1, 'facility/calendar.html',            'FACILITY',     23),
  ('WORK_TBM',               'TBM 관리',            'INDUSTRY',     2, 'work/tbm-list.html',                'WORK',         24),
  ('WORK_RISK',              '위험성평가',          'INDUSTRY',     2, 'work/risk-assessment.html',         'WORK',         25),
  ('WORKER_BASIC',           '작업자 관리',         'INDUSTRY',     1, 'worker/worker-list.html',           'WORKER',       26),
  -- BUILDING 전용
  ('BUILDING_INSPECTION',    '점검관리',            'BUILDING',     1, 'facility/inspection-list.html',     'FACILITY',     30),
  ('BUILDING_EQUIPMENT',     '설비관리',            'BUILDING',     2, 'facility/equipment-list.html',      'FACILITY',     31),
  ('BUILDING_FIRE',          '소방관리',            'BUILDING',     2, 'facility/fire-list.html',           'FACILITY',     32),
  -- CONSTRUCTION 전용
  ('CONSTRUCTION_SITE',      '건설현장 관리',       'CONSTRUCTION', 1, 'construction/site-list.html',       'CONSTRUCTION', 40),
  ('CONSTRUCTION_PROCESS',   '공정 관리',           'CONSTRUCTION', 1, 'construction/process-list.html',    'CONSTRUCTION', 41),
  ('CONSTRUCTION_PTW',       '위험작업허가(PTW)',    'CONSTRUCTION', 2, 'construction/ptw-list.html',        'CONSTRUCTION', 42),
  ('CONSTRUCTION_ENTRY',     '작업자 출입관리',     'CONSTRUCTION', 2, 'construction/entry-list.html',      'CONSTRUCTION', 43),
  ('CONSTRUCTION_SAFETY',    '안전점검',            'CONSTRUCTION', 1, 'construction/safety-check.html',    'CONSTRUCTION', 44),
  ('CONSTRUCTION_ACCIDENT',  '사고관리',            'CONSTRUCTION', 2, 'construction/accident-list.html',   'CONSTRUCTION', 45)
ON CONFLICT (feature_code) DO NOTHING;
```

---

## 작업 2 — API 엔드포인트 추가

**파일:** `routers/feature_flags.py` 신규 생성

```python
from fastapi import APIRouter, Query
from app.database import supabase

router = APIRouter(prefix="/feature-flags", tags=["Feature Flags"])

PLAN_ORDER = {'STARTER': 1, 'BUSINESS': 2, 'ENTERPRISE': 3, 'CUSTOM': 4}

@router.get("/")
async def get_feature_flags(
    sector: str = Query(..., description="INDUSTRY/BUILDING/CONSTRUCTION/SPECIAL"),
    plan:   str = Query(..., description="STARTER/BUSINESS/ENTERPRISE/CUSTOM")
):
    """
    섹터+플랜 기반으로 열린 feature_code 목록 반환
    locked: 섹터는 맞지만 플랜 부족
    hidden: 섹터 불일치 (완전 숨김)
    """
    plan_order = PLAN_ORDER.get(plan.upper(), 1)

    res = supabase.table('factory_features') \
        .select('feature_code,feature_name,sector,min_plan_order,menu_path,menu_group,sort_order') \
        .eq('is_active', True) \
        .order('sort_order') \
        .execute()

    features = res.data or []
    result = {'open': [], 'locked': [], 'hidden': []}

    for f in features:
        f_sector = f['sector']
        f_min    = f['min_plan_order']

        sector_match = (f_sector == 'ALL' or f_sector == sector.upper())

        if not sector_match:
            result['hidden'].append(f['feature_code'])
        elif plan_order >= f_min:
            result['open'].append(f)
        else:
            result['locked'].append({
                **f,
                'required_plan': [k for k,v in PLAN_ORDER.items() if v == f_min][0]
            })

    return {'status': 'success', 'data': result}
```

**main.py에 라우터 등록:**
```python
from routers.feature_flags import router as feature_flags_router
app.include_router(feature_flags_router)
```

---

## 작업 3 — contracts.plan_code 정합성 확인

```sql
-- contracts 테이블의 plan_code 현재 값 확인
SELECT DISTINCT plan_code, COUNT(*) FROM contracts GROUP BY plan_code;

-- factories에 plan_code 직접 추가 (contracts 조인 대신 빠른 조회용)
ALTER TABLE factories
  ADD COLUMN IF NOT EXISTS plan_code VARCHAR(20) DEFAULT 'STARTER';
```

---

## 완료 기준

- [ ] factory_features 테이블 생성 및 데이터 INSERT 완료
- [ ] factories.sector 컬럼 추가 + site_type 매핑 완료  
- [ ] GET /feature-flags?sector=CONSTRUCTION&plan=BUSINESS 응답 정상
- [ ] system_codes plan_code 4개 추가 완료
