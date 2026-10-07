-- WO-DOC-OBJ02-C2C2: Active Child Contract Correction CORR-001
-- Field: CANDIDATE → APPROVED_BY_HUMAN (required_status from field_candidate.is_mandatory)
-- Checklist: APPROVED_BY_HUMAN → REJECTED_BY_HUMAN (mechanical field clones verified = 96)
-- Evidence: CANDIDATE → REJECTED_BY_HUMAN (natively-handled upload types = 12)
-- P0 scope: 24 schemas via document_type_mapping.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
--           AND runtime_form_schema.status = 'CANDIDATE'

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
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rf.status = 'CANDIDATE'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_field_count <> 96 THEN
    RAISE EXCEPTION 'precondition failed: expected 96 CANDIDATE fields, found %', v_field_count;
  END IF;

  -- 96 APPROVED_BY_HUMAN checklists belonging to P0 schemas
  SELECT COUNT(*) INTO v_cl_count
  FROM runtime_checklist_item rc
  JOIN runtime_form_schema rfs ON rfs.id = rc.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rc.status = 'APPROVED_BY_HUMAN'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_cl_count <> 96 THEN
    RAISE EXCEPTION 'precondition failed: expected 96 APPROVED_BY_HUMAN checklists, found %', v_cl_count;
  END IF;

  -- 12 CANDIDATE evidence fields belonging to P0 schemas
  SELECT COUNT(*) INTO v_ev_count
  FROM runtime_evidence_field re
  JOIN runtime_form_schema rfs ON rfs.id = re.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE re.status = 'CANDIDATE'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_ev_count <> 12 THEN
    RAISE EXCEPTION 'precondition failed: expected 12 CANDIDATE evidence fields, found %', v_ev_count;
  END IF;
END $$;

-- ── Duplication guard: verify exactly 96 mechanical field clones ──────────────
-- item_order = field_order AND trim(raw_text) = trim(field_label)

DO $$
DECLARE
  v_clone_count INT;
BEGIN
  SELECT COUNT(*) INTO v_clone_count
  FROM runtime_checklist_item rc
  JOIN runtime_form_schema rfs ON rfs.id = rc.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  JOIN runtime_field rf
    ON  rf.form_schema_id    = rfs.id
    AND rf.field_order       = rc.item_order
    AND trim(rf.field_label) = trim(rc.raw_text)
  WHERE rc.status = 'APPROVED_BY_HUMAN'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_clone_count <> 96 THEN
    RAISE EXCEPTION 'duplication guard failed: expected 96 mechanical field clones, found %', v_clone_count;
  END IF;
END $$;

-- ── Derived evidence guard: verify exactly 12 natively-handled evidence fields ──
-- timestamp_auto (DATE) and signature (SIGNATURE) are handled by native runtime

DO $$
DECLARE
  v_derived_count INT;
BEGIN
  SELECT COUNT(*) INTO v_derived_count
  FROM runtime_evidence_field re
  JOIN runtime_form_schema rfs ON rfs.id = re.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE re.status = 'CANDIDATE'
    AND re.upload_type IN ('timestamp_auto', 'signature')
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_derived_count <> 12 THEN
    RAISE EXCEPTION 'derived evidence guard failed: expected 12 natively-handled evidence fields, found %', v_derived_count;
  END IF;
END $$;

-- ── 1. Field correction: CANDIDATE → APPROVED_BY_HUMAN ───────────────────────
-- required_status derived from field_candidate.is_mandatory (NULL fk_id → NOT_REQUIRED)

INSERT INTO document_schema_audit (
  target_table, target_id, action, changed_by, previous_state, new_state, reason, created_at
)
SELECT
  'runtime_field',
  rf.id,
  'C2C2_ACTIVE_CHILD_CORRECTION',
  'migration:20261007131755',
  jsonb_build_object('status', rf.status, 'required_status', rf.required_status),
  jsonb_build_object(
    'status', 'APPROVED_BY_HUMAN',
    'required_status', CASE
      WHEN fc.is_mandatory IS TRUE THEN 'REQUIRED_BY_HUMAN'
      ELSE 'NOT_REQUIRED'
    END
  ),
  'WO-DOC-OBJ02-C2C2-ACTIVE-CHILD-CORRECTION-IMPLEMENT-001 CORR-001',
  NOW()
FROM runtime_field rf
JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
LEFT JOIN field_candidate fc ON fc.id = rf.field_candidate_id
WHERE rf.status = 'CANDIDATE'
  AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
  AND rfs.status = 'CANDIDATE';

