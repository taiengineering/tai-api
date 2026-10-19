# REF-01 SoT proposed-fields batch 02 checkpoint 35
Date: 2026-10-08. Owner discovery freeze active.
Project vwlahtguyggrhvslabax; table public.ref_form_research_items remains research SoT, LEG remains legal SoT.

## Inputs and mutation
Already collected Git reports 18, 19, 21 only. Native table column proposed field themes/independent field themes was read; existing research IDs P-01..26 (26), RP-01..23 (23), MNT-01..05 (5), CHW-01..05 (5) = 59.
Parsed comma-separated draft field themes as proposed_fields JSON arrays, preserving source report attribution and SOURCE_REPORT_HYPOTHESIS_ONLY in payload. Applied 30 + 29 existing-record updates, no new source discovery, no new research row insertion.
Excluded report 22 PRA-22-01..10: research table contains purpose statements but **no actual proposed field-theme column**, thus do not invent fields.
Other remaining rows are official listed documents, engineering/annex records, and/or existing researched candidates requiring individual field analysis; don't fill without evidence.

## SQL readback
189 total research rows.
98 proposed_fields nonempty (prior 39 + new 59).
PROPOSED-02 marker exactly 59.
Observed original source fields nonempty 0.
LEG-validated legally required fields nonempty 0.
All field claims remain research hypotheses; no REVIEWED, legal/licensing approval, CMS launch or form asset publication.
Existing TAI DB or AUTO artifacts not compared/copied.

## Next
Continue from earlier collected records 09–12 and registry 13, check if they actually document candidate field themes. If absent, leave empty and mark MISSING_SOURCE_FIELD_DETAIL. Make differentiated proposals only via explicit owner design stage, and never insert them as source-observed fields.
Existing records remain 189; no new candidate collection.
