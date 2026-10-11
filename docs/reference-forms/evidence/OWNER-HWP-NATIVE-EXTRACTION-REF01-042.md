# REF-01 owner-uploaded HWP native extraction / checkpoint 042

Date: 2026-10-08. No new source discovery or service implementation.

Owner-uploaded 2022 MOEL reference form collection HWP5, 897024 bytes, SHA256 e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe. Parser inspected original CFB/OLE streams and raw-deflate-compressed BodyText/Section0, decoding HWP paragraph-text record tag 67. This validated paragraph headings and field labels, not necessarily table borders, exact cell coordinates, page breaks or legally required fields. Built-in LibreOffice HWP converter could not read it, so structure-level work remains.

## Exact existing SoT rows populated from internal HWP headings
- REF-C001: safety management policy example, date, company and CEO signature markers.
- REF-C002: goal and implementation plan (two variants), preparer/reviewer/approver, objectives, schedule, metric, department, budget, achievement.
- REF-C003: hazardous equipment register, equipment identifier, capacity, location, quantity, inspection category, guard, frequency, potential injury.
- REF-C012: work permit example, job type, department/contractor, name/signature, request interval, job, workplace, equipment, workers, safety measures and approver.
- REF-C013: incident investigation report, incident time/place, investigators, injuries, property damage, causes, expert opinion, corrective measures and photographs.

DB project vwlahtguyggrhvslabax; public.ref_form_research_items: 5 records previously observed_fields empty now contain exact native-file-visible labels with section headings and UNVERIFIED requiredness. Each carries source_document_checksum, source_document_access OWNER_UPLOADED_HWP_TEXT_PARSED_PARTIAL, owner_source_field_batch OWNER-HWP-01. Original source URL provenance to the *particular bytes* remains unverified; no download URL invented, rights remain UNVERIFIED, LEG required fields remain empty. 189 study rows retained; observed_fields nonempty now 5; LEG fields 0.

Owner also uploaded a 134-page guidance PDF with illustrative forms beginning printed section IV p79, and a 2023 risk-assessment HWPX with eight separate forms. These are source files, not yet mapped as identical to the 2022 HWP titles. The HWPX must be separately mapped by exact task/format evidence without altering existing candidate counts.

## Remaining action
Continue HWP Section0 form-headings map for other REF-C004..016, with nontrivial layout ambiguities flagged. Reconstruct HWP tables with stronger parser/viewer and cross-check PDF section IV. Never claim full implementation-ready state from plain text alone. No new source discovery, no rights/LEG approval, no publication or deploy.
