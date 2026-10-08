# REF-01 SoT proposed fields checkpoint 34
Date 2026-10-08. Collection freeze remains in force.

## Target and source
Supabase project vwlahtguyggrhvslabax, table public.ref_form_research_items.
Read existing report 14 (equipment, confined space), report 15 (governance), and report 17 (environment, fuel gases, research labs, document control).
For 39 existing research IDs, extracted only the report's **proposed field themes** (the original table's fourth column), split comma-separated themes into JSON arrays, and wrote to proposed_fields.
Source report filename, SOURCE_REPORT_HYPOTHESIS_ONLY, and batch PROPOSED-01 are preserved in each row payload.

## Verification
Total rows 189; proposed_fields nonempty 39; observed_fields nonempty 0; legal_required_fields nonempty 0; batch PROPOSED-01 exactly 39.
No original statutory/third-party HWP/PDF inner fields have been inspected as part of this batch. Thus observed_fields and legal_required_fields intentionally remain empty.
All 39 still have pending source field, LEG and rights checks and are not finished publication assets.

## SoT and governance
This DB is authoritative for reference-form candidate status and proposed fields, not for law; LEG remains legal SoT.
No new source discovery, comparison with old TAI DB, AUTO document copying, CMS publication, code deployment, or Owner approval transition.
Next: fill proposed_fields for remaining existing report-source candidates using their native source table columns, then independently examine already discovered official originals for observed_fields and LEG requiredness, logging source links and rights separately.
