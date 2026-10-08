# OBJ-REF-01 QA Batch E (161-189) checkpoint 30
Date 2026-10-08. No further collection permitted.
Supabase project vwlahtguyggrhvslabax, table public.ref_form_research_items.

## Work performed
Final 29 source research rows from existing reports 19 (RP-15..23), 21 (MNT-01..05, CHW-01..05) and 22 (PRA-22-01..10). Read original Git report tables and explicitly restored correct source_title by source columns. Preserved original source_id. Kept original evidence classes separate from TAI hypotheses in JSON payload. Recorded source family/work_trigger, provisional INDEPENDENT_CANDIDATE, review_status=IN_PROGRESS. Not a legal/rights/field verification.
## Readback
total 189; in_progress 189; pending 0; E marker 29.
All five batches A-E saved. **Completion of title/workflow classification is not completion of REF-01 source verification**; no row set REVIEWED.
## Known defect and corrective next
The old provenance ledger 24 incorrectly parsed some original multi-column report tables: reports 18 and 19 used workstream instead of document title. D+E database rows have been corrected against source reports. A future 189-row source-alignment audit should check additional misleading title mappings, especially reports 14/15/17 and generic evidence status; do not assume past classifications correct.
## Governance
No new discovery, old TAI DB comparison, AUTO form copying, public CMS generation, deployment or service changes. REF-02 not yet authorized. Next: corpus-wide completeness/evidence check and cross-reference analysis, only preexisting sources. LEG and reuse rights pending.
