# WO-057B — Google Docs title/approval compatibility investigation and narrow correction
Date: 2026-10-09
Goal: G-muzta7bb-b4a5ab
Status: PROPOSED PATCH; NO RELEASE APPROVAL
Repo: taiengineering/tai-api
Branch: docs/tai-reference-forms-charter-obj-20261008
Anchor for baseline DOCX generator: feffc11ebd1dd55bee3781416db871df80c022ed
Related evidence: WO-057A Google Docs imported QA file 1LXqKptco8oQHBU9LHx1SCSh_QJ4s2FF7Wn8IaETSh-k; original Drive DOCX 1CxD5Flr6uenWa4l9lu-W92xas958-tgw

## GPT analysis and reproducible issue
The original gen_c002_docx.cjs creates two consecutive DOCX tables: buildTitle() is a 170mm single-cell table, and buildApproval() is a separate 170mm two-cell table with a 90mm three-column nested approval table. The Google Docs imported document exposes a merged 2-row x 2-column outer table, first row containing the title in the first column, then second row containing the approval in a nested table. As a result title does not retain full-width 170mm geometry on conversion. This is a conversion-compatibility issue, not evidence of a Word/Hangul defect. Do not redesign the entire document or infer full layout parity from OOXML alone.

## Claude Code authorized execution
Phase 1 read-only:
1. Reconfirm current branch HEAD and clean tree. Preserve original PDF and DOCX file hashes.
2. Inspect OOXML of baseline blank.docx: actual tbl grid, table boundaries and intervening paragraphs; check whether two adjacent tables are interpreted/merged.
3. Inspect the Google Docs converted document layout evidence and verify 170mm title width mismatch. Report exact cause supported by source evidence, not speculation.
Phase 2 narrow POC:
4. Develop a minimal DOCX generator change in an isolated working branch/draft only. Candidate A: insert an explicit separating paragraph between title and approval, with controlled minimal spacing. Candidate B: replace the nested approval with one independent 90mm right-aligned 3-column approval table, so Google Docs has no nested table. Choose using evidence of actual Google Docs import, not preference. Keep original template fields, A4/20mm margins, 170mm content width, approval fields, 20mm goal and atLeast row heights.
5. Generate candidate blank DOCX only and check DOCX/OOXML structural invariants; do not modify production or canonical PDF.
Phase 3 actual Google Docs import (only when linked access available and authorized, test copy only):
6. Import candidate DOCX into a NEW private Google Doc under QA name, not overwrite baseline. Fetch its native document structure. Prove title occupies full document/table width while approval is aligned right beneath. Export PDF and inspect raster image for clipping, title and approval geometry. Record original vs candidate images with evidence.
7. Check basic info row, F09 header, 5 data rows, goal writing area, footer; identify any new conversion regression.
8. If candidate fixes title/approval without regressions, commit only the generator, regenerated DOCX copies, and QA evidence to active development branch after normal PRJ guards. Otherwise stop and report BLOCKED with evidence.

## Acceptance
- Imported Google Docs title spans 170mm relative to A4 20mm page margins, centered.
- Approval is 90mm right-aligned below title, 3 labels and 3 signing spaces.
- No title/approval merge or layout collision on Google Docs exported PDF.
- A4 margins, field identity/ordering, goal 20mm, min data row 14mm, footer intact.
- Native Word/Hangul still UNVERIFIED; Google Docs is an optional compatibility target, not pixel-identical layout requirement.
- DOCX and PDF need semantic + usability parity; exact pixel parity is not demanded.
- Original baseline unaffected; keep Google Docs QA documents private.

## Limitations
Do not create new form families, edit 189 research rows, DB, deploy, merge PR, install software, or claim completion without evidence.
GPT independently reviews the patch and Owner signs off form quality.