UPDATE runtime_field rf
SET
  status          = 'APPROVED_BY_HUMAN',
  required_status = CASE
    WHEN (SELECT fc.is_mandatory FROM field_candidate fc
          WHERE fc.id = rf.field_candidate_id LIMIT 1) IS TRUE
    THEN 'REQUIRED_BY_HUMAN'
    ELSE 'NOT_REQUIRED'
  END
FROM runtime_form_schema rfs
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
WHERE rf.form_schema_id = rfs.id
  AND rf.status = 'CANDIDATE'
  AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
  AND rfs.status = 'CANDIDATE';

-- ── 2. Checklist correction: APPROVED_BY_HUMAN → REJECTED_BY_HUMAN ───────────
-- Mechanical field clones (item_order = field_order, raw_text = field_label)

INSERT INTO document_schema_audit (
  target_table, target_id, action, changed_by, previous_state, new_state, reason, created_at
)
SELECT
  'runtime_checklist_item',
  rc.id,
  'C2C2_ACTIVE_CHILD_CORRECTION',
  'migration:20261007131755',
  jsonb_build_object('status', rc.status),
  jsonb_build_object('status', 'REJECTED_BY_HUMAN'),
  'WO-DOC-OBJ02-C2C2-ACTIVE-CHILD-CORRECTION-IMPLEMENT-001 CORR-001',
  NOW()
FROM runtime_checklist_item rc
JOIN runtime_form_schema rfs ON rfs.id = rc.form_schema_id
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
WHERE rc.status = 'APPROVED_BY_HUMAN'
  AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
  AND rfs.status = 'CANDIDATE';

UPDATE runtime_checklist_item rc
SET status = 'REJECTED_BY_HUMAN'
FROM runtime_form_schema rfs
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
WHERE rc.form_schema_id = rfs.id
  AND rc.status = 'APPROVED_BY_HUMAN'
  AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
  AND rfs.status = 'CANDIDATE';

-- ── 3. Evidence correction: CANDIDATE → REJECTED_BY_HUMAN ────────────────────
-- timestamp_auto / signature evidence rejected in favour of native runtime handling

INSERT INTO document_schema_audit (
  target_table, target_id, action, changed_by, previous_state, new_state, reason, created_at
)
SELECT
  'runtime_evidence_field',
  re.id,
  'C2C2_ACTIVE_CHILD_CORRECTION',
  'migration:20261007131755',
  jsonb_build_object('status', re.status),
  jsonb_build_object('status', 'REJECTED_BY_HUMAN'),
  'WO-DOC-OBJ02-C2C2-ACTIVE-CHILD-CORRECTION-IMPLEMENT-001 CORR-001',
  NOW()
FROM runtime_evidence_field re
JOIN runtime_form_schema rfs ON rfs.id = re.form_schema_id
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
WHERE re.status = 'CANDIDATE'
  AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
  AND rfs.status = 'CANDIDATE';

UPDATE runtime_evidence_field re
SET status = 'REJECTED_BY_HUMAN'
FROM runtime_form_schema rfs
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
WHERE re.form_schema_id = rfs.id
  AND re.status = 'CANDIDATE'
  AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
  AND rfs.status = 'CANDIDATE';

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
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rf.status = 'APPROVED_BY_HUMAN'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_field_approved <> 96 THEN
    RAISE EXCEPTION 'post-condition failed: expected 96 APPROVED_BY_HUMAN fields, found %', v_field_approved;
  END IF;

  SELECT COUNT(*) INTO v_cl_rejected
  FROM runtime_checklist_item rc
  JOIN runtime_form_schema rfs ON rfs.id = rc.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rc.status = 'REJECTED_BY_HUMAN'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_cl_rejected <> 96 THEN
    RAISE EXCEPTION 'post-condition failed: expected 96 REJECTED_BY_HUMAN checklists, found %', v_cl_rejected;
  END IF;

  SELECT COUNT(*) INTO v_ev_rejected
  FROM runtime_evidence_field re
  JOIN runtime_form_schema rfs ON rfs.id = re.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE re.status = 'REJECTED_BY_HUMAN'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_ev_rejected <> 12 THEN
    RAISE EXCEPTION 'post-condition failed: expected 12 REJECTED_BY_HUMAN evidence, found %', v_ev_rejected;
  END IF;
END $$;
