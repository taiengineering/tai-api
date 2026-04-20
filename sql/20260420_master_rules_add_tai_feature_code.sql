ALTER TABLE master_building_legal_rules
  ADD COLUMN IF NOT EXISTS tai_feature_code VARCHAR(50);

COMMENT ON COLUMN master_building_legal_rules.tai_feature_code IS
  'TAI 기능 연결: APPOINTMENT/INSPECTION/REPORT/EDUCATION/DOCUMENT/FIX/CHECKLIST';
