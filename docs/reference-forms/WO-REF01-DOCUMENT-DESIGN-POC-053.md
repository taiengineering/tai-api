# WO-REF01-DOCUMENT-DESIGN-POC-053
Date: 2026-10-08
Status: OWNER DIRECTION RECEIVED / DESIGN & NON-PRODUCTION POC ONLY
Branch: docs/tai-reference-forms-charter-obj-20261008
PR: #564 (open, no merge authorization)

## 0. Purpose and priority
Build genuinely useful, editable and print-ready TAI-owned industrial-safety documents, with a consistent professional visual language. The current work is document authoring and quality control, NOT search/SEO implementation, signup/download flow implementation, or integration matrix development. Existing future policy: searchable DB-fed SEO pages with public preview and signup at download; retain as downstream decision only. Do NOT build web features in this WO.

## 1. Strict authority & scope
- GPT: design, WO, independent verification; Claude Code: inspect, execute, evidence; Owner: acceptance and authorization.
- LEG is sole legal SoT; PRJ is development governance.
- 189 existing research rows are NOT 189 completed/unique forms. Preserve all existing rows and recorded source classifications (WO-046 through WO-052).
- Do not use/copy legacy TAI AUTO templates or datasets.
- Do not infer mandatory law fields from source titles; each field classified VERIFIED_SOURCE, TAI_PRACTICAL_PROPOSAL or LEG_REVIEW_REQUIRED. All claims of legal necessity require explicit LEG review.
- No source redistribution or faithful reconstruction of public/third-party original form until usage rights verified; make original TAI layouts and wording, using verified facts as design input.
- NO production writes, migrations, deployment, PR merge, public publishing or user-facing launch in this WO. Local/staging-independent artifacts only. PR #564 is open.
- Owner chose: no externally visible TAI logos, QR, promotional footer, or marketing text in document. File-level metadata only (where supported): title, creator/producer, stable document ID, version, canonical detail URL once assigned. No hash verification feature in scope.
- Search relationship matrix work is a separate stream, EXCLUDED.
- QA here means DOCUMENT quality review (editing and printing), not QR branding; user specifically declined external logo/QR.

## 2. Proposed POC families, preliminary — verify identity before actual authoring
1. REF-C012 안전작업허가서 — work period, permitted activities, safety conditions and approval/signature workflow.
2. REF-C013 사고조사보고서 — narrative, evidence/photo area, causes and corrective actions.
3. REF-C003 위험기계·기구·설비 목록 — repeatable inventory/table pagination.
4. REF-C002 안전보건 목표 및 추진계획서 — goal, action plan, assignment, schedule.
5. REF-C011 도급업체 안전보건 수준 평가표 — score/rubric, totals, evaluation evidence.
Research IDs are lineage references only, NOT automatically approved canonical IDs. Confirm section identity and field eligibility before drafting. If a candidate fails identity/rights/legal checks, HOLD that candidate and report, do not invent equivalents or substitute silently.

## 3. Document style system v0.1 (suggested baseline, subject to sample QA)
- A4 portrait default; landscape for wide registers only; physical print safety margins and predictable page breaks.
- Single Korean-friendly font family (legally embeddable); body 10–11pt, document title 16–18pt, section 11–12pt.
- Predominantly black/near-black and neutral gray, printer-friendly; no decorative gradients or conspicuous branding.
- Standard title, optional quiet document ID/version, section numbering, consistent table borders/cell padding and whitespace.
- Tables must repeat header on subsequent pages; no clipped long text or unusably small writing areas.
- Layout templates vary by activity: permit, report, register, plan, evaluation. Shared design primitives, not one forced table.
- Keep fill-in blanks large enough; labels explicit, instructions concise; manual handwriting and keyboard-editable usage considered.
- Header/footer identifiers minimal and functional only; no visible advertising or QR.
- Unverified source fields or suggested controls must not be presented as legal requirements.

## 4. Common content/data design before rendering
For each POC form prepare an explicit contract including:
(a) temporary form identity and research/source evidence lineage;
(b) intended users, tasks, when to use, and expected review/approval actions;
(c) sections and ordered fields with types, optionality, multiplicity, allowed length;
(d) exact verified source label vs proposed TAI user-facing label, with origin tags;
(e) evidence for source fields and separate LEG confirmation status;
(f) table row-addition, multiline/photos, calculated scores, signatures;
(g) layout rules and version metadata;
(h) format outputs and test matrix.
Retain intended future metadata fields in authoring manifests: stable id (subject to owner approval), title, edition/version, source lineage, origin/rights, creator/producer, publication URL placeholder; NEVER put a fake URL or fake checksum into a released file.

## 5. Execution phases
PHASE A READ-ONLY PREFLIGHT: inspect the current REF-01 evidence, source constraints, current branch and POC outputs/tooling; present 5-form draft identity and rights/LEGAL risk list. No editing.
PHASE B STYLE SPEC: draft shared style specification and one sample layout per selected document family; explicit editable format choice and supported fonts; do not start production build.
PHASE C NON-PROD POC: after GPT independent review of A+B, create five original draft documents and their field specifications under isolated local or review directory. If unresolved rights/LEGAL identity, HOLD affected draft. Prefer genuinely editable source (DOCX or structured HTML) and reproducible A4 PDF rendering for visual inspection; exact source format must be declared and tested. Do not claim unsupported HWPX editability.
PHASE D DOCUMENT QA: independently review content, blank completion space, table repetition/pagination, 1-page/multi-page and long Korean strings, fonts, signatures and calculations, grayscale print; attach page previews and reproducible test evidence. Do not confuse parser confidence with legal certainty.
PHASE E OWNER REVIEW: choose style and form content. Until approval all five remain NON-PRODUCTION DRAFT.

## 6. Acceptance gates
- No newly invented statutory obligations, no fabricated source equivalence or assumed redistribution rights.
- All 5 draft identities and field provenance documented; holds explicitly listed.
- Shared style components and per-type functional differences shown.
- Editable master and representative printable PDF drafts where technically feasible, together with visual QA outputs; no clipping/overlap; any failed check BLOCKS release.
- Nonvisible metadata demonstrably present in supported output properties, no logo/QR/promo visible, no invented canonical links.
- Existing 189 research rows, DB, live site, main branch and production unaffected.
- Owner may review before approval; no auto-merging, publication or deployment.

## 7. First Claude Code deliverable only
A READ-ONLY inventory and proposed field/layout matrix for the five candidates, containing exact file paths, evidence IDs, verified-vs-proposed fields, blockers, available authoring/render pipeline, and proposed QA scenarios. NO code changes, document generation, DB mutation or commits in this first execution. GPT will then issue narrower implementation authorization based on actual evidence.

## 8. Reporting
Respond with: actual branch/head, evidence source paths, five-row readiness matrix, rights/LEG ambiguity, proposed common font/print rules, editable output/tooling feasibility and hard BLOCKERS. Label anything not independently proven UNVERIFIED.
