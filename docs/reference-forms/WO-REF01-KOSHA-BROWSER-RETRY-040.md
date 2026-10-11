# WO-REF01-KOSHA-BROWSER-RETRY-040
Date 2026-10-08 | Status READY_FOR_CLAUDE_EXECUTION, NOT EXECUTED
Based on GPT independent verification of PILOT-MANIFEST-REF-C001-010.md and current web retrieval.

## Verified external observations
Search/indexed text still lists 2025-02-07 KOSHA Busan article 453942, board 141 and 5 attachments (PDF, HWP, HWP, HWP, ZIP). The 2024-04-23 KOSHA Eastern Gyeongnam crosspost article 449234 also lists same attached form families, though opening the live crosspost may redirect/be inactive.
- Primary: https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?articleNo=453942&boardNo=141&mode=view
- Existing crosspost: https://oshri.kosha.or.kr/kosha/intro/easternGyeongnamBranch_A.do?article.offset=20&articleLimit=10&articleNo=449234&mode=view
Search result listings prove existence of published *attachment names*, NOT accessible file bytes. Prior Claude Code API probe got permission error and no usable HWP.
Scope remains REF-C001..010 only (all in attached [붙임2] HWP). No expansion.

## Division and guards
GPT = analysis, exact instruction, independent verification; Claude Code = technical investigation/file retrieval/evidence; Owner = approval.
PRJ governance and LEG legal SoT. Supabase public.ref_form_research_items (project vwlahtguyggrhvslabax) = reference forms SoT.
No source discovery beyond those already known, no login bypass, credential extraction, hidden token reuse, new unapproved sources, private original copying, TAI AUTO/legacy DB comparisons, migrations, deploy/merge/public downloads.

## Execute only
1. Baseline: commit, 189 DB rows, ten existing blocked records, observed_fields remains [].
2. With an ordinary supported interactive browser, open existing article URL; check article text, five attachment names and whether standard website download click works for [붙임2]. Use only normal public visitor path. If login required, STOP; do not manufacture or capture bearer JWT. If browser automation unavailable, report BROWSER_NOT_AVAILABLE instead of inferring permanent login requirement from raw API errors.
3. If normal click succeeds, preserve original bytes **in temporary local private directory** (not Git nor public storage), record exact download URL after click, SHA256, bytes, MIME, actual file type, source article, attachment name, date, and selected file section. If zero-byte or HTML error file, treat as failure.
4. If [붙임2] downloaded, inspect it via available HWP viewer/parser using native text/structure. Enumerate REF-C001–010 content sections/field labels/table headers literally and cite page/section plus file checksum. Separate from proposed_fields. If text extraction is untrustworthy, mark SECTION_UNVERIFIED. Don't use OCR except last resort, and never infer legally requiredness from an example.
5. Validate what official notice actually says about adaptation versus commercial redistribution. Rights remain UNVERIFIED unless explicit reuse terms are independently documented. LEG legal_required_fields untouched.
6. Write a new evidence receipt in Git (text only, no third-party original bytes) showing per-ID outcome, source link, file checksum, fields with precise references, failure explanation and safe handling. Do NOT overwrite the original failed pilot manifest.
7. Update ONLY ten existing SoT rows after defensible original evidence is recorded. Conditional WHERE keeps source_document_access baseline and preserves pre-existing fields. On success, fill source_attachment_url, source_document_checksum, observed_fields (verbatim with provenance), source_document_access=DOWNLOADED_VERIFIED. On failure update only precise failure/status evidence and do not populate observed_fields. All REVIEWED/owner/publication/legal/right gates remain unchanged.
8. Return detailed BEFORE/AFTER SQL results and STOP for GPT independent check. No next batch.

## Acceptance
PASS only if true file bytes with non-zero size and reproducible checksum, and per-ID fields actually matched in original HWP. PARTIAL if some forms segmented and some not. BLOCKED if only indexed names or failed browser click. No invented download metrics or licensing assertions.
