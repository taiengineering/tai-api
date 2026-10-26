# WO-REF01-SOURCE-IDENTITY-CORRECTION-048
2026-10-08 | GPT independent review of WO-047 | READY FOR CLAUDE EXECUTION; no mutations authorized by this document alone.

## Critical independent finding
Claude WO-047 manifest incorrectly declares HWP-11 '도급·용역·위탁 업체 안전보건 수준 평가 예시' UNRESOLVED / no research_id. Existing SoT record REF-C011 has exact corresponding heading '도급·용역·위탁 업체 안전보건 수준 평가' (verified direct SQL on 2026-10-08). Therefore HWP-11 ↔ REF-C011 is supported, and NEW RECORD CREATION IS FORBIDDEN.
DB was read-only on GPT review: 189 rows; 10 observed_fields populated.

## GPT determinations
- REF-C006: original HWP-06 heading 'KRAS 시스템 위험성평가표 작성 예시' differs from study title '위험성평가표(빈도강도법)'. Native observed field labels may be linked to a **related candidate source section**, but DO NOT silently label as exact title/whole-format identity, change existing source_title, or claim the original KOSHA content is identical across edition/website.
- REF-C007: HWP-07 '안전보건 예산 편성항목 예시', paragraph-level observation acceptable as actual source-field evidence, but these are budget category labels, not necessarily standalone interactive input fields. Capture type CATEGORY/ROW_LABEL vs INPUT_LABEL.
- REF-C008: HWP-08 has two distinct components: evaluation standards (양호/보통/미흡) and evaluation table (직책/성명/담당업무/평가); capture both with parent section provenance, not an invented single flat form.
- REF-C009: HWP-09 staff assignment list exact original label evidence acceptable; role-specific task lists are examples/statutory quotations from guide, not automatic mandatory input fields.
- REF-C010: HWP-10a image-only crush accident flow chart, HWP-10b fall scenario, HWP-10c asphyxiation/electrical scenario should be preserved as three independently identified **source sections**, within a possible related scenario family. No canonical merge and no automatic assumption that REF-C010 means all three. HWP-10a observed fields remain empty until faithful visual extraction.
- REF-C011: HWP-11 confirmed existing REF-C011, source original paragraph labels can be reviewed with reference to PDF page 111. Correct WO-047 erratum explicitly; do not rewrite evidence history.
- HWPX eight sections: native table/row/cell nesting confirmed; missing hp:cellAddr row/col geometry is a residual limitation. Do not claim exact coordinates.

## Claude Code actions (evidence correction only)
1. Read original WO-047 and Git manifest 047 and direct SoT existing rows REF-C006..011; obtain SQL proof of REF-C011 and quote IDs/title.
2. Write separate Git erratum at docs/reference-forms/evidence/REF01-SOURCE-SECTION-ERRATA-048.md, preserving original receipt 047. Correct HWP-11 to REF-C011, disclose REF-C006 title divergence, and clarify 10a/b/c and counted sections; show HWPX table nesting vs exact cells issue.
3. Produce a per-ID proposed write matrix (006,007,008,009,010,011) with exact original labels, locators, confidence, and source-document checksum; do not use source research hypotheses as field evidence.
4. **STOP before updating Supabase**. GPT will independently review exact proposed writes. Keep 189 rows, observed_fields nonempty 10, canonical_candidate_id 0, rights/LEG gates unchanged. No schema, migrations, service code, deploy, new research records, TAI AUTO comparison or external source discovery.

## Acceptance
Correctly recognizes existing REF-C011; fields separated by source purpose and type; no unauthorized form merge; evidence-only Git receipt committed; zero DB changes.
