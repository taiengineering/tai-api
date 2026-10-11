# WO-REF01-DOCUMENT-TYPE-CLASSIFICATION-051
Date: 2026-10-08
Status: READY FOR CLAUDE CODE EVIDENCE COLLECTION — NOT EXECUTED

## 0. Authority
- GPT: analysis, design, work instructions, independent semantic verification and approval of classification.
- Claude Code: investigation, read-only inventory, evidence extraction and report generation. Claude MUST NOT independently decide ambiguous semantic classifications as facts.
- Owner: ultimate approval of canonical-form and publication decisions.
- PRJ: development governance. LEG: sole legal source of truth.
- Research SoT: Supabase project `vwlahtguyggrhvslabax`, `public.ref_form_research_items` (189 frozen research records).
- Repo: `taiengineering/tai-api`; branch `docs/tai-reference-forms-charter-obj-20261008`.

## 1. Baseline and scope
Read 046 three-level identity contract and evidence 047/048/049/050 before beginning.
WO-050 = CLOSED FINAL (source visual/identity evidence accepted).
Expected baseline: 189 research rows; 14 rows with nonempty observed_fields; REF-C006 and REF-C010 observed_fields remain empty and HOLD.
Classify all **189 research records** by document function, NOT declare 189 unique forms or new canonical candidates.
Do not alter original document or study titles. No source discovery outside frozen inventory, no TAI AUTO or legacy DB comparison, no service build/merge/deploy.
Original HWP/HWPX evidence and reference PDFs are eligible only as already-existing evidence.

## 2. Taxonomy — primary exactly one, supplementary zero or more
- FORM: ordinary data-entry/application/permit form.
- CHECKLIST: item-by-item yes/no/status inspection or checking.
- WORKFLOW_DIAGRAM: process or decision flow diagram, without implying editable fields.
- REGISTER: durable inventory/register/history ledger of multiple entries.
- PLAN: forward-looking work/safety/remedial action plan.
- REPORT: accident/investigation/result report.
- EVALUATION: structured scoring/risk or qualification assessment.
- RECORD: minutes, attendance, training or work-execution log.
- REFERENCE: instruction, sample, explanation, guidance, example lacking distinct fillable form purpose.
- UNDETERMINED: insufficient evidence to identify document function.
These categories are functional; a form may contain an evaluation table, but choose the principal business output. Separate *document type* from *source status* (example/blank/guide), *artifact format* (HWP/PDF/HTML), and *workflow family*. Do not classify everything labeled 서식 as FORM.

## 3. Evidence confidence
For each ID, record:
- research_id, source_title, original artifact_type/workflow_family, research report/provenance;
- verified original document section IDs and checksum when available;
- proposed primary_type, secondary_types[];
- confidence: SOURCE_STRUCTURE_VERIFIED (native tables/diagram), SOURCE_TEXT_PARTIAL (paragraph-only), RESEARCH_REPORT_ONLY (secondary research), TITLE_ONLY (no source structure), or INSUFFICIENT;
- evidence_locator; reasoning anchored to function; ambiguity; needs_GPT_review bool;
- legal_gate: always UNVERIFIED unless independently checked by LEG in a future WO;
- rights_gate: unchanged; identity_decision unchanged.
If evidence confidence is TITLE_ONLY or weaker, mark classification as PROVISIONAL. If primary function cannot responsibly be inferred, UNDETERMINED; don't fabricate fields or workflows.
For compound source sections record section-level category independently and DO NOT force research row to inherit all sub-section types.
Especially:
REF-C010: HWP-10a WORKFLOW_DIAGRAM; HWP-10b and 10c TABLE_TEMPLATE source sections (not automatically new research IDs). TABLE_TEMPLATE is a **source structural shape**, not automatically the research-level primary-type enum. REF-C010 research-level type may be WORKFLOW_DIAGRAM PROVISIONAL, but record split/ambiguity and GPT review.
REF-C006: risk frequency×severity METHOD_COMPATIBLE but not IDENTICAL_VERIFIED; provisional EVALUATION allowed as activity category, never claim same source form.
REF-C008: source_title typo retains exact original; evaluator type assessed by source function without modifying source_title.
REF-C011: existing record matched; no duplicate ID.
HWPX hazard investigation checklists must not be conflated with final risk-assessment results.

## 4. Steps
S0 — READ-ONLY PREFLIGHT: verify Git baseline, SoT project/table and counts, no pending concurrent mutation. Capture query and results. If count !=189 or current fields !=14, STOP/FLAG; do not revert outside changes.
S1 — INVENTORY: read all 189 records with research_id, source_title, artifact_type, workflow_family, work_trigger, disposition, relation_group, relevant source/provenance and observed_fields count. Ensure 189 unique IDs, no duplicates, and record missing metadata.
S2 — CLASSIFICATION PROPOSALS: apply taxonomy above to each record using strongest available evidence. Create complete machine-readable 189-row proposal (CSV or JSON in docs/reference-forms/evidence; do NOT include protected source bytes or copyrighted long prose). List by ID with confidence and evidence trace. When original format/section known, distinguish file container from actual inside section and research record.
S3 — QUALITY GATES: primary_type exactly one from enum for each row; secondary types from same enum except UNDETERMINED; no repeated types; no unsupported SOURCE_STRUCTURE_VERIFIED claim; evidence trace for every non-UNDETERMINED primary; count totals sum to 189; identify ambiguous ID groups, duplicate-workflow candidates without merging, and SOURCE_VERIFIED vs HYPOTHESIS totals. Independently check REF-C006/C008/C010/C011.
S4 — GPT REVIEW: write `docs/reference-forms/evidence/REF01-DOCUMENT-TYPE-CLASSIFICATION-PROPOSAL-051.md` containing methodology, ten-category totals, evidence levels, exceptions, sample validation, known unresolved, and pointer to complete 189-row proposal. Return all evidence. STOP before any Supabase write or canonical ID assignment.
S5 — RETURN: repo/branch/commit; inventory count; classification counts; complete proposal link; exact 189-row coverage; source-linked cases; ambiguity count; DB mutations=0; FINAL=EVIDENCE_READY_FOR_GPT_REVIEW/PARTIAL/BLOCKED.

## 5. Forbidden operations
No insert/update/delete on Supabase, migrations or RLS changes, no source_title normalization, no changes to observed_fields, no LEG or rights determinations, no publication/approval, no new research row/source collection, no canonical merging or unique-form counts, no implementation, no deploy, no PR merge. Never claim Owner approval or GPT PASS before actual verification.

## 6. Acceptance
This WO succeeds at evidence-collection stage only if it produces a full 189-ID traceable classification **proposal** with strict uncertainty labels and preserves original data. GPT independently reviews before any later authorized persistence.
