# REF-01 three-level identity and version data contract / 046
Date: 2026-10-08. Design only; not a DB migration or implementation authorization.
LEG remains the sole legal SoT; PRJ development governance. Existing Supabase vwlahtguyggrhvslabax.public.ref_form_research_items retains all 189 original research rows as research SoT.
## Identity problem
Research row is not original physical document, nor a unique eventual TAI form. Some HWP/HWPX documents bundle multiple numbered sections, and the same activity appears in multiple source documents. A record can relate to several source sections and a section may relate to multiple research records. Do not use canonical_candidate_id prematurely.
## Three identities
1. Research item, key research_id: preserve existing 189 rows, provenance, original hypotheses and reviewer evidence; DO NOT treat count as number of deliverable forms.
2. Source asset + source section: source_asset_id stable from exact file SHA256 and source owner/edition, with bytes digest, acquisition provenance, status, license, and file type. source_section_id references source_asset_id and stable section ordinal/heading; stores page/paragraph/cell coordinates and observed exact labels, parser confidence, parsing limits. Do not duplicate the same asset per research row.
3. Canonical TAI form + variant: canonical_form_id independent unique function/workflow identity; variant_id for method, sector, lifecycle, format, official-annex edition. Every candidate remains DRAFT_IDENTITY until independently scoped and Owner approved. Version is source asset edition or TAI publication version, **not just calendar year**.

## Proposed relational model (NOT APPLIED)
ref_form_source_assets(asset_id PK, sha256 UNIQUE, publisher, title, edition_date, original_url, original_filename, mime, byte_size, access_provenance, parse_status, rights_status, license_evidence_url, added_at).
ref_form_source_sections(section_id PK, asset_id FK, section_ordinal, exact_heading, start_locator, end_locator, observed_fields JSONB array, parse_fidelity, unique(asset_id,section_ordinal)).
ref_form_research_section_links(research_id FK existing, section_id FK, relationship_type ENUM of EXACT_TITLE_MATCH/WORKFLOW_EQUIVALENT/VARIANT/RELATED_STAGE/UNDETERMINED, evidence_note, reviewer_status, UNIQUE pair).
ref_form_canonical_forms(canonical_form_id PK, canonical_title, workflow_trigger, artifact_type, actor_contract JSONB, status DRAFT/REVIEW/OWNER_APPROVED/EXCLUDED).
ref_form_canonical_variants(variant_id PK, canonical_form_id FK, sector/method/source_epoch applicability, format_contract, field_contract JSONB, legal_sot_reference, rights_route, review_status).
ref_form_canonical_lineage(variant_id FK, research_id FK nullable, section_id FK nullable, evidence_note, link_decision, UNIQUE relevant tuple).
Source content rights: never expose/redistribute private source bytes by default; secure evidence storage separate from public CMS.

## Mapping evidence already observed
2022 MOEL HWP5 asset SHA256 e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe — 10 research rows have partial native BodyText observed fields. Section/page/cell fidelity is NOT yet complete; exact linked section identities remain unapproved.
2023 risk-assessment HWPX asset SHA256 c624ea2e72c4e79b8daa011375d2105f3f917e069b47dfd95c9850b193d21d46 — 8 original numbered sections. Existing four tentative research associations:
REF-C015 ↔ near-miss discovery = SAME_WORKFLOW_DIFFERENT_SOURCE_FORM;
REF-C027 ↔ hazard checklist = RELATED_STAGE_NOT_IDENTICAL;
REF-C064 ↔ TBM meeting = POSSIBLE_VARIANT_SCOPE_DIFFERENCE;
REF-C014 ↔ risk reduction = RELATED_CONTROL_STAGE_NOT_IDENTICAL.
Remaining 4 sections: manufacturing hazard information, workplace patrol hazard survey, interview hazard survey, safety-data hazard survey: no confirmed matching research ID; do not create one or force merge.
## Validation/acceptance
- 189 research rows preserved.
- Each source asset stored once by verified checksum and has section inventory; no fictitious source section inferred from title only.
- Every mapping includes provenance and exact relationship semantics; ambiguous maps remain undecided.
- Canonical count remains UNKNOWN until form-level field, document purpose, audience and legal/rights gates resolved.
- Final implementation-ready artifact needs per-variant input field contract, format layout, process/actors, LEG checked requiredness, publication rights, and test fixtures.
- Source files remain nonpublic, and new code/database schema only after separate Owner authorization of proposed DDL and PRJ migration authority.
## Immediate next WO after approval
Claude Code gathers faithful section/cell locators for existing 2022 HWP and 2023 HWPX, along with source-asset checksum. GPT verifies link decision and contract. Do not enter a build phase before source segmentation.
