# OBJ-REF-01 — DB checkpoint 25 / collection frozen
Date: 2026-10-08
Scope authorized by Owner: instead of Git-only checkpoint notes, create separate SQL research table and persist the previously collected 189 investigation rows. NO new sources or new form discovery.

## Target and operation evidence
Supabase project ID vwlahtguyggrhvslabax (TAI core).
Created public.ref_form_research_items by migration create_ref_form_research_items_20261008.
Exactly 189 preserved source rows from docs/reference-forms/OBJ-REF-01-FULL-PROVENANCE-LEDGER-24.md.
Loaded using 5 SQL insert batches: 40 / 40 / 40 / 40 / 29, on conflict(research_id) do nothing.
Verification SELECT: total=189, unique_ids=189, source_reports=8, review_status=PENDING count=189, source_fields_status=FIELDS_UNVERIFIED count=189.
RLS ENABLED, no access SELECT granted to anon or authenticated. Both has_table_privilege returns false. No public SELECT/UPDATE policies created. The service_role/server-admin privileged path remains separate; never place keys in frontend.
Security advisor runs project-wide and includes 'rls_enabled_no_policy' INFO findings across many pre-existing tables. For this table, policy-free + revoked privileges is intentional private-internal posture, not a justification to grant public access. Do not change other tables due to advisor output.

## Schema summary
Primary research_id text; source_report, source_title, source_evidence, source_fields_status, reuse_rights_status, legal_review_status; workflow_family, work_trigger, canonical_candidate_id, disposition, review_status, reviewer_notes, jsonb payload, timestamps.
Disposition enum check: UNREVIEWED, INDEPENDENT_CANDIDATE, OFFICIAL_ORIGINAL, TECHNICAL_REFERENCE, EXCLUDE, NEEDS_REVIEW.
Review status: PENDING, IN_PROGRESS, REVIEWED, BLOCKED.
All originally gathered source notes retained in payload. No source-rights approvals or original file field verification implied.

## Checkpoint and resume model
- QA batch A = 001-040, B = 041-080, C = 081-120, D = 121-160, E = 161-189 by frozen provenance ledger order. Do not assign numeric index based on lexicographical research_id alone; use frozen source ledger.
- Before each batch: SELECT existing rows, preserve source provenance; write only designated work-trigger/field-family/decision/status when independently supported. Persist checkpoint after each 40 or fewer records.
- After each batch: read-back count, dispositions, status, review notes and list blockers. Never silently mark REVIEWED without per-row evidence.
- No existing TAI DB comparison or AUTO form copying. No production service changes; this newly created table is an isolated study workspace in the same Supabase project.
- This data table does NOT authorize creating the final 8-table CMS. REF-02+ remains gated. No merge/deploy.

## Current Object state
REF-01 NEW COLLECTION = FROZEN.
REF-01 CORPUS_DB_LOADED=YES, review=IN_PROGRESS.
189/189 saved and PENDING; QA-A actual classification not yet written.
REF-02 classification=BLOCKED until corpus QA and approval.
