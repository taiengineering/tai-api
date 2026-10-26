# WO-REF01-KOSHA-ACCESS-RECHECK-040
Date 2026-10-08. GPT independent verification of WO-039: database integrity PASS; original-file acquisition BLOCKED; cause of missing Bearer token NOT independently established.
Source pilot: docs/reference-forms/evidence/PILOT-MANIFEST-REF-C001-010.md.
Scope remains REF-C001..010 ONLY. No new forms or source discovery. No app deploy, schema changes, new DB rows, approval transitions or bypass of access controls.

## Independent findings
- Evidence manifest exists in Git. Full source attachment URLs/hash/content still unknown.
- DB exact 10 rows have source URL, PAGE_ACCESSIBLE_FILE_AUTH_BLOCKED, NULL file URL and SHA, empty observed_fields, FIELDS_UNVERIFIED, RIGHTS_UNVERIFIED, IN_PROGRESS and NOT_READY.
- Corpus 189 unchanged, REVIEWED count 0.
- Claude's technical probes returned permission error; this alone does not prove real human login is required, or that the SPA cannot access public content in a normally initialized anonymous browser.
- Label PAGE_ACCESSIBLE_FILE_AUTH_BLOCKED currently documents investigative attempt, not independently proven authentication policy. Leave historical result intact until conclusive evidence.

## Claude Code narrow remediation (read-only)
1. In an ordinary browser session, without spoofing Bearer tokens or bypassing auth, open ONLY the previously recorded official KOSHA article URL in a fully loaded browser. Record page title, whether posted article and attachment listings render, and browser-visible HTTP status codes. Do not use personal credentials, cookies or JWT in receipts.
2. If normal anonymous UI loads article and download, use the website-provided permitted attachment action; record exact link, file name/type, size, SHA256, 10 requested title association. No third-party bytes in Git.
3. If anonymous UI cannot load, distinguish (a) actual login required, (b) JS/session/bootstrap initialization failure, (c) blocked/inaccessible environment, (d) missing/deprecated article. Do not infer one from a 401 refresh endpoint alone. Report HAR only after secret/cookie/auth-header redaction; otherwise textual status only.
4. Preserve all current SoT field and legal/rights states. **No DB mutation in this diagnostic WO**; return diagnostic evidence to GPT first.
5. Do not search new KOSHA pages or replace source with mirror in this WO. No next form ID. STOP for independent GPT assessment.

## Acceptance
- Concise root cause: independently observed / uncertain, with reproducible privacy-safe evidence.
- Page visible vs SPA shell distinction; attachment accessible vs not.
- Precise correction proposal for DB status only if supported, but DO NOT apply.
- State COMPLETE/INCONCLUSIVE and DO_NOT_EXPAND=TRUE.
