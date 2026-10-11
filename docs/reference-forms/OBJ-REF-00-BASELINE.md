# OBJ-REF-00 — Baseline evidence v1 (2026-10-08)

Status: IN_PROGRESS, evidence partial; **not CLOSED**.

## Verification after charter/workplan Git upload
- Git target: taiengineering/tai-api / docs/tai-reference-forms-charter-obj-20261008, verified file reads for:
  - docs/reference-forms/TAI-REF-FORM-PLAN-001.md (blob ab1b8958ff342f27b648ba1ab6cdff1f0201cf30)
  - docs/reference-forms/TAI-REF-FORM-OBJECT-PLAN-001.md (blob 91af07e7b3984ca681b52796a8cdd0dced2d876b)
- Supabase project: vwlahtguyggrhvslabax; SELECT-only on public tables.
- SQL (read only): `SELECT 'document_forms' AS t,COUNT(*) n FROM public.document_forms UNION ALL SELECT 'document_form_master',COUNT(*) FROM public.document_form_master UNION ALL SELECT 'form_templates',COUNT(*) FROM public.form_templates;`
- Observed: document_forms=260, document_form_master=64, form_templates=11, sum=335 records; **not** distinct documents.
- Last observed reference_form* table existence check: no reference_form* tables in public. New CMS has not been created.
- Existing separate document engine docs located in docs/document-engine/obj00; object model reference located in docs/tai-rebuild/01_작업계획서_object방식.md.
- Existing conversation artifacts locally inspected: research V0.1 has 5 sheets, SEO V0.2 7 sheets, CMS V0.3 13 sheets. Each includes '통합 후보 인벤토리' 219 worksheet rows = header + 218 candidates. CMS V0.3 also has SEO 콘텐츠 설계 219 rows. **These remain unverified candidates**, not authoritative requirements.
- No table writes or deployment.

## Unverified / needs next evidence
- Per-row primary IDs, name/key collision counts and status in all 3 tables need current read-only snapshot.
- Legal obligation/source claims require LEG and current official government records. Do not infer obligation from label '법정서식'.
- Full coverage of actual industry-specific safety management forms not established.
- Exact duplicate mapping across 335 raw records and 218 candidates not run.
- Individual public-source licensing and HWP/HWPX conversion test not run.
- Owner approval pending for later implementation stages.

## Next
REF-00: capture column/key/review baseline and repo contract boundaries; mark as DONE only after independent verification. Then REF-01 discovery. Production DB DDL/apply remains BLOCKED.
