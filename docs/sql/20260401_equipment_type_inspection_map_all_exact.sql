-- 기존 DB에 SIMILAR/NONE 으로 들어간 행을 전부 EXACT 로 승격 (equipment_std = 기존 fallback 반영)
-- Supabase SQL Editor 에서 20260331 스크립트 적용 후 실행

UPDATE equipment_type_inspection_map SET
  equipment_std = COALESCE(equipment_std, fallback_std),
  fallback_std = NULL,
  map_quality = 'EXACT'
WHERE type_code IS NOT NULL AND type_code <> '040';

UPDATE equipment_type_inspection_map SET
  equipment_std = NULL,
  fallback_std = NULL,
  map_quality = 'EXACT',
  note = '기타 — 표준 미정, 점검항목 없음(필요 시 관리자 매핑)'
WHERE type_code = '040';
