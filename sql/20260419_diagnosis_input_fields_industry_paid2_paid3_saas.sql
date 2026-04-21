-- PAID2/PAID3 산업 유료 진단 입력 — SaaS 정렬 (2026-04-19)
-- Supabase SQL Editor 또는 마이그레이션 파이프라인에서 실행.

-- ── 1-1. PAID2: 기존 공정 유무 필드 비활성화 ─────────────────────────
UPDATE diagnosis_input_fields
SET is_active = false
WHERE sector = 'INDUSTRY' AND tier = 'PAID2'
  AND field_code IN (
    'has_welding', 'has_painting', 'has_plating',
    'has_casting', 'has_heat_treatment', 'has_high_place_work'
  );

-- process_list: KSIC 기반 searchable_select 구조
UPDATE diagnosis_input_fields
SET input_options = '{
  "columns": [
    {
      "key": "process_name",
      "type": "searchable_select",
      "label": "공정명",
      "source": "ksic_process_map",
      "source_key": "process_path",
      "source_label": "process_lv2",
      "allow_manual": true,
      "manual_placeholder": "직접 입력 (예: 도장, 열처리 등)",
      "required": true
    },
    {
      "key": "hazard_codes",
      "type": "multi_select",
      "label": "주요 위험요인",
      "options": ["전도", "추락", "협착", "충돌", "화재", "폭발", "감전", "질식", "절단", "중량물", "분진", "소음", "유해물질", "고온", "기타"],
      "required": false
    },
    {
      "key": "worker_count",
      "type": "number",
      "label": "작업자 수",
      "min": 0,
      "required": false
    },
    {
      "key": "is_primary",
      "type": "boolean",
      "label": "주요공정",
      "required": false
    }
  ],
  "add_row_label": "공정 추가",
  "min_rows": 1
}'::jsonb,
    help_text = 'KSIC 업종 기반 공정 목록에서 선택하거나, 직접 입력하여 추가할 수 있습니다'
WHERE sector = 'INDUSTRY' AND tier = 'PAID2' AND field_code = 'process_list';

UPDATE diagnosis_input_fields
SET is_active = false
WHERE sector = 'INDUSTRY' AND tier = 'PAID2' AND field_code = 'process_worker_data';

UPDATE diagnosis_input_fields
SET is_active = false
WHERE sector = 'INDUSTRY' AND tier = 'PAID2' AND field_code = 'process_count';

-- ── 1-2. PAID3: 구 설비 필드 비활성화 ───────────────────────────────
UPDATE diagnosis_input_fields
SET is_active = false
WHERE sector = 'INDUSTRY' AND tier = 'PAID3'
  AND field_code IN (
    'has_crane', 'crane_count', 'has_press', 'has_conveyor',
    'has_pressure_vessel', 'has_forklift', 'forklift_count',
    'has_grinding', 'has_rolling', 'has_injection', 'has_elevator',
    'equipment_inspection_status'
  );

-- equipment_list: 없을 때만 INSERT (재실행 안전)
INSERT INTO diagnosis_input_fields (
  sector, tier, field_group, field_code, field_name, field_type,
  input_options, placeholder, help_text, is_required, sort_order, is_active
)
SELECT
  'INDUSTRY', 'PAID3', '설비', 'equipment_list', '설비 목록', 'table',
  '{
    "columns": [
      {
        "key": "equipment_type",
        "type": "select",
        "label": "설비 유형",
        "source": "system_codes",
        "source_category": "equipment_type",
        "allow_manual": true,
        "manual_placeholder": "기타 설비 직접 입력",
        "required": true
      },
      {
        "key": "asset_name",
        "type": "text",
        "label": "설비명/모델",
        "placeholder": "예: 5톤 천장크레인, 150톤 프레스",
        "required": false
      },
      {
        "key": "quantity",
        "type": "number",
        "label": "수량",
        "min": 1,
        "required": true
      },
      {
        "key": "capacity_value",
        "type": "number",
        "label": "용량",
        "required": false
      },
      {
        "key": "capacity_unit",
        "type": "select",
        "label": "단위",
        "source": "system_codes",
        "source_category": "equipment_capacity_unit",
        "required": false
      },
      {
        "key": "is_legal_target",
        "type": "boolean",
        "label": "법정검사대상",
        "help_text": "산안법·에너지법 등 정기검사 대상 여부",
        "required": false
      }
    ],
    "add_row_label": "설비 추가",
    "min_rows": 1
  }'::jsonb,
  '보유 설비를 유형별로 등록하세요',
  'SaaS 설비 등록과 동일한 40개 유형에서 선택하거나, 기타로 직접 입력할 수 있습니다',
  true, 30, true
WHERE NOT EXISTS (
  SELECT 1 FROM diagnosis_input_fields
  WHERE sector = 'INDUSTRY' AND tier = 'PAID3' AND field_code = 'equipment_list'
);
