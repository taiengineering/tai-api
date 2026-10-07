-- WO-DOC-OBJ02-C2C2: Active Child Contract Correction
-- Field: CANDIDATE → APPROVED_BY_HUMAN (required_status from is_mandatory)
-- Checklist: APPROVED_BY_HUMAN → REJECTED_BY_HUMAN (mechanical field clones)
-- Evidence: CANDIDATE → REJECTED_BY_HUMAN (derived fields rejected in favour of native runtime)
-- Scope: 24 P0 candidate schemas promoted in C2-C1.

-- ── Precondition guards ──────────────────────────────────────────────────────

DO $$
DECLARE
  v_field_count  INT;
  v_cl_count     INT;
  v_ev_count     INT;
BEGIN
  -- 96 CANDIDATE fields belonging to P0 schemas
  SELECT COUNT(*) INTO v_field_count
  FROM runtime_field rf
  JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  WHERE rf.status = 'CANDIDATE'
    AND dsc.status = 'APPROVED_FOR_RUNTIME_USE';

  IF v_field_count <> 96 THEN
    RAISE EXCEPTION 'precondition failed: expected 96 CANDIDATE fields, found %', v_field_count;
  END IF;

  -- 96 APPROVED_BY_HUMAN checklists belonging to P0 schemas
  SELECT COUNT(*) INTO v_cl_count
  FROM runtime_checklist_item rc
  JOIN runtime_form_schema rfs ON rfs.id = rc.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  WHERE rc.status = 'APPROVED_BY_HUMAN'
    AND dsc.status = 'APPROVED_FOR_RUNTIME_USE';

  IF v_cl_count <> 96 THEN
    RAISE EXCEPTION 'precondition failed: expected 96 APPROVED_BY_HUMAN checklists, found %', v_cl_count;
  END IF;

  -- 12 CANDIDATE evidence fields belonging to P0 schemas
  SELECT COUNT(*) INTO v_ev_count
  FROM runtime_evidence_field re
  JOIN runtime_form_schema rfs ON rfs.id = re.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  WHERE re.status = 'CANDIDATE'
    AND dsc.status = 'APPROVED_FOR_RUNTIME_USE';

  IF v_ev_count <> 12 THEN
    RAISE EXCEPTION 'precondition failed: expected 12 CANDIDATE evidence fields, found %', v_ev_count;
  END IF;
END $$;

-- ── 1. Field correction: CANDIDATE → APPROVED_BY_HUMAN ───────────────────────
-- required_status derived from is_mandatory (is_mandatory=true → REQUIRED_BY_HUMAN, else NOT_REQUIRED)

INSERT INTO document_schema_audit (
  table_name, row_id, column_name, previous_state, new_state, reason, changed_at
)
SELECT
  'runtime_field',
  rf.id,
  'status',
  jsonb_build_object('status', rf.status, 'required_status', rf.required_status),
  jsonb_build_object(
    'status', 'APPROVED_BY_HUMAN',
    'required_status', CASE WHEN rf.is_mandatory THEN 'REQUIRED_BY_HUMAN' ELSE 'NOT_REQUIRED' END
  ),
  'WO-DOC-OBJ02-C2C2: active child contract — field promoted from CANDIDATE',
  NOW()
FROM runtime_field rf
JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
WHERE rf.status = 'CANDIDATE'
  AND dsc.status = 'APPROVED_FOR_RUNTIME_USE';

UPDATE runtime_field rf
SET
  status = 'APPROVED_BY_HUMAN',
  required_status = CASE WHEN rf.is_mandatory THEN 'REQUIRED_BY_HUMAN' ELSE 'NOT_REQUIRED' END,
  updated_at = NOW()
FROM runtime_form_schema rfs
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
WHERE rf.form_schema_id = rfs.id
  AND rf.status = 'CANDIDATE'
  AND dsc.status = 'APPROVED_FOR_RUNTIME_USE';

-- ── 2. Checklist correction: APPROVED_BY_HUMAN → REJECTED_BY_HUMAN ───────────
-- These are mechanical field clones (item_order=field_order, raw_text=field_label).

