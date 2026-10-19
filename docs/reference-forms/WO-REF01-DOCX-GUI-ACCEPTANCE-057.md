# WO-REF01-DOCX-GUI-ACCEPTANCE-057
Date: 2026-10-09
Status: AUTHORIZED TO INVESTIGATE & RUN LOCAL NON-PRODUCTION QA; NO APPROVAL IMPLIED
Goal: G-muzta7bb-b4a5ab
Repo: taiengineering/tai-api
Branch: docs/tai-reference-forms-charter-obj-20261008
Anchor: feffc11ebd1dd55bee3781416db871df80c022ed

## Purpose
Verify whether REF-C002 blank/example DOCX can actually be edited, saved, reopened, paginated and printed by end users. Do not repeat XML-only checks as a substitute for GUI QA.

## Role & scope
GPT: plan, independent evidence verification, final gate recommendation.
Claude Code: local machine investigation, authorized QA execution, objective receipts.
Owner: final document-quality approval.
LEG legal SoT and PRJ governance unchanged. No source rights clearance, publication, merging or deployment.

## Preflight (READ ONLY)
1. Confirm git remote/branch/HEAD and clean working tree; verify target DOCX files exist and their hashes.
2. Check actual availability of Microsoft Word for Mac, Hancom/Hangul for Mac, and any genuine GUI or headless-render capable office suite. Do NOT install software or request new licenses.
3. Check local file open/modify/save/export permissions and whether interaction can be controlled/observed by Claude Code. Mac automation permissions are not assumed; record any blocker.
4. Record app name/version, font availability, exact input artifact SHA, date and intended test method.
5. If no real office app access exists, STOP and report GUI_UNVERIFIED; do not label ZIP/XML parsing as GUI opening, rendering or editing.

## Safe QA execution (only if a real editor is available)
Use throwaway COPIES of docs/reference-forms/output/TAI-FORM-C002-blank.docx and -example.docx. Never overwrite approved baseline artifacts.
A. Open blank DOCX, record screenshot with visible title, approval block, basic info, goal, table, footer.
B. Enter realistic Korean strings for company, date, document number/year; fill goal with 3-5 lines; edit table values.
C. Add rows to 10 and then 18, insert long Korean descriptions, and check column width, row expansion, clipping and header repetition. Preserve sample values in evidence file.
D. Save, close, reopen: assert all values and layout remain.
E. Export to PDF from the same actual editor, record page count and screenshots of all pages, especially breaks. Compare exact field list/order with canonical c002_fields.json and the existing PDF reference; page count need not be identical when user edits content.
F. Check PDF and DOCX metadata and absence of logo/QR/promo material; no legal-required claims.
G. Repeat in Hangul as available (if only Word is installed, mark HANGUL_UNVERIFIED, not PASS).
H. If software absent, manual owner QA is a separate subsequent gate; provide a precise small checklist without falsely approving.

## Test cases and acceptance matrix
T01 Open DOCX without repair warning.
T02 Enter business/date/year/number and retain on save/reopen.
T03 Goal paragraph 3-5 lines expands without truncation.
T04 5 -> 10 -> 18 rows editable and saved, all text retained.
T05 Long Korean strings and budget numerics remain visible.
T06 Table header repeats across actual page breaks.
T07 Footer PAGE/NUMPAGES shows correct counts in exported PDF.
T08 Approval/signature area remains usable.
T09 Page size A4, margins approximately 20mm, no overlap or clipping.
T10 PDF export from editor works and preserves all fields.
T11 Word version and Hangul version independently reported (PASS or UNVERIFIED).
T12 Fonts: note installed/absent NanumGothic and fallback behavior, no unauthorized font redistribution.
T13 Edited files are copies; original DOCX/PDF hashes unchanged.
For each item: PASS/FAIL/UNVERIFIED + exact artifact and evidence path. A preconfigured OOXML property is not enough for renderer-dependent tests.

## Evidence requirements
Record environment/app versions, provenance and SHA of artifacts, scripted vs human actions, screenshots, editor-generated PDF and file hashes, per-test matrix, defects and severity, report path. Screenshots must show the actual document/editor, not a mockup.
If access is unavailable, report BLOCKED/GUI_UNVERIFIED explicitly and recommend minimal owner/manual steps.

## Prohibitions
No external publication, no production DB writes/migrations, no deployment, no PR merge, no forced push, no source-rights claims, no work on other form families, no installation, no alteration to frozen 189 research rows.
Do not claim WO-054/REF-C002 CLOSED FINAL until GPT evidence verification and Owner quality approval.

## First response required
Return PREFLIGHT capability inventory and whether authentic GUI execution is possible. If yes, proceed with tests using throwaway copies and report evidence. If not, STOP and report GUI_UNVERIFIED without initiating unrelated work.
