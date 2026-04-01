-- TAI: 설비 type_code ↔ inspection_master.equipment_std 매핑 (작업지시서 20260331)
-- Supabase: SQL Editor 또는 migration 으로 적용

-- ── 1) 매핑 테이블 ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS equipment_type_inspection_map (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type_code       TEXT NOT NULL UNIQUE,
  type_name_ko    TEXT NOT NULL,
  equipment_std   TEXT,
  fallback_std    TEXT,
  map_quality     TEXT DEFAULT 'EXACT',
  note            TEXT,
  is_active       BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE equipment_type_inspection_map IS
  '설비 type_code(숫자) ↔ inspection_master.equipment_std(영문) 매핑. A방법 데이터 수집 후 교체 예정';

-- ── 2) 9종 EXACT ───────────────────────────────────────────
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
  ('038', '압력용기','pressure_vessel', 'EXACT')
ON CONFLICT (type_code) DO UPDATE SET
  type_name_ko = EXCLUDED.type_name_ko,
  equipment_std = EXCLUDED.equipment_std,
  fallback_std = NULL,
  map_quality = EXCLUDED.map_quality,
  note = NULL;

-- ── 3) 나머지 31종 — 전부 equipment_std 직접 지정 + EXACT (fallback 없음) ───────
INSERT INTO equipment_type_inspection_map
  (type_code, type_name_ko, equipment_std, fallback_std, map_quality, note) VALUES
  ('001', '변압기',       'pump',            NULL, 'EXACT', '전기설비 — pump 점검항목'),
  ('002', '기중차단기',   'pump',            NULL, 'EXACT', '전기설비 — pump 점검항목'),
  ('003', '진공차단기',   'pump',            NULL, 'EXACT', '전기설비 — pump 점검항목'),
  ('004', '배선용차단기', 'pump',            NULL, 'EXACT', '전기설비 — pump 점검항목'),
  ('005', '누전차단기',   'pump',            NULL, 'EXACT', '전기설비 — pump 점검항목'),
  ('006', '배전반',       'pump',            NULL, 'EXACT', '전기설비 — pump 점검항목'),
  ('007', '분전반',       'pump',            NULL, 'EXACT', '전기설비 — pump 점검항목'),
  ('008', '전동기',       'pump',            NULL, 'EXACT', '회전기계 — pump 점검항목'),
  ('009', 'UPS',          'pump',            NULL, 'EXACT', '전기설비 — pump 점검항목'),
  ('010', '비상발전기',   'pump',            NULL, 'EXACT', '회전기계 — pump 점검항목'),
  ('013', '열교환기',     'pressure_vessel', NULL, 'EXACT', '압력용기 점검항목'),
  ('015', '탱크',         'pressure_vessel', NULL, 'EXACT', '압력용기 점검항목'),
  ('016', '밸브',         'pump',            NULL, 'EXACT', '배관계통 — pump 점검항목'),
  ('017', '배관',         'pump',            NULL, 'EXACT', '배관계통 — pump 점검항목'),
  ('019', '냉동기',       'compressor',      NULL, 'EXACT', '압축기계 점검항목'),
  ('020', '칠러',         'compressor',      NULL, 'EXACT', '압축기계 점검항목'),
  ('022', '호이스트',     'crane',           NULL, 'EXACT', '양중기계 점검항목'),
  ('026', '에스컬레이터', 'elevator',        NULL, 'EXACT', '승강설비 점검항목'),
  ('027', '가스탱크',     'pressure_vessel', NULL, 'EXACT', '압력용기 점검항목'),
  ('028', 'LPG탱크',      'pressure_vessel', NULL, 'EXACT', '압력용기 점검항목'),
  ('029', '화학물질탱크', 'pressure_vessel', NULL, 'EXACT', '압력용기 점검항목'),
  ('030', '유류탱크',     'pressure_vessel', NULL, 'EXACT', '압력용기 점검항목'),
  ('031', '스프링클러',   'pump',            NULL, 'EXACT', '소방설비 — pump 점검항목'),
  ('032', '자동화재탐지', 'pump',            NULL, 'EXACT', '소방설비 — pump 점검항목'),
  ('033', '소화기',       'pump',            NULL, 'EXACT', '소화기 — pump 점검항목 연동'),
  ('034', '소화전',       'pump',            NULL, 'EXACT', '소방설비 — pump 점검항목'),
  ('035', '배기시설',     'fan',             NULL, 'EXACT', '팬/송풍 점검항목'),
  ('036', '집진기',       'fan',             NULL, 'EXACT', '팬/송풍 점검항목'),
  ('037', '오수처리시설', 'pump',            NULL, 'EXACT', '펌프계통 점검항목'),
  ('039', '냉동기(냉각)', 'compressor',      NULL, 'EXACT', '압축기계 점검항목'),
  ('040', '기타',         NULL,              NULL, 'EXACT', '기타 — 표준 미정, 점검항목 없음(관리자 PATCH 가능)')
ON CONFLICT (type_code) DO UPDATE SET
  type_name_ko = EXCLUDED.type_name_ko,
  equipment_std = EXCLUDED.equipment_std,
  fallback_std = EXCLUDED.fallback_std,
  map_quality = EXCLUDED.map_quality,
  note = EXCLUDED.note;

-- ── 4) equipment_model_master 영문 컬럼 ─────────────────────
ALTER TABLE equipment_model_master
  ADD COLUMN IF NOT EXISTS equipment_std_eng TEXT;

COMMENT ON COLUMN equipment_model_master.equipment_std_eng IS
  'inspection_master.equipment_std과 JOIN용 영문 표준명. A방법 수집 후 전체 보완 예정';

UPDATE equipment_model_master SET equipment_std_eng = 'boiler'
  WHERE equipment_std ILIKE '%보일러%';
UPDATE equipment_model_master SET equipment_std_eng = 'pump'
  WHERE equipment_std ILIKE '%펌프%' AND equipment_std_eng IS NULL;
UPDATE equipment_model_master SET equipment_std_eng = 'compressor'
  WHERE (equipment_std ILIKE '%압축기%' OR equipment_std ILIKE '%컴프레서%') AND equipment_std_eng IS NULL;
UPDATE equipment_model_master SET equipment_std_eng = 'crane'
  WHERE equipment_std ILIKE '%크레인%' AND equipment_std_eng IS NULL;
UPDATE equipment_model_master SET equipment_std_eng = 'elevator'
  WHERE (equipment_std ILIKE '%승강기%' OR equipment_std ILIKE '%엘리베이터%') AND equipment_std_eng IS NULL;
UPDATE equipment_model_master SET equipment_std_eng = 'conveyor'
  WHERE equipment_std ILIKE '%컨베이어%' AND equipment_std_eng IS NULL;
UPDATE equipment_model_master SET equipment_std_eng = 'fan'
  WHERE (equipment_std ILIKE '%팬%' OR equipment_std ILIKE '%송풍%') AND equipment_std_eng IS NULL;
UPDATE equipment_model_master SET equipment_std_eng = 'pressure_vessel'
  WHERE (equipment_std ILIKE '%압력용기%' OR equipment_std ILIKE '%탱크%' OR equipment_std ILIKE '%저장조%')
    AND equipment_std_eng IS NULL;
UPDATE equipment_model_master SET equipment_std_eng = 'press'
  WHERE equipment_std ILIKE '%프레스%' AND equipment_std_eng IS NULL;
