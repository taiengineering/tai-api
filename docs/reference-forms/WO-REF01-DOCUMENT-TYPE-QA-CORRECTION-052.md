# WO-REF01-DOCUMENT-TYPE-QA-CORRECTION-052
2026-10-08. GPT review of evidence/REF01-DOCUMENT-TYPE-CLASSIFICATION-PROPOSAL-051.md.
Status: READY FOR CLAUDE EVIDENCE CORRECTION; WO-051 classification proposal not approved for database persistence.

Authority: GPT analysis/design/independent verification; Claude Code investigation and evidence; Owner approval. PRJ governance, LEG legal SoT. Repo taiengineering/tai-api branch docs/tai-reference-forms-charter-obj-20261008. Database project vwlahtguyggrhvslabax public.ref_form_research_items: baseline 189 rows, observed_fields nonempty 14, canonical assigned 0, owner/publication gates unchanged.

## Known issues requiring correction
1. EQUIP-01..05 titles are 작업계획서 yet assigned CHECKLIST. Compare output purpose; PLAN candidate, retain PROVISIONAL without originals.
2. REF-C045 '소방시설 자체점검 실시결과 보고서' assigned CHECKLIST; REPORT candidate, preserve legal official form review gate.
3. REF-C063 '사후관리 조치결과 보고서 별지86' assigned EVALUATION; REPORT candidate, with statutory form original unverified.
4. REF-C007 original HWP is '안전보건 예산 편성항목 예시' (category list); formerly FORM: reconsider PLAN vs REFERENCE. Determine principal output without claiming an interactive input field.
5. REF-C009 staff placement and duties table formerly FORM; examine REGISTER/RECORD and avoid false source structural confidence.
6. RP-07 monthly improvement-task management table formerly EVALUATION; REGISTER candidate.
7. PRA-22-04 isolation/stock adjustment approval form formerly REGISTER; FORM candidate.
8. Recheck other similar keyword-induced type errors, including FORM vs PLAN, CHECKLIST vs REPORT, REGISTER vs RECORD and statutory reporting forms.
9. REF-C008 evidence rationale incorrectly cites '배점/점수'; its actual observed_fields hold rating criteria, position, name, responsibilities and evaluations. Fix rationale from actual records.
10. REF-C010 WO-051 notes misquote visual node N24 as '관할관청 보고'. WO-050 source N24 = '현장 안전보건활동'; correct, preserving flow chart as source section, no extra research IDs.
11. Distinguish HWP paragraph-only verified text vs HWPX table hierarchy and image diagram. Do not label complete HWP cell geometry verified. Source evidence tiers need clear terminology and definitions; if existing tier SOURCE_STRUCTURE_VERIFIED retained as generic source inspection, add explicit fidelity tag NATIVE_PARAGRAPH_ONLY.
12. WO-051 report claims two non-provisional source-structure rows but totals show 14 non-provisional; correct arithmetic statement.

## Execution
S0 read 046-051 and WO-050; verify live DB read-only baseline, snapshot branch head.
S1 systematically QA all 189 proposed classifications, focused above. Generate explicit per-ID reasoned change matrix with old/new types, strongest actual evidence and confidence, leave unresolved as UNDETERMINED or provisional. Keep the 189-row proposal immutable as evidence history.
S2 correct provenance text, N24 node, C008 rationale, confidence/fidelity claims, and discrepancy counts. Do not conflate file section structure with confirmed input fields; WORKFLOW_DIAGRAM is not a form.
S3 commit new corrected 189-row proposal and errata under docs/reference-forms/evidence/REF01-DOCUMENT-TYPE-QA-052.md. Check 189 unique IDs, all ten enum values, sums=189, evidence and confidence, no unsupported certainty; report diff from 051 and exact type totals.
S4 return commit, evidence path, changed ID count, provisional totals, unresolved, db_mutations=0, verdict EVIDENCE_READY_FOR_GPT_REVIEW / PARTIAL / BLOCKED. STOP for GPT independent verification.

Forbidden: SQL mutations, new original/source discovery, new research rows, canonical merges/assignments, title corrections, LEG assertions, rights decisions, production services/build/deploy/merge, reading TAI AUTO/legacy database.
