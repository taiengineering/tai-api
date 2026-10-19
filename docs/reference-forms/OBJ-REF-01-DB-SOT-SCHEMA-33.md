# REF-01 reference forms SoT schema / checkpoint 33
Date: 2026-10-08
Owner instruction: use existing research database table as the sole source of truth for this form corpus; extend columns and persist audit progress. **Legal obligations remain authoritative in LEG, not this form table**. PRJ governance unchanged.

## SoT designation
Supabase project vwlahtguyggrhvslabax / public.ref_form_research_items.
Original 189 source records retained. This table is authoritative for form research-row identity, provenance, workflow analysis, proposed canonical intent, evidence, validation progress, rights, approval and publication readiness (NOT current law).
Original Git research reports 03–22 are frozen source evidence; Git checkpoint logs are audit receipts, not competing mutable databases.
Existing TAI AUTO business documents/DB were not compared or copied.

## Added explicit columns
- Identity / discovery: canonical_title, practitioner_role, artifact_type, suggested_formats, source_url, source_attachment_url, source_document_checksum, source_document_access, corpus_version.
- Distinguish field authority: observed_fields (actual source file verified, array), proposed_fields (TAI independent design hypotheses, array), legal_required_fields (LEG validated, array). Never copy proposed columns into observed_fields.
- Evidence and traceability: source_observation_note, legal_sot_reference, legal_checked_at, license_reference, reuse_checked_at.
- Relationships and gate: relation_group, related_research_ids, validation_blockers, reviewer_id, reviewed_at, owner_approval_status, owner_approved_at, publication_status.
- Existing original provenance, disposition, reviewer_notes, payload, review_status, timestamps retained.
- New states default owner_approval_status NOT_REQUESTED, publication_status NOT_READY. Check constraints constrain states.
- Source file access NOT_CHECKED unless explicitly verified.
- Backfilled group and related IDs from already saved relation evidence for 51 source rows, evidence description from the earlier 40 source audit rows.
- Added three conservative blockers to 189 rows: SOURCE_FIELDS_UNVERIFIED, LEGAL_REVIEW_PENDING, RIGHTS_UNVERIFIED. These are not statements of law but blockers for publication/validation.
- No new form candidates, source searches, TAI AUTO duplication, production deployment, or public-facing UI.

## Verification
- Total research rows 189.
- Relation group filled for 51 rows, source observation note filled for 40.
- 189 rows have blockers and 189 remain NOT_REQUESTED / NOT_READY, 0 REVIEWED.
- Table RLS enabled and no SELECT privilege for anon or authenticated.
- New indexes: relation_group, publication_status+owner_approval_status.
- Migration applied: extend_ref_form_research_items_sot_20261008.

## Critical remaining gates
- Existing REF-01 classification work is **not full field examination**; source attachment bytes have not been independently reviewed.
- All fields observed_fields/proposed_fields/legal_required_fields start empty; legally mandated form fields must cite LEG at field-level.
- Do not set APPROVED_FOR_PUBLICATION/PUBLISHED without all current law, reuse rights, source-field verification or independent-original creation approvals and explicit Owner authorization. Columns exist but automated transition guards still need design and approval before CMS.
- Source evidence link fields are null until exact URL for the specific form and download is verified from *already acquired sources*. No invented links.
- External service publication prohibited at this phase; REF-02 still pending after REF-01 QA gate.

## Continuation
Next: source record field audit in 25/40-row checkpoints. Write verified original observed_fields vs proposed_fields independently and update traceable source URLs from existing reports only. Then LEG and copyright reviews. All intermediate save updates directly to this SoT and optionally Git receipts.
