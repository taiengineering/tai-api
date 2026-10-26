# OBJ-REF-01 QA Batch A (001–040) — DB checkpoint 26
Date 2026-10-08
Authority: Owner requested DB checkpoint approach and sequential resumption; additional discovery frozen.
Project vwlahtguyggrhvslabax, table public.ref_form_research_items (private RLS enabled).
Source of row identity: 24 provenance research register, REF-C001..REF-C040.

## Applied changes
- Updated exactly 40 existing rows, without creating new candidate rows.
- For each: workflow_family, work_trigger, disposition (INDEPENDENT_CANDIDATE, provisional), reviewer_notes (basis and blockers), payload QA identifiers, updated_at and review_status=IN_PROGRESS.
- Recorded 8 potential same-purpose references by ID: 025↔012, 029↔006, 030↔016, 031↔024, 032↔011, 034↔010, 035↔013, 036↔015. Cross-references are not final merge decisions.
- Official KOSHA webpage public examples (1–24) are NOT legal annexes by default; provision type only a working hypothesis. Report names kept verbatim including evident typos.
- No legally required field names, file rights, or document formats approved. No independent form file created.
- All 40 still require original content / LEG and licensing verification, thus IN_PROGRESS not REVIEWED.
- SQL readback: total 189; QA-A 40; IN_PROGRESS 40; PENDING 149.
- Do not change existing TAI AUTO or form data; no new source discovery. No runtime app changes or deployment.

## Resume checkpoint
Next batch **B=REF-C041..REF-C080**. Read rows before update, perform title+event+function discrimination. Update only pending, verify 40 count, store batch marker B-041-080. If unknown set explicit blocker, not invented field truth.
Remaining C (81–120) D (121–160) E (161–189). Count of research rows != count of final unique templates.
REF-01 QA remains open, REF-02 blocked pending owner gate.
