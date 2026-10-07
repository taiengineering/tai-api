-- WO-DOC-OBJ02-C2C2: Active Child Contract Correction CORR-002
-- Field: CANDIDATE → APPROVED_BY_HUMAN (required_status from field_candidate.is_mandatory)
-- Checklist: APPROVED_BY_HUMAN → REJECTED_BY_HUMAN (mechanical field clones exact=96)
-- Evidence: CANDIDATE → REJECTED_BY_HUMAN (FK chain + semantic pair exact=12)
-- P0 scope: 24 schemas via document_type_mapping.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
--           AND runtime_form_schema.status = 'CANDIDATE'

-- ── [PRE-1] Target schema exact guard ────────────────────────────────────────

DO $$
DECLARE
  v_pre_schema_count     INT;
  v_pre_schema_candidate INT;
BEGIN
  SELECT COUNT(DISTINCT rfs.id) INTO v_pre_schema_count
  FROM runtime_form_schema rfs
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_pre_schema_count <> 24 THEN
    RAISE EXCEPTION 'PRE-1 failed: expected 24 distinct target schemas, found %', v_pre_schema_count;
  END IF;

  SELECT COUNT(*) INTO v_pre_schema_candidate
  FROM runtime_form_schema rfs
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rfs.status = 'CANDIDATE'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE');

  IF v_pre_schema_candidate <> 24 THEN
    RAISE EXCEPTION 'PRE-1 failed: expected 24 CANDIDATE schemas, found %', v_pre_schema_candidate;
  END IF;
END $$;

-- ── [PRE-2] Field exact + FK + mandatory guard ────────────────────────────────

DO $$
DECLARE
  v_pre_field_total    INT;
  v_pre_fk_matched     INT;
  v_pre_mandatory_true  INT;
  v_pre_mandatory_false INT;
  v_pre_mandatory_null  INT;
BEGIN
  SELECT COUNT(*) INTO v_pre_field_total
  FROM runtime_field rf
  JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rf.status = 'CANDIDATE'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_pre_field_total <> 96 THEN
    RAISE EXCEPTION 'PRE-2 failed: expected 96 CANDIDATE fields, found %', v_pre_field_total;
  END IF;

  SELECT COUNT(*) INTO v_pre_fk_matched
  FROM runtime_field rf
  JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  JOIN field_candidate fc ON fc.id = rf.field_candidate_id
  WHERE rf.status = 'CANDIDATE'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_pre_fk_matched <> 96 THEN
    RAISE EXCEPTION 'PRE-2 failed: field_candidate FK matched % (expected 96) — NULL field_candidate_id detected', v_pre_fk_matched;
  END IF;

  SELECT COUNT(*) INTO v_pre_mandatory_true
  FROM runtime_field rf
  JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  JOIN field_candidate fc ON fc.id = rf.field_candidate_id
  WHERE rf.status = 'CANDIDATE'
    AND fc.is_mandatory IS TRUE
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_pre_mandatory_true <> 38 THEN
    RAISE EXCEPTION 'PRE-2 failed: expected 38 mandatory=true fields, found %', v_pre_mandatory_true;
  END IF;

  SELECT COUNT(*) INTO v_pre_mandatory_false
  FROM runtime_field rf
  JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  JOIN field_candidate fc ON fc.id = rf.field_candidate_id
  WHERE rf.status = 'CANDIDATE'
    AND fc.is_mandatory IS FALSE
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_pre_mandatory_false <> 58 THEN
    RAISE EXCEPTION 'PRE-2 failed: expected 58 mandatory=false fields, found %', v_pre_mandatory_false;
  END IF;

  SELECT COUNT(*) INTO v_pre_mandatory_null
  FROM runtime_field rf
  JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  JOIN field_candidate fc ON fc.id = rf.field_candidate_id
  WHERE rf.status = 'CANDIDATE'
    AND fc.is_mandatory IS NULL
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_pre_mandatory_null <> 0 THEN
    RAISE EXCEPTION 'PRE-2 failed: expected 0 mandatory=null fields, found %', v_pre_mandatory_null;
  END IF;
END $$;

-- ── [PRE-3] Checklist exact duplicate guard ───────────────────────────────────

DO $$
DECLARE
  v_pre_cl_total INT;
  v_pre_cl_clone INT;
