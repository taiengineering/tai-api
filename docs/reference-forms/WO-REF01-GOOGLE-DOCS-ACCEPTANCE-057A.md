# WO-057A — Google Docs editor QA alternate path
Date: 2026-10-09
Status: QA INSTRUCTIONS READY; GUI TEST NOT RUN
Goal: G-muzta7bb-b4a5ab
Base: WO-REF01-DOCX-GUI-ACCEPTANCE-057.md
Anchor: feffc11ebd1dd55bee3781416db871df80c022ed (REF-C002 DOCX code)
## Decision
Owner reports no adequate local document editor. Use Google Docs as OPTIONAL browser-based initial editor QA, without installing desktop software. A Google Docs PASS does NOT mean Word or Hangul compatibility PASS.
## Access
Google Drive/Docs connection requires explicit Owner connection; until available, STOP as EXTERNAL_EDITOR_ACCESS_BLOCKED. Do not request credentials or copy/upload a document to an external account without confirmed authorization and connection. No fake testing.
## Procedure, once owner access is confirmed
1. Obtain two source DOCX files from branch: output/TAI-FORM-C002-blank.docx and output/TAI-FORM-C002-example.docx. Record source SHA-256 and origin Git SHA.
2. Copy/upload only testing artifacts into Owner-authorized Google Drive location. Do not modify source files, production DB, services, Git main or PR.
3. Open DOCX in Google Docs editor and capture screenshot of initial layout.
4. Enter 사업장명, 작성일, 문서번호, 적용 연도. Enter 3–5 lines for 전사 목표. Check clipping.
5. Edit and insert rows to 10 and 18; stress-test long Korean text, budget numerics, table header repetition and page numbers on actual page breaks.
6. Save/close/reopen copy. Export PDF, inspect each page for clipping, fonts, approval blocks and table headers. Record application and export method (native DOCX edit vs converted Google Docs); avoid confusing Google Docs native format with Word DOCX.
7. Verify metadata as supported, and no logo, QR or promo content; never claim legal mandatory status.
8. Report per T01–T13 of WO-057: PASS/FAIL/UNVERIFIED with exact screenshot/export evidence and document hashes.
9. Mark WORD_GUI_QA=UNVERIFIED and HANGUL_GUI_QA=UNVERIFIED unless those exact editors are actually tested.
## Current gates
PDF_POC=PASS; DOCX_STRUCTURE=PASS; GOOGLE_DOCS_GUI=NOT_RUN; WORD_GUI=UNVERIFIED; HANGUL_GUI=UNVERIFIED; OWNER_FINAL_APPROVAL=PENDING.
## Prohibitions
No production deployment, DB changes, PR merge, new forms, external publication, invented screenshots, or release approval. If Google Docs access unavailable, submit a short owner self-test instruction and STOP, no repeated code changes.
