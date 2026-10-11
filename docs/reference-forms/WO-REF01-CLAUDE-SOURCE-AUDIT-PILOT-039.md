# WO-REF01-CLAUDE-SOURCE-AUDIT-PILOT-039
Date: 2026-10-08 | STATUS: READY_FOR_CLAUDE_EXECUTION, NOT EXECUTED
Owner instruction: GPT designs, writes WO and independently verifies; Claude Code only investigates/executes/extracts/collects evidence. Owner approves implementation.
LEG = statutory SoT; PRJ = development governance; public.ref_form_research_items = reference-form research SoT.

## Purpose
Validate previously identified original document attachments, *not* search for new candidate forms. Start an evidence-first 10-record pilot. STOP if source access, rights or traceability unavailable; NEVER invent source fields.

## Frozen scope
Supabase project vwlahtguyggrhvslabax, public.ref_form_research_items, 189 existing rows. Branch docs/tai-reference-forms-charter-obj-20261008; reference docs OBJ-REF-01-DB-SOT-SCHEMA-33.md, OBJ-REF-01-IMPLEMENTATION-READY-DEFINITION-38.md and existing source reports.
Pilot records: REF-C001 through REF-C010, official KOSHA public form names. Exact existing source URL:
https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?articleNo=453942&boardNo=141&mode=view
Original report 03: OBJ-REF-01-KOSHA-24-FORMS-SOURCE-03.md.
Check list: 001 안전보건경영방침, 002 안전보건활동 목표/세부 추진계획, 003 위험기계·기구·설비 목록 작성 서식, 004 유해·위험물질 목록 작성 서식, 005 작업별 위험과관리 대장, 006 위험성평가표(빈도강도법), 007 안전보건예산 편성 서식, 008 안전보건 전문이력 평가 기준 및 평가표, 009 안전보건 전문인력 등 배치표 및 담당업무, 010 사고 발생 대응 시나리오(처리 흐름도). Preserve official source spelling exactly, no unapproved corrections.

## Execution stages
S0 PREFLIGHT READ ONLY: identify exact repo branch HEAD, linked Supabase project/table RLS, 189 total records and current review fields; check local tooling for HWP/HWPX/ZIP/PDF inspection. Record version, source URL availability, original attachment URI and terms, before any mutation. No deploy, migrations, PR merge.
S1 SOURCE RETRIEVAL: open **only existing source URL**, identify exact attachment href, click/download permitted publicly accessible file(s) to isolated local evidence directory. If authentication/blocked/403, record access failure and stop that item; no bypass, no alternative-source discovery. Hash exact bytes SHA256; report bytes, MIME, container file names and document boundary.
S2 PARSE WITH PROVENANCE: associate a source file and specific page/table/section with each of ten titles. Extract original visible field labels and table columns, required marker and sign-off fields only where literally found; note multi-form attachments and ambiguous segmentation. Preserve exact Korean wording, never fill inferred fields. Spreadsheet formulas, sheets and print formats only if actual workbook. No OCR except when no native parsing exists and original images are readable. Distinguish page-listed name (title only) from contents verified.
S3 RIGHTS: collect source public notice/license exactly. Being free to modify for own use is NOT redistribution authorization. Record verbatim short excerpts and URL, no presumptive approval.
S4 STAGING FIRST: produce /tmp or docs/reference-forms/evidence/ pilot evidence manifest (NO copyrighted source file bytes committed). Manifest fields per ID: exact URL, attachment URL, SHA, byte count, mime, page/section, observed_fields candidate JSON with provenance per item, error code/obstacle, usage rights evidence/status, screenshot or local view references (no fabricated URLs). Provide extraction limitations.
S5 CONDITIONAL DB SAVE: only after manifests conform to S4, update existing 10 rows with exact source_url, source_attachment_url, checksum, source_document_access, observed_fields *only for genuinely observed fields*, source_observation_note; use field objects with label and source section. Protect against overwriting existing nonempty fields, maintain proposed_fields separate. Rights status remains UNVERIFIED unless license explicit, LEG fields untouched. If updates require new table/schema or broad SQL privileges, STOP and request GPT WO. Do not change owner_approval_status, publication_status or REVIEWED. Prefer transaction and exact ID match with row counts. No other tables or production app services. SQL report before/after.
S6 RECEIPT: report each of 10 IDs with ACCESSIBLE / DOWNLOAD_FAILED / FIELDS_VERIFIED / TITLE_ONLY, field count, unverified reasons, hash and source. Git receipt with commit (not original third-party attachment). Zero guesswork. No work on IDs outside pilot.

## Acceptance / stop criteria
- All 10 IDs accounted for with evidence or explicit block, no invented or auto-promoted legal fields.
- Original files saved only in local isolated investigator workspace, not published or committed.
- Evidence reproducible by exact source URL + bytes hash + section/page.
- DB identity, 189 row total unchanged; original observed_fields updated strictly by actual file verification. All legal and rights approval remain pending unless independently verified; cannot mark final approval.
- No new form research, no comparisons to TAI legacy DB, no TAI AUTO form duplication, no public source republishing.
- If official site contains a newer attachment, do not silently switch; report to GPT for scope/version decision.
- The 10 records are pilot; wait for GPT independent verification and Owner approval before next batch.

## Required return format
PREFLIGHT (branch SHA, DB count, RLS)
SOURCE MANIFEST (10 IDs + exact file/section evidence)
FIELD EXTRACTION (separately observed vs proposed)
RIGHTS/LEGAL OPEN ITEMS
DB SQL EVIDENCE (before/after, updated rows)
FAILURES WITH REPRODUCIBLE ERRORS
GIT RECEIPT (path, commit)
FINAL: PILOT_EXECUTED / PARTIAL / BLOCKED and DO_NOT_EXPAND = TRUE.

This WO is ready for manual submission to Claude Code. Writing it in Git does NOT launch Claude Code.