BEGIN
  SELECT COUNT(*) INTO v_pre_cl_total
  FROM runtime_checklist_item rc
  JOIN runtime_form_schema rfs ON rfs.id = rc.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rc.status = 'APPROVED_BY_HUMAN'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_pre_cl_total <> 96 THEN
    RAISE EXCEPTION 'PRE-3 failed: expected 96 APPROVED_BY_HUMAN checklists, found %', v_pre_cl_total;
  END IF;

  SELECT COUNT(*) INTO v_pre_cl_clone
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

  IF v_pre_cl_clone <> 96 THEN
    RAISE EXCEPTION 'PRE-3 failed: exact mechanical clones = % (expected total=96 exact=96)', v_pre_cl_clone;
  END IF;
END $$;

-- ── [PRE-4] Evidence FK chain + semantic exact pair guard ─────────────────────

DO $$
DECLARE
  v_pre_ev_total      INT;
  v_pre_ev_fk         INT;
  v_pre_ev_semantic   INT;
  v_pre_ev_unexpected INT;
BEGIN
  SELECT COUNT(*) INTO v_pre_ev_total
  FROM runtime_evidence_field re
  JOIN runtime_form_schema rfs ON rfs.id = re.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE re.status = 'CANDIDATE'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_pre_ev_total <> 12 THEN
    RAISE EXCEPTION 'PRE-4 failed: expected 12 CANDIDATE evidence fields, found %', v_pre_ev_total;
  END IF;

  SELECT COUNT(DISTINCT re.id) INTO v_pre_ev_fk
  FROM runtime_evidence_field re
  JOIN runtime_form_schema rfs ON rfs.id = re.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  JOIN evidence_field_candidate efc ON efc.id = re.evidence_candidate_id
  JOIN runtime_field rf
    ON  rf.field_candidate_id = efc.field_candidate_id
    AND rf.form_schema_id     = rfs.id
  WHERE re.status = 'CANDIDATE'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_pre_ev_fk <> 12 THEN
    RAISE EXCEPTION 'PRE-4 failed: evidence FK chain matched % (expected 12)', v_pre_ev_fk;
  END IF;

  SELECT COUNT(DISTINCT re.id) INTO v_pre_ev_semantic
  FROM runtime_evidence_field re
  JOIN runtime_form_schema rfs ON rfs.id = re.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  JOIN evidence_field_candidate efc ON efc.id = re.evidence_candidate_id
  JOIN runtime_field rf
    ON  rf.field_candidate_id = efc.field_candidate_id
    AND rf.form_schema_id     = rfs.id
  WHERE re.status = 'CANDIDATE'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE'
    AND (
      (re.upload_type = 'timestamp_auto' AND rf.input_type = 'date')
      OR (re.upload_type = 'signature'   AND rf.input_type = 'signature')
    );

  IF v_pre_ev_semantic <> 12 THEN
    RAISE EXCEPTION 'PRE-4 failed: evidence semantic exact pairs = % (expected 12)', v_pre_ev_semantic;
  END IF;

  SELECT COUNT(*) INTO v_pre_ev_unexpected
  FROM runtime_evidence_field re
  JOIN runtime_form_schema rfs ON rfs.id = re.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE re.status = 'CANDIDATE'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE'
    AND re.upload_type NOT IN ('timestamp_auto', 'signature');

  IF v_pre_ev_unexpected <> 0 THEN
    RAISE EXCEPTION 'PRE-4 failed: unexpected evidence types found = %', v_pre_ev_unexpected;
  END IF;
END $$;

-- ── [PRE-5] Audit idempotency guard ──────────────────────────────────────────

DO $$
DECLARE
  v_pre_audit_existing INT;
BEGIN
  SELECT COUNT(*) INTO v_pre_audit_existing
  FROM document_schema_audit
  WHERE action     = 'C2C2_ACTIVE_CHILD_CORRECTION'
    AND changed_by = 'migration:20261007131755';

  IF v_pre_audit_existing <> 0 THEN
    RAISE EXCEPTION 'PRE-5 failed: idempotency guard — this correction has already been applied (audit count = %)', v_pre_audit_existing;
  END IF;
END $$;

