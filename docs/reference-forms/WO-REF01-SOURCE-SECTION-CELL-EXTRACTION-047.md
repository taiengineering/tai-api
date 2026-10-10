# WO-REF01-SOURCE-SECTION-CELL-EXTRACTION-047
Date: 2026-10-08 | READY FOR CLAUDE CODE EXECUTION; not executed
Basis: OBJ-REF-01-THREE-LEVEL-IDENTITY-CONTRACT-046.md and evidence receipts 041–045.

## Authority and scope
GPT: analysis, specification, WO, independent verification. Claude Code: technical investigation, safe extraction, reproducible evidence, permitted existing-SoT updates. Owner: approval.
PRJ: development governance; LEG: legal SoT; Supabase vwlahtguyggrhvslabax.public.ref_form_research_items: research SoT, 189 rows.
No discovery of additional form candidates. No comparison with TAI AUTO/legacy DB. No deployment, public distribution, new DB schema, production code, merge or new research rows.

## Inputs
The **Owner-uploaded** three sources, transferred explicitly into Claude Code's local workspace by Owner (ChatGPT attachment filesystem is not presumed accessible from Claude Code):
- MOEL 2022 HWP collection, SHA256 e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe.
- MOEL guide PDF, SHA256 a73ce4c67dfcb4a1b27f647ad346496f1bc7421666653da516c9ca92a46c60ff.
- 2023 risk-assessment HWPX, SHA256 c624ea2e72c4e79b8daa011375d2105f3f917e069b47dfd95c9850b193d21d46.
Recompute hashes from actual supplied bytes. If any hash mismatch or file inaccessible, STOP THAT FILE with recorded error; no speculative recovery from filename.

## S0 PREFLIGHT / READ ONLY
Verify repo HEAD and 046 baseline, PDF/HWP/HWPX file hashes, SoT row count 189 and current 10 native-HWP observed-field rows; find suitable native HWP5 OLE/CFB BodyText parser and HWPX XML table parser. Collect exact versions. If no parser reliably preserves cell boundaries, mark PARTIAL; do not infer layout from plain text.

## S1 HWP5 FORM BOUNDARY EVIDENCE
Parse HWP5 BodyText sections at paragraph and table-control level. Build a full ordered manifest of headings and their start/end boundaries. For each form record heading spelling, ordered paragraphs, table index, row/column structure, merged-cell hints, visible field labels, page locator only if justified, CFB stream and record ordinal. No rewrite of original HWP. Cross-check 2022 MOEL guide PDF chapter IV reference forms: distinguish printed page label from physical PDF page index. The previously tagged ten REF-C001/002/003/004/005/012/013/014/015/016 must be verified against actual source sections; do NOT copy from SoT as evidence. Investigate 006–011 and ambiguity in the guide reference names. If no exact match, return UNRESOLVED instead of guessing.

## S2 HWPX EIGHT-SECTION EXTRACTION
From Contents/section0.xml (or actual section paths), reconstruct ordered eight form sections, their page/paragraph/table/row/cell locator, merged cells if present, literal headers and labels. Preserve 2023 source edition and HWPX checksum as source identity. Inspect difference between forms (risk information,巡 inspection, interview, safety-data review, checklist, control measures, TBM, near miss); **do not conflate risk-identification survey with risk-assessment outcome**. Preserve 4 unlinked original sections as separate evidence, NOT new SoT candidate IDs.

## S3 EVIDENCE MANIFEST (before DB)
Write source section manifest text/JSON (no copyrighted original bytes in Git) to docs/reference-forms/evidence/REF01-SOURCE-SECTION-MANIFEST-047.md, with for each exact source section:
source SHA256, source title/year, section ordinal, exact Korean heading, HWP5/HWPX structural locator, tabular cell coordinates and extracted labels, extraction confidence (NATIVE_TABLE_VERIFIED / NATIVE_PARAGRAPH_ONLY / PDF_CROSSCHECK_ONLY / UNRESOLVED), artifact type, candidate matching research_id if justified, relationship kind EXACT_SOURCE_SECTION / RELATED_STAGE / VARIANT / UNDETERMINED, parser limitations and evidence references.
Require counts: HWP section inventory and HWPX exactly 8 numbered forms (or recorded discrepancy). Annotate NULLs honestly. Do not claim real mandated legal fields without LEG.

## S4 GPT REVIEW GATE
Submit S0–S3 receipt FIRST. STOP before DB writes for new source-asset/section identities, canonical identifiers, original field replacements, or changes to source_document_access. GPT must independently inspect evidence and authorize specifically scoped SQL (with Owner gate for schema changes).
Existing DB proposed_fields/observed_fields must remain unchanged in this WO. No migrations or table creation.

## S5 RETURN
- exact file hash verification;
- parser name/version and native cell fidelity;
- HWP section count + HWPX 8 section count and per-section fields;
- source-to-research ID matching matrix with ambiguities;
- PDF cross-check by printed/physical page;
- Git manifest link/commit;
- DB mutation count 0, 189 rows unchanged;
- failures and blocked items;
- FINAL = EVIDENCE_READY_FOR_GPT_REVIEW / PARTIAL / BLOCKED.
Do not expand to other sources or launch downstream implementation.

## Security and rights
Owner source files private; do not commit source file bytes or distribute them. Copyright/reuse and LEG mandatory field judgments remain pending. Never bypass protected external site authentication.
