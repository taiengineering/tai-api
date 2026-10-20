-- WO-WWW-SS-THUMBNAIL-001 P3-R3 — Migration Delta: Claim Ownership Columns
--
-- STATUS: DESIGN ONLY — NOT applied to production DB.
-- Requires Owner approval + separate G3-delta gate before execution.
--
-- Purpose:
--   Adds process-level claim ownership columns to reference_form_preview_artifacts.
--   Without these columns, _process_one() can only guard the final DB update with
--   thumbnail_qa_status=PENDING (prevents QA_PASS overwrite) but cannot verify that
--   the PENDING row belongs to the current process.
--
--   With thumbnail_claim_id, the final UPDATE matches claim_id as well, ensuring
--   that a revived process (crashed + recovered) cannot write QA_PASS over another
--   process's active claim.
--
-- Proposed claim protocol (post-migration):
--   Claim:  UPDATE SET thumbnail_qa_status='PENDING',
--                       thumbnail_claim_id=<uuid>,
--                       thumbnail_claimed_at=now()
--           WHERE id=<pa_id> AND thumbnail_qa_status IS NULL
--   Finalize: UPDATE SET thumbnail_qa_status='QA_PASS', ...
--           WHERE id=<pa_id> AND thumbnail_claim_id=<uuid>
--   Release: UPDATE SET thumbnail_qa_status='QA_FAIL', thumbnail_claim_id=NULL
--           WHERE id=<pa_id> AND thumbnail_claim_id=<uuid>
--
-- Staleness detection (optional):
--   A monitoring job can identify claims older than N minutes via thumbnail_claimed_at
--   and reset them without a --reset-pending operator invocation.

ALTER TABLE reference_form_preview_artifacts
  ADD COLUMN IF NOT EXISTS thumbnail_claim_id   uuid         NULL,
  ADD COLUMN IF NOT EXISTS thumbnail_claimed_at  timestamptz  NULL;

COMMENT ON COLUMN reference_form_preview_artifacts.thumbnail_claim_id IS
  'UUID generated per backfill process when it atomically claims this row. '
  'The final QA_PASS UPDATE also requires this value to match, preventing a '
  'revived or concurrent process from overwriting an active claim.';

COMMENT ON COLUMN reference_form_preview_artifacts.thumbnail_claimed_at IS
  'Timestamp when thumbnail_claim_id was set. Used for stale-claim detection.';