-- ── 1. Field correction: CANDIDATE → APPROVED_BY_HUMAN ───────────────────────
-- required_status from field_candidate.is_mandatory (INNER JOIN; NULL FK already rejected in PRE-2)

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
    'required_status', CASE WHEN fc.is_mandatory THEN 'REQUIRED_BY_HUMAN' ELSE 'NOT_REQUIRED' END
  ),
  'WO-DOC-OBJ02-C2C2-ACTIVE-CHILD-CORRECTION-IMPLEMENT-001 CORR-002',
  NOW()
FROM runtime_field rf
JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
JOIN field_candidate fc ON fc.id = rf.field_candidate_id
WHERE rf.status = 'CANDIDATE'
  AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
  AND rfs.status = 'CANDIDATE';

UPDATE runtime_field rf
SET
  status          = 'APPROVED_BY_HUMAN',
  required_status = CASE WHEN fc.is_mandatory THEN 'REQUIRED_BY_HUMAN' ELSE 'NOT_REQUIRED' END
FROM runtime_form_schema rfs
JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
JOIN field_candidate fc ON fc.id = rf.field_candidate_id
WHERE rf.form_schema_id = rfs.id
  AND rf.status = 'CANDIDATE'
  AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
  AND rfs.status = 'CANDIDATE';

-- ── 2. Checklist correction: APPROVED_BY_HUMAN → REJECTED_BY_HUMAN ───────────

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
  'WO-DOC-OBJ02-C2C2-ACTIVE-CHILD-CORRECTION-IMPLEMENT-001 CORR-002',
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
  'WO-DOC-OBJ02-C2C2-ACTIVE-CHILD-CORRECTION-IMPLEMENT-001 CORR-002',
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

-- ── [POST-1] Schema unchanged guard ──────────────────────────────────────────

DO $$
DECLARE
  v_post_schema_candidate INT;
BEGIN
  SELECT COUNT(*) INTO v_post_schema_candidate
  FROM runtime_form_schema rfs
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rfs.status = 'CANDIDATE'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE');

  IF v_post_schema_candidate <> 24 THEN
    RAISE EXCEPTION 'POST-1 failed: expected 24 CANDIDATE schemas unchanged, found %', v_post_schema_candidate;
  END IF;
END $$;

-- ── [POST-2] Field exact guard ────────────────────────────────────────────────

DO $$
DECLARE
  v_post_field_approved INT;
  v_post_required       INT;
  v_post_not_required   INT;
  v_post_candidate_only INT;
BEGIN
  SELECT COUNT(*) INTO v_post_field_approved
  FROM runtime_field rf
  JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rf.status = 'APPROVED_BY_HUMAN'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_post_field_approved <> 96 THEN
    RAISE EXCEPTION 'POST-2 failed: expected 96 APPROVED_BY_HUMAN fields, found %', v_post_field_approved;
  END IF;

  SELECT COUNT(*) INTO v_post_required
  FROM runtime_field rf
  JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rf.required_status = 'REQUIRED_BY_HUMAN'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_post_required <> 38 THEN
    RAISE EXCEPTION 'POST-2 failed: expected 38 REQUIRED_BY_HUMAN fields, found %', v_post_required;
  END IF;

  SELECT COUNT(*) INTO v_post_not_required
  FROM runtime_field rf
  JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rf.required_status = 'NOT_REQUIRED'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_post_not_required <> 58 THEN
    RAISE EXCEPTION 'POST-2 failed: expected 58 NOT_REQUIRED fields, found %', v_post_not_required;
  END IF;

  SELECT COUNT(*) INTO v_post_candidate_only
  FROM runtime_field rf
  JOIN runtime_form_schema rfs ON rfs.id = rf.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rf.required_status = 'CANDIDATE_ONLY'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_post_candidate_only <> 0 THEN
    RAISE EXCEPTION 'POST-2 failed: expected 0 CANDIDATE_ONLY fields, found %', v_post_candidate_only;
  END IF;
END $$;

-- ── [POST-3] Checklist exact guard ────────────────────────────────────────────

DO $$
DECLARE
  v_post_cl_rejected INT;
  v_post_cl_approved INT;