INSERT INTO document_schema_audit (
  table_name, row_id, column_name, previous_state, new_state, reason, changed_at
)
SELECT
  'runtime_checklist_item',
  rc.id,
  'status',
  jsonb_build_object('status', rc.status),
  jsonb_build_object('status', 'REJECTED_BY_HUMAN'),
  'WO-DOC-OBJ02-C2C2: active child contract — duplicate checklist rejected (mechanical clone of field)',
  NOW()
FROM runtime_checklist_item rc
JOIN runtime_form_schema rfs ON rfs.id = rc.form_schema_id
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
WHERE rc.status = 'APPROVED_BY_HUMAN'
  AND dsc.status = 'APPROVED_FOR_RUNTIME_USE';

UPDATE runtime_checklist_item rc
SET
  status = 'REJECTED_BY_HUMAN',
  updated_at = NOW()
FROM runtime_form_schema rfs
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
WHERE rc.form_schema_id = rfs.id
  AND rc.status = 'APPROVED_BY_HUMAN'
  AND dsc.status = 'APPROVED_FOR_RUNTIME_USE';

-- ── 3. Evidence correction: CANDIDATE → REJECTED_BY_HUMAN ────────────────────
-- These are derived evidence fields (date / signature) rejected in favour of native runtime.

INSERT INTO document_schema_audit (
  table_name, row_id, column_name, previous_state, new_state, reason, changed_at
)
SELECT
  'runtime_evidence_field',
  re.id,
  'status',
  jsonb_build_object('status', re.status),
  jsonb_build_object('status', 'REJECTED_BY_HUMAN'),
  'WO-DOC-OBJ02-C2C2: active child contract — derived evidence rejected (date/signature handled natively)',
  NOW()
FROM runtime_evidence_field re
JOIN runtime_form_schema rfs ON rfs.id = re.form_schema_id
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
WHERE re.status = 'CANDIDATE'
  AND dsc.status = 'APPROVED_FOR_RUNTIME_USE';

UPDATE runtime_evidence_field re
SET
  status = 'REJECTED_BY_HUMAN',
  updated_at = NOW()
FROM runtime_form_schema rfs
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
WHERE re.form_schema_id = rfs.id
  AND re.status = 'CANDIDATE'
  AND dsc.status = 'APPROVED_FOR_RUNTIME_USE';

-- ── Post-condition assertions ─────────────────────────────────────────────────

DO $$
DECLARE
  v_field_approved  INT;
  v_cl_rejected     INT;
  v_ev_rejected     INT;
BEGIN
  SELECT COUNT(*) INTO v_field_approved
  FROM runtime_field rf
  JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  WHERE rf.status = 'APPROVED_BY_HUMAN'
    AND dsc.status = 'APPROVED_FOR_RUNTIME_USE';

  IF v_field_approved < 96 THEN
    RAISE EXCEPTION 'post-condition failed: expected >= 96 APPROVED_BY_HUMAN fields, found %', v_field_approved;
  END IF;

  SELECT COUNT(*) INTO v_cl_rejected
  FROM runtime_checklist_item rc
  JOIN runtime_form_schema rfs ON rfs.id = rc.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  WHERE rc.status = 'REJECTED_BY_HUMAN'
    AND dsc.status = 'APPROVED_FOR_RUNTIME_USE';

  IF v_cl_rejected < 96 THEN
    RAISE EXCEPTION 'post-condition failed: expected >= 96 REJECTED_BY_HUMAN checklists, found %', v_cl_rejected;
  END IF;

  SELECT COUNT(*) INTO v_ev_rejected
  FROM runtime_evidence_field re
  JOIN runtime_form_schema rfs ON rfs.id = re.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  WHERE re.status = 'REJECTED_BY_HUMAN'
    AND dsc.status = 'APPROVED_FOR_RUNTIME_USE';

  IF v_ev_rejected < 12 THEN
    RAISE EXCEPTION 'post-condition failed: expected >= 12 REJECTED_BY_HUMAN evidence, found %', v_ev_rejected;
  END IF;
END $$;