BEGIN
  SELECT COUNT(*) INTO v_post_cl_rejected
  FROM runtime_checklist_item rc
  JOIN runtime_form_schema rfs ON rfs.id = rc.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rc.status = 'REJECTED_BY_HUMAN'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_post_cl_rejected <> 96 THEN
    RAISE EXCEPTION 'POST-3 failed: expected 96 REJECTED_BY_HUMAN checklists, found %', v_post_cl_rejected;
  END IF;

  SELECT COUNT(*) INTO v_post_cl_approved
  FROM runtime_checklist_item rc
  JOIN runtime_form_schema rfs ON rfs.id = rc.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE rc.status = 'APPROVED_BY_HUMAN'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_post_cl_approved <> 0 THEN
    RAISE EXCEPTION 'POST-3 failed: expected 0 APPROVED_BY_HUMAN checklists, found %', v_post_cl_approved;
  END IF;
END $$;

-- ── [POST-4] Evidence exact guard ─────────────────────────────────────────────

DO $$
DECLARE
  v_post_ev_rejected INT;
  v_post_ev_candidate INT;
BEGIN
  SELECT COUNT(*) INTO v_post_ev_rejected
  FROM runtime_evidence_field re
  JOIN runtime_form_schema rfs ON rfs.id = re.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE re.status = 'REJECTED_BY_HUMAN'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_post_ev_rejected <> 12 THEN
    RAISE EXCEPTION 'POST-4 failed: expected 12 REJECTED_BY_HUMAN evidence, found %', v_post_ev_rejected;
  END IF;

  SELECT COUNT(*) INTO v_post_ev_candidate
  FROM runtime_evidence_field re
  JOIN runtime_form_schema rfs ON rfs.id = re.form_schema_id
  JOIN document_schema_candidate dsc ON dsc.id = rfs.schema_candidate_id
  JOIN document_type_mapping dtm ON dtm.doc_id = dsc.doc_id
  WHERE re.status = 'CANDIDATE'
    AND dtm.doc_type IN ('EQUIP','INSP','CHK','TBM','PPE')
    AND rfs.status = 'CANDIDATE';

  IF v_post_ev_candidate <> 0 THEN
    RAISE EXCEPTION 'POST-4 failed: expected 0 CANDIDATE evidence, found %', v_post_ev_candidate;
  END IF;
END $$;

-- ── [POST-5] Audit exact guard ────────────────────────────────────────────────

DO $$
DECLARE
  v_post_audit_total INT;
  v_post_audit_field INT;
  v_post_audit_cl    INT;
  v_post_audit_ev    INT;
BEGIN
  SELECT COUNT(*) INTO v_post_audit_total
  FROM document_schema_audit
  WHERE action     = 'C2C2_ACTIVE_CHILD_CORRECTION'
    AND changed_by = 'migration:20261007131755';

  IF v_post_audit_total <> 204 THEN
    RAISE EXCEPTION 'POST-5 failed: expected 204 audit records, found %', v_post_audit_total;
  END IF;

  SELECT COUNT(*) INTO v_post_audit_field
  FROM document_schema_audit
  WHERE action      = 'C2C2_ACTIVE_CHILD_CORRECTION'
    AND changed_by  = 'migration:20261007131755'
    AND target_table = 'runtime_field';

  IF v_post_audit_field <> 96 THEN
    RAISE EXCEPTION 'POST-5 failed: expected 96 audit records for runtime_field, found %', v_post_audit_field;
  END IF;

  SELECT COUNT(*) INTO v_post_audit_cl
  FROM document_schema_audit
  WHERE action      = 'C2C2_ACTIVE_CHILD_CORRECTION'
    AND changed_by  = 'migration:20261007131755'
    AND target_table = 'runtime_checklist_item';

  IF v_post_audit_cl <> 96 THEN
    RAISE EXCEPTION 'POST-5 failed: expected 96 audit records for runtime_checklist_item, found %', v_post_audit_cl;
  END IF;

  SELECT COUNT(*) INTO v_post_audit_ev
  FROM document_schema_audit
  WHERE action      = 'C2C2_ACTIVE_CHILD_CORRECTION'
    AND changed_by  = 'migration:20261007131755'
    AND target_table = 'runtime_evidence_field';

  IF v_post_audit_ev <> 12 THEN
    RAISE EXCEPTION 'POST-5 failed: expected 12 audit records for runtime_evidence_field, found %', v_post_audit_ev;
  END IF;
END $$;
